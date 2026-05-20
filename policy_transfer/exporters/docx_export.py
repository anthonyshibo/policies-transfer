from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document

from policy_transfer.config import NEW_BROKER_COMPANY, NEW_BROKER_LICENSE_NO
from policy_transfer.models import PolicyCase


def export_service_appointment(template: Path, output: Path, case: PolicyCase) -> None:
    doc = Document(str(template))
    sign = _chinese_date(case.sign_date.value) if case.sign_date.value else _chinese_date(date.today().isoformat())
    proposer_cn = case.proposer.chinese_name.value or case.proposer.english_given_name.value
    proposer_en = _english_name(case)
    proposer_id = case.proposer.id_number.value
    policy_no = case.policy_no.value or case.proposal_no.value
    tr_name = case.tr_name.value
    tr_license = case.tr_license_no.value

    for paragraph in doc.paragraphs:
        text = paragraph.text
        if text.startswith("日期："):
            paragraph.text = f"日期：{sign}"
        elif "本人" in text and "身份证号码" in text:
            paragraph.text = (
                f"本人____{proposer_cn}______, 身份证号码_{proposer_id}___，謹此函確認，"
                f"將委任{NEW_BROKER_COMPANY}（牌照号码：{NEW_BROKER_LICENSE_NO}）为本人新的保險經紀公司."
            )
        elif "另委任 業務代表" in text:
            paragraph.text = (
                f"另委任 業務代表：_{tr_name}__（IA Code:__{tr_license}____）為本人在上述公司的保險經紀人管理我的保單，"
                f"保單號碼:_{policy_no}_______________________________，委任即日起生效。"
            )
        elif text.startswith("姓名:"):
            paragraph.text = f"姓名:__{proposer_en}___"

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))


def _english_name(case: PolicyCase) -> str:
    return " ".join(part for part in [case.proposer.english_family_name.value, case.proposer.english_given_name.value] if part).strip()


def _chinese_date(value: str) -> str:
    parts = value.split("-")
    if len(parts) == 3:
        return f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日"
    return value
