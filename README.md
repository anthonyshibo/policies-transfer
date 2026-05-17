# Policy Transfer Tool

本地保单转单工具：上传 A 公司保单 PDF，抽取为统一保单模型，人工确认后生成 B 公司文件和 C 系统导入 Excel。

第一版支持 Prudential / 保诚 PDF，架构预留其他保险公司解析器。

## Quick Start

```bash
/Users/anthony/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m policy_transfer.server
```

然后打开：

```text
http://127.0.0.1:8787
```

默认模板路径来自用户提供的附件：

- `/Users/anthony/Documents/transfer/B`
- `/Users/anthony/Documents/transfer/C/policy-import-v181.xlsx`

## Test

```bash
/Users/anthony/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m tests.test_transfer
```

## Output

每个转换任务会生成：

- `client-booklet.pdf`
- `client-acknowledgement.pdf`
- `risk-assessment.pdf`
- `service-appointment.docx`
- `policy-import.xlsx`
- `conversion-report.json`

## Architecture

- `policy_transfer.extractors`: 保险公司解析器插件。
- `policy_transfer.models`: 统一中间数据模型。
- `policy_transfer.exporters`: B 公司文件和 C Excel 导出。
- `policy_transfer.server`: 无外部 Web 框架依赖的本地网页工具。

