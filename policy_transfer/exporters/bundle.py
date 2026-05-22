from __future__ import annotations

import json
import re
from pathlib import Path

from policy_transfer.config import B_ACK, B_CLIENT_BOOKLET, B_RISK, B_SERVICE_DOCX, DEFAULT_C_TEMPLATE
from policy_transfer.exporters.docx_export import export_service_appointment
from policy_transfer.exporters.excel_export import export_policy_import
from policy_transfer.exporters.pdf_forms import add_diagonal_line_marks, fill_pdf_form, normalize_page_numbers
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
    fill_pdf_form(B_CLIENT_BOOKLET, files["client_booklet"], _client_booklet_values(case), clear_unmapped=True)
    add_diagonal_line_marks(files["client_booklet"], first_page=6, last_page=12)
    normalize_page_numbers(files["client_booklet"], skip_first_page=True)
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
        "Date": "",
        "Video Date": "",
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
    proposer_chinese = _split_chinese_name(proposer.chinese_name.value)
    insured_chinese = _split_chinese_name(insured.chinese_name.value)
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
        "assets_Others liquid": "0",
        "assets_Estimated Total Liquid": _number(fin.liquid_assets.value),
        "assets_Fixed": _number(fin.fixed_assets.value),
        "assets_Total": _number(_sum_numbers(fin.liquid_assets.value, fin.fixed_assets.value)),
        "liability_Estimated Total": _number(fin.liabilities.value),
        "Estimated Total Net Worth": _number(fin.net_worth.value),
        "Name of Client": _english_name(case),
        "ID/ Passport No": proposer.id_number.value,
        "Product Name": products,
        "Payment Term": case.products[0].premium_term.value if case.products else "",
        "Dropdown_fna1": products,
        "Dropdown_fna1-1": case.products[0].premium_term.value if case.products else "",
        "Appointment Date": "",
        "Name & License": _tr_name_license(case),
        "Client": _english_name(case),
        "Insured": " ".join(part for part in [insured.english_family_name.value, insured.english_given_name.value] if part),
        "Coverage/ Premium": _coverage_premium(case),
        "Nationality": _country_display(proposer.nationality.value),
        "Fullname": _english_name(case),
        "Surname": proposer.english_family_name.value,
        "Given Name": proposer.english_given_name.value,
        "Surname_C": proposer_chinese[0],
        "Given Name_C": proposer_chinese[1],
        "Date of Birth": _display_date(proposer.date_of_birth.value),
        "Residential Address": proposer.residential_address.value,
        "Mobile": _phone(proposer.phone_country_code.value, proposer.phone.value),
        "Email": proposer.email.value,
        "Identity": proposer.id_number.value,
        "Place of Birth": _country_display(proposer.place_of_birth.value),
        "fill_6-1": _country_display(proposer.nationality.value),
        "fill_7-1": proposer.id_number.value,
        "Occupation 職業": proposer.occupation.value,
        "Nature of Business 業務性質": proposer.business_nature.value,
        "company name 公司名字": proposer.employer.value,
        "company address 公司地址": proposer.business_address.value or proposer.residential_address.value,
        "Education": _education_choice(proposer.education_level.value),
        "Group1": _title_choice(proposer.sex.value),
        "Group2": _sex_choice(proposer.sex.value),
        "Marital Status": _marital_choice(proposer.marital_status.value),
        "Surname_2": insured.english_family_name.value,
        "Given Name_2": insured.english_given_name.value,
        "Surname_C2": insured_chinese[0],
        "Given Name_C2": insured_chinese[1],
        "DOB_2": _display_date(insured.date_of_birth.value),
        "Residential Address_2": insured.residential_address.value,
        "Nationality_2": _country_display(insured.nationality.value),
        "Identification_2": insured.id_number.value,
        "Place of Birth2": insured.place_of_birth.value,
        "Group8": _insured_sex_choice(insured.sex.value),
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


def _phone(country_code: object, phone: object) -> str:
    parts = [str(country_code or "").strip(), str(phone or "").strip()]
    return "-".join(part for part in parts if part)


def _split_chinese_name(value: object) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    if len(text) == 1:
        return text, ""
    return text[:1], text[1:]


def _title_choice(sex: object) -> str:
    text = str(sex or "").upper()
    if "F" in text or "女" in text:
        return "/Choice3"
    if "M" in text or "男" in text:
        return "/Choice1"
    return ""


def _sex_choice(sex: object) -> str:
    text = str(sex or "").upper()
    if "F" in text or "女" in text:
        return "/Choice2"
    if "M" in text or "男" in text:
        return "/Choice1"
    return ""


def _insured_sex_choice(sex: object) -> str:
    text = str(sex or "").upper()
    if "M" in text or "男" in text:
        return "/Choice1"
    if "F" in text or "女" in text:
        return "/2"
    return ""


def _marital_choice(value: object) -> str:
    text = str(value or "").lower()
    if "single" in text or "未婚" in text:
        return "/Choice1"
    if "married" in text or "已婚" in text:
        return "/Choice2"
    if "divorc" in text or "離婚" in text:
        return "/Choice3"
    if "separat" in text or "分居" in text:
        return "/Choice4"
    return ""


def _education_choice(value: object) -> str:
    text = str(value or "").lower()
    if "primary" in text or "小學" in text:
        return "/Choice1"
    if "secondary" in text or "advance" in text or "中學" in text or "預科" in text:
        return "/Choice2"
    if "tertiary" in text or "university" in text or "大專" in text or "大學" in text:
        return "/Choice3"
    if text:
        return "/Choice4"
    return ""


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
