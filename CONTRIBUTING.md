# 参与贡献

感谢您帮助改进取件码图片识别工具。

## 提交 Issue

请先搜索是否已有相同问题。提交复现材料时，请删除或替换以下内容：

- 客户姓名、电话和地址；
- 订单号、真实取件码和运单号；
- 登录信息、Cookie、Token 和内部网址；
- 本机用户名和私人目录路径。

建议用自制测试图片和虚构号码复现问题。

## 本地开发

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Pull Request

- 保持修改范围清晰，不混入订单文件、日志或虚拟环境。
- 为号码解析规则的变化补充测试。
- 确保测试和语法检查通过。
- 说明行为变化及需要人工复核的边界情况。
