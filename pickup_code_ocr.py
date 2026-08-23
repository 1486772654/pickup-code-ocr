#!/usr/bin/env python3
"""Extract pickup codes/tracking numbers from images in HTML-based .xls files."""

from __future__ import annotations

import argparse
import base64
import copy
import ipaddress
import re
import socket
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote_to_bytes, urlparse

import numpy as np
import requests
from bs4 import BeautifulSoup
from PIL import Image
from rapidocr import RapidOCR


DEFAULT_PROXY = "http://127.0.0.1:7897"
IMAGE_TIMEOUT = (8, 45)


def runtime_dir() -> Path:
    """Return the user-visible tool directory for source and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


TOOL_DIR = runtime_dir()


@dataclass(frozen=True)
class Candidate:
    value: str
    confidence: float


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def read_html(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = data.decode(encoding)
            if "<table" in text.lower():
                return text
        except UnicodeDecodeError:
            continue
    raise ValueError("文件不是可识别的网页表格 .xls，或字符编码不受支持。")


def normalize_line(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans({"—": "-", "–": "-", "－": "-", "﹣": "-"}))
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9])", "", text)
    return text.strip()


def looks_like_timestamp(value: str) -> bool:
    if not (len(value) in (12, 14) and value.startswith("20")):
        return False
    formats = {12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}
    try:
        datetime.strptime(value, formats[len(value)])
        return True
    except ValueError:
        return False


def looks_like_date_pickup(value: str) -> bool:
    parts = value.split("-")
    if len(parts) != 3 or len(parts[0]) != 4:
        return False
    try:
        year, month = int(parts[0]), int(parts[1])
        day_prefix = int(parts[2][:2]) if len(parts[2]) >= 2 else int(parts[2])
    except ValueError:
        return False
    return 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day_prefix <= 31


def extract_candidates(lines: Iterable[str], scores: Iterable[float]) -> list[Candidate]:
    found: dict[str, float] = {}
    pickup_pattern = re.compile(r"(?<!\d)(\d{1,4}(?:-\d{1,4}){2,4})(?!\d)")
    alpha_pattern = re.compile(r"(?<![A-Z0-9])([A-Z]{1,5}[-:]?\d{8,20})(?![A-Z0-9])", re.I)
    numeric_pattern = re.compile(r"(?<!\d)(\d{12,20})(?!\d)")

    for raw_text, raw_score in zip(lines, scores):
        text = normalize_line(raw_text)
        confidence = float(raw_score)

        for match in pickup_pattern.finditer(text):
            value = match.group(1)
            if not looks_like_date_pickup(value):
                found[value] = max(found.get(value, 0.0), confidence)

        for match in alpha_pattern.finditer(text):
            value = re.sub(r"[-:]", "", match.group(1)).upper()
            found[value] = max(found.get(value, 0.0), confidence)

        for match in numeric_pattern.finditer(text):
            value = match.group(1)
            if not looks_like_timestamp(value):
                found[value] = max(found.get(value, 0.0), confidence)

    alpha_values = [value for value in found if re.match(r"^[A-Z]", value)]
    for value in list(found):
        if value.isdigit() and any(alpha.endswith(value) for alpha in alpha_values):
            del found[value]

    return [Candidate(value, confidence) for value, confidence in found.items()]


def prefer_pickup_codes(candidates: Iterable[Candidate]) -> list[Candidate]:
    items = list(candidates)
    pickup_codes = [
        candidate
        for candidate in items
        if re.fullmatch(r"\d{1,4}(?:-\d{1,4}){2,4}", candidate.value)
    ]
    return pickup_codes or items


def is_local_target(url: str) -> bool:
    host = urlparse(url).hostname
    if not host:
        return True
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def validate_image(data: bytes) -> bytes:
    with Image.open(BytesIO(data)) as image:
        image.verify()
    return data


def download_image(
    source: str,
    input_dir: Path,
    session: requests.Session,
    proxy: str | None,
) -> bytes:
    if source.startswith("data:"):
        header, payload = source.split(",", 1)
        data = base64.b64decode(payload) if ";base64" in header else unquote_to_bytes(payload)
        return validate_image(data)

    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        local_path = Path(source)
        if not local_path.is_absolute():
            local_path = input_dir / local_path
        return validate_image(local_path.read_bytes())

    try:
        response = session.get(source, timeout=IMAGE_TIMEOUT)
        response.raise_for_status()
        return validate_image(response.content)
    except (requests.RequestException, OSError, ValueError):
        if not proxy or is_local_target(source):
            raise
        response = session.get(
            source,
            timeout=IMAGE_TIMEOUT,
            proxies={"http": proxy, "https": proxy},
        )
        response.raise_for_status()
        return validate_image(response.content)


def run_ocr(engine: RapidOCR, image_bytes: bytes) -> tuple[list[str], list[float]]:
    with Image.open(BytesIO(image_bytes)) as image:
        rgb = np.asarray(image.convert("RGB"))
    result = engine(rgb)
    if result is None or not result.txts:
        return [], []
    return list(result.txts), [float(score) for score in result.scores]


def clean_existing_text(text: str) -> str:
    text = re.sub(r"[\s,，]+", " ", text).strip()
    return text if text not in {",", "，"} else ""


def existing_pickup_values(cell) -> list[str]:
    """Extract manually typed pickup codes without image outlet labels."""
    text_nodes = [str(node) for node in cell.find_all(string=True)]
    if not text_nodes:
        return []
    candidates = prefer_pickup_codes(
        extract_candidates(text_nodes, [1.0] * len(text_nodes))
    )
    return [candidate.value for candidate in candidates]


def extract_outlet_labels(cell) -> list[str]:
    """Read outlet labels written after each image in the pickup-code cell."""
    labels: list[str] = []
    for image in cell.find_all("img"):
        suffix_parts: list[str] = []
        for sibling in image.next_siblings:
            if getattr(sibling, "name", None) == "img":
                break
            suffix_parts.append(
                sibling.get_text(" ", strip=True)
                if hasattr(sibling, "get_text")
                else str(sibling)
            )
        suffix = "".join(suffix_parts).strip(" \t\r\n,，")
        match = re.search(r"[-－—﹣]\s*([^,，]+)", suffix)
        labels.append(match.group(1).strip() if match else suffix)
    return labels


def unique_output_path(input_path: Path, output_dir: Path = TOOL_DIR) -> Path:
    candidate = output_dir / f"{input_path.stem}_取件码已识别.xls"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{input_path.stem}_取件码已识别_{counter}.xls"
        counter += 1
    return candidate


def set_cell_lines(soup: BeautifulSoup, cell, lines: Iterable[str]) -> None:
    cell.clear()
    existing_style = cell.get("style", "").strip()
    text_style = "mso-number-format:'@';"
    cell["style"] = f"{existing_style} {text_style}".strip()
    cleaned = [re.sub(r"\s+", "", line) for line in lines if line.strip()]
    for index, line in enumerate(cleaned):
        if index:
            line_break = soup.new_tag("br")
            line_break["style"] = "mso-data-placement:same-cell"
            cell.append(line_break)
        item = soup.new_tag("span")
        item.string = line
        cell.append(item)


def ensure_outlet_column(soup: BeautifulSoup, rows, pickup_index: int) -> int:
    """Ensure a 快递网点 column immediately precedes 取件码."""
    header_cells = rows[0].find_all(["th", "td"], recursive=False)
    header_names = [cell.get_text(" ", strip=True) for cell in header_cells]
    outlet_index = next(
        (index for index, name in enumerate(header_names) if name in {"快递网点", "快递站", "网点"}),
        None,
    )

    if outlet_index is None:
        outlet_index = pickup_index
        header_cell = soup.new_tag("td")
        header_cell.string = "快递网点"
        header_cells[pickup_index].insert_before(header_cell)
        for row in rows[1:]:
            cells = row.find_all("td", recursive=False)
            if pickup_index < len(cells):
                outlet_cell = soup.new_tag("td")
                outlet_cell["style"] = cells[pickup_index].get("style", "")
                cells[pickup_index].insert_before(outlet_cell)
        return pickup_index + 1

    if header_names[outlet_index] != "快递网点":
        header_cells[outlet_index].clear()
        header_cells[outlet_index].string = "快递网点"

    if outlet_index == pickup_index - 1:
        return pickup_index

    for row in rows:
        cells = row.find_all(["th", "td"], recursive=False)
        if outlet_index < len(cells) and pickup_index <= len(cells):
            outlet_cell = cells[outlet_index].extract()
            current_pickup_index = pickup_index - 1 if outlet_index < pickup_index else pickup_index
            cells = row.find_all(["th", "td"], recursive=False)
            cells[current_pickup_index].insert_before(outlet_cell)
    return pickup_index


def process_file(
    input_path: Path,
    output_path: Path,
    proxy: str | None,
    review_threshold: float,
) -> dict[str, int]:
    source_html = read_html(input_path)
    soup = BeautifulSoup(source_html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("文件中没有找到表格。")

    rows = table.find_all("tr", recursive=False)
    if not rows:
        raise ValueError("表格中没有数据。")

    headers = rows[0].find_all(["th", "td"], recursive=False)
    header_names = [cell.get_text(" ", strip=True) for cell in headers]
    try:
        pickup_index = header_names.index("取件码")
    except ValueError as exc:
        raise ValueError("没有找到名为“取件码”的列。") from exc

    pickup_index = ensure_outlet_column(soup, rows, pickup_index)

    header_names = [
        cell.get_text(" ", strip=True)
        for cell in rows[0].find_all(["th", "td"], recursive=False)
    ]
    order_index = header_names.index("订单号") if "订单号" in header_names else None
    session = requests.Session()
    session.headers.update({"User-Agent": "PickupCodeOCR/1.0"})
    engine = RapidOCR()
    stats = {
        "rows": 0,
        "image_rows": 0,
        "images": 0,
        "recognized": 0,
        "review": 0,
        "failed": 0,
        "added_rows": 0,
    }

    for row_number, row in enumerate(rows[1:], start=2):
        cells = row.find_all("td", recursive=False)
        if pickup_index >= len(cells):
            continue
        stats["rows"] += 1
        pickup_cell = cells[pickup_index]
        images = pickup_cell.find_all("img")
        original_values = existing_pickup_values(pickup_cell)
        outlet_cell = cells[pickup_index - 1]
        original_outlet = clean_existing_text(outlet_cell.get_text(" ", strip=True))
        order_number = ""
        if order_index is not None and order_index < len(cells):
            order_number = cells[order_index].get_text(" ", strip=True).replace("\xa0", "")

        if not images:
            continue

        stats["image_rows"] += 1
        stats["images"] += len(images)
        all_candidates: dict[str, float] = {}
        candidate_outlets: dict[str, str] = {}
        outlet_labels = extract_outlet_labels(pickup_cell)
        image_failures = 0

        print(f"第 {row_number} 行 / 订单 {order_number or '-'}：处理 {len(images)} 张图片")
        for image_number, image in enumerate(images, start=1):
            source = str(image.get("src", "")).strip()
            if not source:
                image_failures += 1
                continue
            try:
                image_bytes = download_image(source, input_path.parent, session, proxy)
                texts, scores = run_ocr(engine, image_bytes)
                detected_candidates = extract_candidates(texts, scores)
                candidates = prefer_pickup_codes(detected_candidates)
                for candidate in candidates:
                    all_candidates[candidate.value] = max(
                        all_candidates.get(candidate.value, 0.0), candidate.confidence
                    )
                    candidate_outlets.setdefault(
                        candidate.value,
                        outlet_labels[image_number - 1]
                        if image_number <= len(outlet_labels)
                        else original_outlet,
                    )
            except Exception as exc:  # Continue processing other images in the same order.
                image_failures += 1
                print(f"  图片 {image_number} 处理失败：{type(exc).__name__}: {exc}")

        values = list(all_candidates)
        entries: list[tuple[str, str]] = []
        seen_values: set[str] = set()
        for value in original_values:
            if value not in seen_values:
                entries.append((original_outlet, value))
                seen_values.add(value)
        for value in values:
            if value not in seen_values:
                entries.append((candidate_outlets.get(value, original_outlet), value))
                seen_values.add(value)

        if not entries:
            entries = [(original_outlet, "未提取到号码")]

        set_cell_lines(soup, outlet_cell, [entries[0][0]] if entries[0][0] else [])
        set_cell_lines(soup, pickup_cell, [entries[0][1]])
        anchor = row
        for outlet, value in entries[1:]:
            cloned_row = copy.deepcopy(row)
            cloned_cells = cloned_row.find_all("td", recursive=False)
            set_cell_lines(soup, cloned_cells[pickup_index - 1], [outlet] if outlet else [])
            set_cell_lines(soup, cloned_cells[pickup_index], [value])
            anchor.insert_after(cloned_row)
            anchor = cloned_row
            stats["added_rows"] += 1

        if values:
            low_confidence = any(score < review_threshold for score in all_candidates.values())
            if image_failures:
                stats["review"] += 1
            elif low_confidence:
                stats["review"] += 1
            else:
                stats["recognized"] += 1
        elif image_failures == len(images):
            stats["failed"] += 1
        else:
            stats["review"] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(str(soup), encoding="utf-8")
    return stats


def select_input_file() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="选择订单 Excel 文件",
            filetypes=[("Excel 97-2003 文件", "*.xls"), ("所有文件", "*.*")],
        )
        root.destroy()
        return Path(selected) if selected else None
    except Exception:
        entered = input("请输入订单 .xls 文件完整路径：").strip().strip('"')
        return Path(entered) if entered else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="识别订单 Excel 取件码列中的图片文字")
    parser.add_argument("input", nargs="?", help="输入的网页格式 .xls 文件")
    parser.add_argument("-o", "--output", help="输出文件路径；默认保存在工具目录中")
    parser.add_argument(
        "--proxy",
        default=DEFAULT_PROXY,
        help="仅在外网图片直连失败后使用的代理；传空字符串可禁用",
    )
    parser.add_argument(
        "--review-threshold",
        type=float,
        default=0.75,
        help="低于该 OCR 置信度时标记待复核，默认 0.75",
    )
    return parser.parse_args()


def main() -> int:
    configure_console()
    args = parse_args()
    input_path = Path(args.input).expanduser() if args.input else select_input_file()
    if input_path is None:
        print("已取消。")
        return 0
    input_path = input_path.resolve()
    if not input_path.is_file():
        print(f"错误：文件不存在：{input_path}")
        return 1

    output_path = Path(args.output).expanduser().resolve() if args.output else unique_output_path(input_path)
    if output_path == input_path:
        print("错误：输出路径不能与原文件相同。")
        return 1

    try:
        stats = process_file(
            input_path=input_path,
            output_path=output_path,
            proxy=args.proxy or None,
            review_threshold=args.review_threshold,
        )
    except Exception as exc:
        print(f"处理失败：{type(exc).__name__}: {exc}")
        return 1

    print("\n处理完成")
    print(f"输出文件：{output_path}")
    print(
        "统计："
        f"订单 {stats['rows']} 行，图片订单 {stats['image_rows']} 行，"
        f"图片 {stats['images']} 张，已识别 {stats['recognized']} 行，"
        f"新增明细 {stats['added_rows']} 行，待复核 {stats['review']} 行，"
        f"失败 {stats['failed']} 行"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
