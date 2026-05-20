from __future__ import annotations

import os
import sys as _sys
from pathlib import Path

if getattr(_sys, "frozen", False):
    # In PyInstaller builds, __file__ points inside the temporary _MEIPASS
    # extraction directory. Keep mutable data next to the exe instead.
    ROOT = Path(_sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
CASES_DIR = DATA_DIR / "cases"
OUTPUT_DIR = DATA_DIR / "outputs"

DEFAULT_TRANSFER_DIR = Path("/Users/anthony/Documents/transfer")
PROJECT_TEMPLATE_DIR = ROOT / "templates"
PROJECT_B_DIR = PROJECT_TEMPLATE_DIR / "B"
PROJECT_C_TEMPLATE = PROJECT_TEMPLATE_DIR / "C" / "policy-import-v181.xlsx"
PROJECT_TR_REPRESENTATIVES = CONFIG_DIR / "tr_representatives.csv"


def _default_path(env_name: str, project_path: Path, dev_path: Path) -> Path:
    if os.environ.get(env_name):
        return Path(os.environ[env_name])
    return project_path if project_path.exists() else dev_path


DEFAULT_B_DIR = _default_path("POLICY_TRANSFER_B_DIR", PROJECT_B_DIR, DEFAULT_TRANSFER_DIR / "B")
DEFAULT_C_TEMPLATE = _default_path("POLICY_TRANSFER_C_TEMPLATE", PROJECT_C_TEMPLATE, DEFAULT_TRANSFER_DIR / "C" / "policy-import-v181.xlsx")
TR_REPRESENTATIVES_FILE = _default_path("POLICY_TRANSFER_TR_REPRESENTATIVES", PROJECT_TR_REPRESENTATIVES, DEFAULT_TRANSFER_DIR / "tr_representatives.csv")

SUPPLIER_CHANNEL = os.environ.get("POLICY_TRANSFER_SUPPLIER_CHANNEL", "BP-Acorn Insurance Brokers Limited")
SUPPLIER_CHANNEL_CODE = os.environ.get("POLICY_TRANSFER_SUPPLIER_CHANNEL_CODE", "acorn.insurance")
SUPPLIER_USER_ACCOUNT = os.environ.get("POLICY_TRANSFER_SUPPLIER_USER_ACCOUNT", "acorn.insurance")

NEW_BROKER_COMPANY = os.environ.get("POLICY_TRANSFER_NEW_BROKER_COMPANY", "Finexis Advisory (HK) Limited")
NEW_BROKER_LICENSE_NO = os.environ.get("POLICY_TRANSFER_NEW_BROKER_LICENSE_NO", "FB1593")

B_CLIENT_BOOKLET = DEFAULT_B_DIR / "（TR版）客戶資料手冊_繁體 v202604.pdf"
B_ACK = DEFAULT_B_DIR / "Client’s Ack & Agreement 客戶確認及協議書 v202510.pdf"
B_RISK = DEFAULT_B_DIR / "Risk Assessment Form v202507.pdf"
B_SERVICE_DOCX = DEFAULT_B_DIR / "保单服务委任函_曾冬灵.docx"

for directory in (CONFIG_DIR, DATA_DIR, CASES_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

if not PROJECT_TR_REPRESENTATIVES.exists():
    PROJECT_TR_REPRESENTATIVES.write_text("name,ia_no\n", encoding="utf-8")
