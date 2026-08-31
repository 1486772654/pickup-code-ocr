<div align="center">

# 取件码图片识别工具

**自动识别订单 Excel“取件码”列图片中的取件码或运单号，并按一条号码一行输出。**

[![CI](https://github.com/1486772654/pickup-code-ocr/actions/workflows/ci.yml/badge.svg)](https://github.com/1486772654/pickup-code-ocr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[快速开始](#快速开始) · [处理规则](#处理规则) · [命令行用法](#命令行用法) · [赞赏支持](#赞赏支持) · [许可证](#许可证)

</div>

---

## 功能

- 读取订单系统导出的网页格式 `.xls` 文件。
- 准确定位“取件码”列中图片所在的订单行。
- 识别常见取件码和 12 至 20 位运单号。
- 确保“快递网点”列位于“取件码”前；源表中的“快递站/网点”会统一为“快递网点”，图片后的网点文字也会按图片顺序填入。
- 一张图片有多个号码时，复制整条订单信息，每行只放一个号码。
- 有取件码时优先保留取件码；只有运单号时填写运单号。
- 删除“取件码”列中的图片，不新增辅助列。
- 原文件保持不变，结果另存为新文件。

## 快速开始

### Windows 双击运行

1. 安装 [Python 3.10-3.13](https://www.python.org/downloads/)，安装时勾选 `Add Python to PATH`。
2. 下载本仓库源码并解压。
3. 双击 `run_pickup_code_ocr.cmd`。
4. 第一次运行会自动创建 `.venv` 并安装 OCR 依赖。
5. 在弹窗中选择订单 `.xls` 文件。

结果保存在工具目录中，文件名类似：

```text
订单_取件码已识别.xls
```

如果同名文件已存在，程序会自动追加 `_2`、`_3`，不会覆盖旧结果。

### 客户免安装版

客户电脑没有 Python 时，请使用免安装构建包：解压后双击 `PickupCodeOCR.exe`，或运行 `运行取件码识别.cmd` 查看处理统计。必须保留整个文件夹，不能只复制 EXE。

维护者可以在 Windows + Python 3.11 环境中运行下面的命令生成免安装目录：

```powershell
.\build_portable.ps1
```

生成目录为 `dist/PickupCodeOCR`，其中包含 Python 运行时、OCR 依赖和模型文件。

## 处理规则

| 输入情况 | 输出规则 |
| --- | --- |
| 取件码单元格已有文字 | 保留原文字 |
| 图片里有一个取件码 | 写入当前订单行 |
| 图片里有多个取件码 | 复制订单行，每行写一个取件码 |
| 图片里同时出现取件码和运单号 | 优先写取件码 |
| 图片里只有运单号 | 写入运单号 |
| 源表已有“快递站/网点”列 | 移到“取件码”前并统一列名为“快递网点” |
| 源表没有快递网点列 | 在“取件码”前插入“快递网点”列，并读取图片后的网点文字；没有网点文字时留空 |
| 图片处理失败或没有识别到号码 | 写入“未提取到号码”，并在窗口提示复核 |

支持的常见格式：

```text
1-1-1101
207-1-4105
YT8895066339655
SF1234567890123
123456789012345
```

## 命令行用法

直接运行 Python：

```powershell
python pickup_code_ocr.py "D:\订单.xls"
```

指定输出文件：

```powershell
python pickup_code_ocr.py "D:\订单.xls" -o "D:\识别结果.xls"
```

禁用直连失败后的本地代理重试：

```powershell
python pickup_code_ocr.py "D:\订单.xls" --proxy ""
```

## 本地安装

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe pickup_code_ocr.py "D:\订单.xls"
```

## 输入文件要求

- 文件扩展名为 `.xls`，实际内容是 HTML 网页表格。
- 表头中必须有名为“取件码”的列。
- 图片可以是内嵌 Data URL、本地相对路径或 HTTP/HTTPS 地址。

传统二进制 Excel 97-2003 工作簿不是本工具的目标格式。遇到“文件不是可识别的网页表格”提示时，请先从原订单系统重新导出网页格式 `.xls`。

## 隐私说明

程序在本机处理表格和图片，不会主动上传订单数据。只有表格中图片本身使用 HTTP/HTTPS 地址时，程序才会下载该图片。请不要把真实订单文件、客户姓名、电话、地址或运单数据提交到公开 Issue。

## 已知限制

- OCR 准确率受截图清晰度、裁剪、遮挡和字体影响。
- 低清图片、反光图片和字符粘连可能需要人工复核。
- 输出仍使用网页格式 `.xls`，可由 Microsoft Excel 或 WPS 打开。
- 默认在图片直连失败后尝试 `127.0.0.1:7897`；可通过 `--proxy` 修改或禁用。

## 测试

```powershell
python -m unittest discover -s tests -v
python -m compileall -q pickup_code_ocr.py tests
```

## 技术来源

- [RapidOCR](https://github.com/RapidAI/RapidOCR) 提供本地 OCR 能力。
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) 用于解析和更新 HTML 表格。
- [ONNX Runtime](https://onnxruntime.ai/) 运行 OCR 模型。

各依赖按其各自许可证发布。

## 赞赏支持

如果这个项目对你有帮助，欢迎在 GitHub 点一个 [Star](https://github.com/1486772654/pickup-code-ocr/stargazers)、提交 Issue 或分享给有需要的人。

也可以自愿扫码支持后续维护：

<p align="center">
  <img src="docs/donate.png" alt="微信支付赞赏二维码" width="320" />
</p>

赞赏完全自愿，不影响项目功能、问题反馈或后续使用。

如需替换收款码，只需要替换 `docs/donate.png`，不需要修改程序代码。

## 参与贡献

提交问题或改进前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## 许可证

本项目采用 [MIT License](LICENSE)。

## 联系方式

作者邮箱：1486772654@qq.com。
