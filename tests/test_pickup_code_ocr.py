import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from pickup_code_ocr import (
    Candidate,
    extract_candidates,
    normalize_line,
    prefer_pickup_codes,
    runtime_dir,
    set_cell_lines,
    unique_output_path,
)


class CandidateExtractionTests(unittest.TestCase):
    def test_normalizes_dash_and_internal_spaces(self):
        self.assertEqual(normalize_line("207 － 1 － 4105"), "207-1-4105")

    def test_extracts_multiple_pickup_codes(self):
        values = extract_candidates(
            ["取件码 207-1-4105", "另一个 8-2-901"],
            [0.98, 0.91],
        )
        self.assertEqual([item.value for item in values], ["207-1-4105", "8-2-901"])

    def test_prefers_pickup_code_over_tracking_number(self):
        values = prefer_pickup_codes(
            [
                Candidate("YT8895066339655", 0.99),
                Candidate("207-1-4105", 0.95),
            ]
        )
        self.assertEqual([item.value for item in values], ["207-1-4105"])

    def test_keeps_tracking_number_when_no_pickup_code_exists(self):
        values = prefer_pickup_codes([Candidate("SF1234567890123", 0.96)])
        self.assertEqual([item.value for item in values], ["SF1234567890123"])

    def test_drops_timestamp_and_duplicate_numeric_suffix(self):
        values = extract_candidates(
            ["20260820194031", "YT8895066339655", "8895066339655"],
            [0.99, 0.99, 0.99],
        )
        self.assertEqual([item.value for item in values], ["YT8895066339655"])


class OutputFormattingTests(unittest.TestCase):
    def test_runtime_dir_uses_executable_location_when_frozen(self):
        executable = str(Path("C:/Portable/PickupCodeOCR.exe"))
        with patch("pickup_code_ocr.sys.frozen", True, create=True), patch(
            "pickup_code_ocr.sys.executable", executable
        ):
            self.assertEqual(runtime_dir(), Path("C:/Portable"))

    def test_cell_contains_one_compact_value(self):
        soup = BeautifulSoup("<table><tr><td>old</td></tr></table>", "html.parser")
        cell = soup.find("td")
        set_cell_lines(soup, cell, [" 207 - 1 - 4105 "])
        self.assertEqual(cell.get_text(), "207-1-4105")

    def test_output_path_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            input_path = output_dir / "订单.xls"
            first = output_dir / "订单_取件码已识别.xls"
            first.touch()
            self.assertEqual(
                unique_output_path(input_path, output_dir),
                output_dir / "订单_取件码已识别_2.xls",
            )


if __name__ == "__main__":
    unittest.main()
