from __future__ import annotations

import json
import uuid
from pathlib import Path

from policy_transfer.config import CASES_DIR, OUTPUT_DIR
from policy_transfer.models import PolicyCase


def create_case(case: PolicyCase) -> str:
    case_id = uuid.uuid4().hex[:12]
    save_case(case_id, case)
    return case_id


def save_case(case_id: str, case: PolicyCase) -> None:
    path = case_path(case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_case(case_id: str) -> PolicyCase:
    path = case_path(case_id)
    if not path.exists():
        raise FileNotFoundError(case_id)
    return PolicyCase.from_dict(json.loads(path.read_text(encoding="utf-8")))


def case_path(case_id: str) -> Path:
    return CASES_DIR / case_id / "case.json"


def upload_dir(case_id: str) -> Path:
    path = CASES_DIR / case_id / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(case_id: str) -> Path:
    path = OUTPUT_DIR / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path

