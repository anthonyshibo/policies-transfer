from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CASES_DIR = DATA_DIR / "cases"
OUTPUT_DIR = DATA_DIR / "outputs"

DEFAULT_TRANSFER_DIR = Path("/Users/anthony/Documents/transfer")
PROJECT_TEMPLATE_DIR = ROOT / "templates"
PROJECT_B_DIR = PROJECT_TEMPLATE_DIR / "B"
PROJECT_C_TEMPLATE = PROJECT_TEMPLATE_DIR / "C" / "policy-import-v181.xlsx"


def _default_path(env_name: str, project_path: Path, dev_path: Path) -> Path:
    if os.environ.get(env_name):
        return Path(os.environ[env_name])
    return project_path if project_path.exists() else dev_path


DEFAULT_B_DIR = _default_path("POLICY_TRANSFER_B_DIR", PROJECT_B_DIR, DEFAULT_TRANSFER_DIR / "B")
DEFAULT_C_TEMPLATE = _default_path("POLICY_TRANSFER_C_TEMPLATE", PROJECT_C_TEMPLATE, DEFAULT_TRANSFER_DIR / "C" / "policy-import-v181.xlsx")

B_CLIENT_BOOKLET = DEFAULT_B_DIR / "（TR版）客戶資料手冊_繁體 v202604.pdf"
B_ACK = DEFAULT_B_DIR / "Client’s Ack & Agreement 客戶確認及協議書 v202510.pdf"
B_RISK = DEFAULT_B_DIR / "Risk Assessment Form v202507.pdf"
B_SERVICE_DOCX = DEFAULT_B_DIR / "保单服务委任函_曾冬灵.docx"

for directory in (DATA_DIR, CASES_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
