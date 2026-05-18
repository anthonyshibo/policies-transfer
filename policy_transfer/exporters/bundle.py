from __future__ import annotations

import json
import re
from pathlib import Path

from policy_transfer.config import B_ACK, B_CLIENT_BOOKLET, B_RISK, B_SERVICE_DOCX, DEFAULT_C_TEMPLATE
from policy_transfer.exporters.docx_export import export_service_appointment
from policy_transfer.exporters.excel_export import export_policy_import
from policy_transfer.exporters.pdf_forms import fill_pdf_form
from policy_transfer.models import PolicyCase


def export_bundle(case: PolicyCase, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for existing in output_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    prefix = _filename_prefix(case)
    files = {
        "client_booklet": output_dir / f"{prefix}_client_booklet.pdf",
        "client_acknowledgement": output_dir / f"{prefix}_ack.pdf",
        "risk_assessment": output_dir / f"{prefix}_risk.pdf",
        "service_appointment": output_dir / f"{prefix}_appointment.docx",
        "policy_import": output_dir / f"{prefix}_policy_import.xlsx",
        "report": output_dir / f"{prefix}_report.json",
    }

    fill_pdf_form(B_ACK, files["client_acknowledgement"], _ack_values(case))
    fill_pdf_form(B_RISK, files["risk_assessment"], _risk_values(case))
    fill_pdf_form(B_CLIENT_BOOKLET, files["client_booklet"], _client_booklet_values(case))
    export_service_appointment(B_SERVICE_DOCX, files["service_appointment"], case)
    export_policy_import(DEFAULT_C_TEMPLATE, files["policy_import"], case)

    report = {
        "case": case.as_dict(),
        "review_issues": case.review_issues,
        "outputs": {key: str(value) for key, value in files.items() if key != "report"},
    }
    files["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return files


def _filename_prefix(case: PolicyCase) -> str:
    holder = case.proposer.chinese_name.value or _english_name(case) or "Holder"
    policy_no = case.policy_no.value or case.proposal_no.value or "No"
    parts = ["transfer", holder, policy_no]
    return "_".join(_safe_filename_part(part) for part in parts if _safe_filename_part(part))


def _safe_filename_part(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"_+", "_", text)
    return text[:80] or ""


def _english_name(case: PolicyCase) -> str:
    return " ".join(part for part in [case.proposer.english_family_name.value, case.proposer.english_given_name.value] if part).strip()


def _ack_values(case: PolicyCase) -> dict[str, object]:
    return {
        "Please tick the box if you agree with the provision use and transfer of your personal data for": "/On",
        "Name of Client": _english_name(case),
        "Name of Introducer": "",
        "ID/ Passport No": case.proposer.id_number.value,
        "Date": _display_date(case.sign_date.value),
        "Video Date": _display_date(case.virtual_meeting_date.value or case.sign_date.value),
        "Name and Licensed No": _tr_name_license(case),
    }


def _risk_values(case: PolicyCase) -> dict[str, object]:
    return {
        "Client": _english_name(case),
        "Nationality": _risk_nationality(case.proposer.nationality.value),
        "Product/Service": _risk_product_service(case),
        "Text4": case.tr_name.value,
    }


def _client_booklet_values(case: PolicyCase) -> dict[str, object]:
    proposer = case.proposer
    insured = case.insured
    fin = case.financial
    products = ", ".join(str(p.name.value) for p in case.products if p.name.value)
    return {
        "income_Monthly Average Salary": _number(fin.monthly_income.value),
        "income_Average Bonus": _number(fin.monthly_unearned_income.value),
        "income_Monthly Average Rental": "0",
        "income_Others": "0",
        "income_Monthly Average Total": _number(_sum_numbers(fin.monthly_income.value, fin.monthly_unearned_income.value)),
        "income_Yearly Average Total": _number(_times_12(_sum_numbers(fin.monthly_income.value, fin.monthly_unearned_income.value))),
        "Expenses_Monthly Average Total": _number(fin.monthly_expenses.value),
        "Expenses_Yearly Average Total": _number(_times_12(fin.monthly_expenses.value)),
        "assets_Cash and Deposits": _number(fin.liquid_assets.value),
        "assets_Fixed": _number(fin.fixed_assets.value),
        "assets_Total": _number(_sum_numbers(fin.liquid_assets.value, fin.fixed_assets.value)),
        "liability_Estimated Total": _number(fin.liabilities.value),
        "Estimated Total Net Worth": _number(fin.net_worth.value),
        "Name of Client": _english_name(case),
        "ID/ Passport No": proposer.id_number.value,
        "Product Name": products,
        "Payment Term": case.products[0].premium_term.value if case.products else "",
        "Appointment Date": _display_date(case.sign_date.value),
        "Name & License": _tr_name_license(case),
        "Client": _english_name(case),
        "Insured": " ".join(part for part in [insured.english_family_name.value, insured.english_given_name.value] if part),
        "Coverage/ Premium": _coverage_premium(case),
        "Nationality": _country_display(proposer.nationality.value),
    }


def _display_date(value: object) -> str:
    if not value:
        return ""
    text = str(value)
    parts = text.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return text


def _times_12(value: object) -> object:
    try:
        return float(value) * 12
    except (TypeError, ValueError):
        return ""


def _sum_numbers(*values: object) -> object:
    total = 0.0
    seen = False
    for value in values:
        try:
            total += float(value)
            seen = True
        except (TypeError, ValueError):
            pass
    return total if seen else ""


def _number(value: object) -> object:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number.is_integer():
        return str(int(number))
    return str(number)


def _country_display(value: object) -> str:
    text = str(value or "")
    if text.lower() == "china" or "中國" in text:
        return "中國"
    return text


def _coverage_premium(case: PolicyCase) -> str:
    main = next((p for p in case.products if p.kind == "basic"), None)
    if not main or not main.sum_assured.value:
        return ""
    currency = str(case.currency.value or "").lower()
    prefix = "us" if currency == "usd" else currency
    amount = _number(main.sum_assured.value)
    try:
        amount = f"{int(float(main.sum_assured.value)):,}"
    except (TypeError, ValueError):
        pass
    return f"保額{prefix}{amount}"


def _tr_name_license(case: PolicyCase) -> str:
    name = str(case.tr_name.value or "").strip()
    license_no = str(case.tr_license_no.value or "").strip()
    if name and license_no:
        return f"{name} ({license_no})"
    return name or license_no


def _risk_nationality(value: object) -> str:
    text = str(value or "")
    if text.lower() == "china" or "中國" in text:
        return "CHINESE"
    return text.upper()


def _risk_product_service(case: PolicyCase) -> str:
    codes = {str(product.code.value or "").upper() for product in case.products}
    names = " ".join(str(product.name.value or "") for product in case.products)
    if "CIM3" in codes or "危疾" in names:
        return "PRU-CI"
    return ", ".join(str(p.name.value) for p in case.products if p.name.value)
