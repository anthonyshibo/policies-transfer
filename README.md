# Policy Transfer Tool

本地保单转单工具：上传 A 公司保单 PDF，抽取为统一保单模型，人工确认后生成 B 公司文件和 C 系统导入 Excel。

当前版本：`v0.2.0`

第一版支持 Prudential / 保诚 PDF，架构预留其他保险公司解析器。

## Quick Start

```bash
/Users/anthony/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m policy_transfer.server
```

然后打开：

```text
http://127.0.0.1:8787
```

开发运行和打包默认使用仓库中的内置模板：

- `templates/B`
- `templates/C/policy-import-v181.xlsx`

可通过环境变量覆盖模板和业务机构配置：

- `POLICY_TRANSFER_B_DIR`
- `POLICY_TRANSFER_C_TEMPLATE`
- `POLICY_TRANSFER_SUPPLIER_CHANNEL`
- `POLICY_TRANSFER_SUPPLIER_CHANNEL_CODE`
- `POLICY_TRANSFER_SUPPLIER_USER_ACCOUNT`
- `POLICY_TRANSFER_NEW_BROKER_COMPANY`
- `POLICY_TRANSFER_NEW_BROKER_LICENSE_NO`
- `POLICY_TRANSFER_TR_REPRESENTATIVES`

TR 人员下拉名单默认读取：

```text
config/tr_representatives.csv
```

在上传页选择“手工输入并保存至名单”后，新的业务代表姓名和 IA 号码会写入该 CSV，下次可从名单直接选择；相同姓名及 IA 号码不会重复写入。

格式：

```csv
name,ia_no
CHAN TAI MAN,TR123456
```

首页默认使用原始文档抽取的 TR name / IA 号码；如果选择配置名单或手工输入，则以首页指定值为准。

## Mac App 打包

安装 PyInstaller 后，可执行：

```bash
PYTHON_BIN=/path/to/python3 zsh scripts/build_macos_app.sh
```

产物为 `dist/PolicyTransferTool-Mac-v<版本号>.zip`。代码或内置模板变更后需要重新打包；仅修改外置 `config/tr_representatives.csv` 不需要重新打包。

## Windows EXE 打包

目前 Windows 单文件版经测试需使用 **Python 3.12** 打包；其他 Python 版本可能出现运行错误。先安装 Python 3.12、依赖和 PyInstaller：

```bat
py -3.12 -m pip install -r requirements.txt pyinstaller
```

然后在项目根目录双击 `build.bat`，或执行：

```bat
build.bat
```

脚本的核心打包命令为：

```bat
py -3.12 -m PyInstaller --onefile --windowed --name PolicyTransfer --add-data "templates;templates" --hidden-import policy_transfer.server --hidden-import policy_transfer.extractors --hidden-import policy_transfer.models --hidden-import policy_transfer.exporters --hidden-import docx --collect-all docx --collect-all openpyxl launcher.py
```

生成文件位于：

```text
dist\PolicyTransfer.exe
```

分发给其他 Windows 电脑时，请将 EXE 与可编辑的配置文件夹一起发送：

```text
PolicyTransfer-Windows\
├── PolicyTransfer.exe
└── config\
    └── tr_representatives.csv
```

程序首次运行会在 EXE 同级创建 `data\outputs\` 保存输出文件；手工输入的新 TR 人员会写入同级 `config\tr_representatives.csv`。修改外置 TR 名单无需重新打包；修改代码或内置模板后需要重新打包。

## Test

```bash
/Users/anthony/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m tests.test_transfer
```

## Output

每个转换任务会生成：

- `transfer_{holder}_{policy_no}_client_booklet.pdf`
- `transfer_{holder}_{policy_no}_ack.pdf`
- `transfer_{holder}_{policy_no}_risk.pdf`
- `transfer_{holder}_{policy_no}_appointment.docx`
- `transfer_{holder}_{policy_no}_policy_import.xlsx`
- `transfer_{holder}_{policy_no}_report.json`

## Architecture

- `policy_transfer.extractors`: 保险公司解析器插件。
- `policy_transfer.models`: 统一中间数据模型。
- `policy_transfer.exporters`: B 公司文件和 C Excel 导出。
- `policy_transfer.server`: 无外部 Web 框架依赖的本地网页工具。
