# 部署说明书

本工具是一个轻量本地 Web 应用，核心依赖为 Python。当前版本使用 Python 标准库提供网页服务，不依赖 FastAPI/Node/数据库。

## 生产目录和模板口径

生产使用时，业务人员只需要提供 A 公司保单文件。B 公司表格和 C 系统 Excel 模板是开发/验证阶段用于设计映射和校验输出的参考材料，生产部署时应作为应用内置模板随代码一起发布，不要求业务人员另行准备。

推荐部署结构：

```text
policy-transfer/
  policy_transfer/
  templates/
    B/
      （TR版）客戶資料手冊_繁體 v202604.pdf
      Client’s Ack & Agreement 客戶確認及協議書 v202510.pdf
      Risk Assessment Form v202507.pdf
      保单服务委任函_曾冬灵.docx
    C/
      policy-import-v181.xlsx
  data/
    cases/
    outputs/
```

日常生产输入：

- A 公司保单 PDF：通过网页上传，或后续接入生产 A 目录批量导入。

应用内置模板：

- B 公司模板目录：只由开发/运维维护。
- C 系统 Excel 模板：只由开发/运维维护。

建议用环境变量指定内置模板位置和服务参数：

```bash
POLICY_TRANSFER_B_DIR=/opt/policy-transfer/templates/B
POLICY_TRANSFER_C_TEMPLATE=/opt/policy-transfer/templates/C/policy-import-v181.xlsx
POLICY_TRANSFER_HOST=127.0.0.1
POLICY_TRANSFER_PORT=8787
```

输出文件会写入项目目录下的 `data/outputs/<case-id>/`。

## Linux 服务器部署

推荐环境：Ubuntu 22.04/24.04，Python 3.12。

```bash
cd /opt/policy-transfer
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export POLICY_TRANSFER_B_DIR=/opt/policy-transfer/templates/B
export POLICY_TRANSFER_C_TEMPLATE=/opt/policy-transfer/templates/C/policy-import-v181.xlsx
export POLICY_TRANSFER_HOST=0.0.0.0
export POLICY_TRANSFER_PORT=8787

python -m policy_transfer.server
```

生产建议：

- 放在内网或 VPN 后面，不建议公网裸奔，因为文件包含客户个人资料。
- 用 Nginx 做 HTTPS 和访问控制。
- 用 systemd 托管进程。
- 业务人员只上传 A 公司保单文件；B/C 模板由发布包提供并由运维控制版本。
- 当前“来源区域裁剪预览”依赖 macOS `qlmanage`。Linux 上会自动退回不可裁剪状态；仍可通过“打开整页 PDF”查看来源。若要 Linux 也支持裁剪，下一版可改接 Poppler/PyMuPDF。

## macOS 本地部署

推荐环境：macOS 自带或 Homebrew Python 3.12。

```bash
cd "/Users/anthony/Documents/New project"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export POLICY_TRANSFER_B_DIR="/Users/anthony/Documents/transfer/B"
export POLICY_TRANSFER_C_TEMPLATE="/Users/anthony/Documents/transfer/C/policy-import-v181.xlsx"

python -m policy_transfer.server
```

打开：

```text
http://127.0.0.1:8787
```

macOS 本地版本支持来源字段的裁剪预览，因为系统自带 `qlmanage` 可把 PDF 单页渲染成 PNG。

如果是生产打包后的本地版本，建议把 B/C 模板放在项目内 `templates/`，而不是继续指向开发测试用的 `/Users/anthony/Documents/transfer/B` 和 `/Users/anthony/Documents/transfer/C`。

## Windows 本地部署

推荐环境：Windows 10/11，Python 3.12。

PowerShell 示例：

```powershell
cd C:\policy-transfer
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:POLICY_TRANSFER_B_DIR="C:\policy-transfer\templates\B"
$env:POLICY_TRANSFER_C_TEMPLATE="C:\policy-transfer\templates\C\policy-import-v181.xlsx"
$env:POLICY_TRANSFER_HOST="127.0.0.1"
$env:POLICY_TRANSFER_PORT="8787"

python -m policy_transfer.server
```

打开：

```text
http://127.0.0.1:8787
```

Windows 当前可正常上传、审核、导出 B 文件和 C Excel。来源字段的“裁剪图预览”依赖 macOS `qlmanage`，Windows 会退回为整页 PDF 链接。若 Windows 也需要裁剪预览，建议后续增加 PyMuPDF 或 Poppler 渲染方案。

## 验证

在任一平台部署后运行：

```bash
python -m tests.test_transfer
```

成功时会看到：

```text
All tests passed.
```

然后在网页上传 A 公司保单 PDF，进入人工确认页，保存确认后生成输出文件。

## 安全和运维建议

- 客户资料属于敏感信息，服务器部署时必须启用 HTTPS、访问控制和磁盘权限控制。
- 定期清理 `data/cases` 和 `data/outputs`，避免长期保留客户文件。
- B/C 模板是应用的一部分。模板版本变化时，不要直接覆盖生产旧模板；建议按版本建目录、更新映射并重新跑一次样本对比。
- Python 版本建议使用 3.12。Python 3.13 移除了 `cgi` 模块，当前轻量上传实现不建议直接跑在 3.13。
