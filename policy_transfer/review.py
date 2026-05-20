from __future__ import annotations

import re
from typing import Any

from policy_transfer.models import FieldValue, PolicyCase, flatten_case


VISIBLE_FIELDS = [
    "source_company",
    "proposal_no",
    "billing_no",
    "policy_no",
    "policy_status",
    "sign_date",
    "submission_date",
    "issue_date",
    "policy_date",
    "first_premium_date",
    "next_premium_date",
    "commission_date",
    "cooling_off_end_date",
    "currency",
    "payment_mode",
    "payment_method",
    "total_modal_premium",
    "relationship",
    "broker_company",
    "tr_name",
    "tr_code",
    "tr_license_no",
    "virtual_meeting_date",
    "proposer.english_family_name",
    "proposer.english_given_name",
    "proposer.chinese_name",
    "proposer.date_of_birth",
    "proposer.sex",
    "proposer.nationality",
    "proposer.id_type",
    "proposer.id_number",
    "proposer.travel_permit_number",
    "proposer.phone_country_code",
    "proposer.phone",
    "proposer.email",
    "proposer.residential_address",
    "proposer.correspondence_address",
    "proposer.employer",
    "proposer.business_nature",
    "proposer.occupation",
    "proposer.business_address",
    "proposer.education_level",
    "insured.english_family_name",
    "insured.english_given_name",
    "insured.chinese_name",
    "insured.date_of_birth",
    "insured.sex",
    "insured.nationality",
    "insured.id_type",
    "insured.id_number",
    "insured.residential_address",
    "financial.monthly_income",
    "financial.monthly_unearned_income",
    "financial.monthly_expenses",
    "financial.liquid_assets",
    "financial.fixed_assets",
    "financial.liabilities",
    "financial.net_worth",
    "financial.objectives",
    "financial.protection_period",
    "financial.payment_affordability",
]

FIELD_SECTIONS: list[tuple[str, str, list[str]]] = [
    (
        "保单资料",
        "Policy",
        [
            "source_company",
            "proposal_no",
            "billing_no",
            "policy_no",
            "policy_status",
            "sign_date",
            "submission_date",
            "issue_date",
            "policy_date",
            "first_premium_date",
            "next_premium_date",
            "commission_date",
            "cooling_off_end_date",
            "currency",
            "payment_mode",
            "payment_method",
            "total_modal_premium",
        ],
    ),
    (
        "投保人资料",
        "Proposer",
        [
            "relationship",
            "proposer.english_family_name",
            "proposer.english_given_name",
            "proposer.chinese_name",
            "proposer.date_of_birth",
            "proposer.sex",
            "proposer.nationality",
            "proposer.id_type",
            "proposer.id_number",
            "proposer.travel_permit_number",
            "proposer.phone_country_code",
            "proposer.phone",
            "proposer.email",
            "proposer.residential_address",
            "proposer.correspondence_address",
            "proposer.employer",
            "proposer.business_nature",
            "proposer.occupation",
            "proposer.business_address",
            "proposer.education_level",
        ],
    ),
    (
        "受保人资料",
        "Insured",
        [
            "insured.english_family_name",
            "insured.english_given_name",
            "insured.chinese_name",
            "insured.date_of_birth",
            "insured.sex",
            "insured.nationality",
            "insured.id_type",
            "insured.id_number",
            "insured.residential_address",
        ],
    ),
    (
        "财务及需要分析",
        "Financial / FNA",
        [
            "financial.monthly_income",
            "financial.monthly_unearned_income",
            "financial.monthly_expenses",
            "financial.liquid_assets",
            "financial.fixed_assets",
            "financial.liabilities",
            "financial.net_worth",
            "financial.objectives",
            "financial.protection_period",
            "financial.payment_affordability",
        ],
    ),
    (
        "业务代表及合规",
        "TR / Compliance",
        [
            "broker_company",
            "tr_name",
            "tr_code",
            "tr_license_no",
            "virtual_meeting_date",
        ],
    ),
]

FIELD_LABELS: dict[str, tuple[str, str, str]] = {
    "source_company": ("来源保险公司", "Source company", "用于选择解析规则，并写入 C 导入表的保险公司信息。"),
    "proposal_no": ("申请书/保单号码", "Proposal / policy number", "用于 B 文件、C 导入表的保单号码。"),
    "billing_no": ("缴费编号", "Billing number", "来源记录字段，方便核对保费资料。"),
    "policy_no": ("保单号码", "Policy number", "C 导入表必填；目前按申请书编号预填。"),
    "policy_status": ("保单状态", "Policy status", "C 导入表必填，默认生效中 INFORCE。"),
    "sign_date": ("签署日期", "Sign date", "用于 B 文件签署日期，也可作为缺失日期的参考。"),
    "submission_date": ("递交日期", "Submission date", "C 导入表日期字段。"),
    "issue_date": ("缮发日期", "Issue date", "C 导入表日期字段；源文件没有时可留空。"),
    "policy_date": ("保单日期", "Policy date", "C 导入表必填，并影响续保提醒；未从 A PDF 明确找到时必须确认。"),
    "first_premium_date": ("首期保费日", "First premium date", "C 导入表续保提醒相关字段；没有可靠来源时请人工确认。"),
    "next_premium_date": ("下期保费日", "Next premium date", "C 导入表续保提醒相关字段；没有可靠来源时可留空或人工确认。"),
    "commission_date": ("合约/计佣日期", "Commission date", "C 导入表必填；没有独立来源时按签署/保单日期确认。"),
    "cooling_off_end_date": ("冷静期结束日期", "Cooling-off end date", "C 导入表非必填日期字段。"),
    "currency": ("保单货币", "Policy currency", "用于 B 文件及 C 导入表。"),
    "payment_mode": ("缴费频率", "Payment frequency", "用于 B 文件及 C 导入表，例如 ANNUALLY。"),
    "payment_method": ("缴费方式", "Payment method", "用于核对保费资料。"),
    "total_modal_premium": ("每期总保费及征费", "Total modal premium and levy", "用于保费核对；若需要拆分主险/附加险，需人工确认。"),
    "relationship": ("投保人与受保人关系", "Relationship to insured", "用于 C 导入表关系字段。"),
    "broker_company": ("原经纪公司", "Broker company", "用于来源核对。"),
    "tr_name": ("业务代表姓名", "Technical representative name", "用于 B 文件签署区、确认书、风险评估表和委任函。"),
    "tr_code": ("业务代表编号", "TR code", "用于来源核对。"),
    "tr_license_no": ("业务代表牌照号码", "Technical representative license no.", "用于 B 文件签署区、确认书、风险评估表和委任函。"),
    "virtual_meeting_date": ("虚拟会议日期", "Virtual meeting date", "用于客户确认书字段 “a virtual meeting held on”。A PDF 未明确提供时默认按签署日期预填，需要人工确认。"),
    "proposer.english_family_name": ("投保人英文姓", "Proposer English family name", "用于 B 文件及 C 导入表。"),
    "proposer.english_given_name": ("投保人英文名", "Proposer English given name", "用于 B 文件及 C 导入表。"),
    "proposer.chinese_name": ("投保人中文姓名", "Proposer Chinese name", "用于 B 文件及 C 导入表。"),
    "proposer.date_of_birth": ("投保人出生日期", "Proposer date of birth", "C 导入表必填。"),
    "proposer.sex": ("投保人性别", "Proposer sex", "C 导入表必填。"),
    "proposer.nationality": ("投保人国籍", "Proposer nationality", "C 导入表必填。"),
    "proposer.id_type": ("投保人证件类型", "Proposer ID type", "用于核对证件信息。"),
    "proposer.id_number": ("投保人证件号码", "Proposer ID number", "B 文件及 C 导入表必填。"),
    "proposer.travel_permit_number": ("投保人通行证号码", "Proposer travel permit number", "用于 C 导入表和客户资料核对。"),
    "proposer.phone_country_code": ("投保人电话区号", "Proposer phone country code", "用于 C 导入表联系方式。"),
    "proposer.phone": ("投保人联系电话", "Proposer phone", "用于 C 导入表联系方式。"),
    "proposer.email": ("投保人电邮", "Proposer email", "用于 C 导入表联系方式。"),
    "proposer.residential_address": ("投保人居住地址", "Proposer residential address", "用于 B 文件及 C 导入表。"),
    "proposer.correspondence_address": ("投保人通讯地址", "Proposer correspondence address", "用于 C 导入表。"),
    "proposer.employer": ("投保人公司名称", "Proposer employer", "用于 B 客户资料手册及 C 导入表。"),
    "proposer.business_nature": ("投保人行业性质", "Proposer business nature", "用于 B 客户资料手册及 C 导入表。"),
    "proposer.occupation": ("投保人职业/职位", "Proposer occupation", "用于 B 客户资料手册及 C 导入表。"),
    "proposer.business_address": ("投保人公司地址", "Proposer business address", "用于 B 客户资料手册及 C 导入表。"),
    "proposer.education_level": ("投保人教育程度", "Proposer education level", "用于 B 客户资料手册 Education Level 勾选。"),
    "insured.english_family_name": ("受保人英文姓", "Insured English family name", "用于 B 文件及 C 导入表。"),
    "insured.english_given_name": ("受保人英文名", "Insured English given name", "用于 B 文件及 C 导入表。"),
    "insured.chinese_name": ("受保人中文姓名", "Insured Chinese name", "用于 B 文件及 C 导入表。"),
    "insured.date_of_birth": ("受保人出生日期", "Insured date of birth", "C 导入表必填。"),
    "insured.sex": ("受保人性别", "Insured sex", "C 导入表必填。"),
    "insured.nationality": ("受保人国籍", "Insured nationality", "C 导入表必填。"),
    "insured.id_type": ("受保人证件类型", "Insured ID type", "用于核对证件信息。"),
    "insured.id_number": ("受保人证件号码", "Insured ID number", "C 导入表必填。"),
    "insured.residential_address": ("受保人居住地址", "Insured residential address", "C 导入表必填。"),
    "financial.monthly_income": ("每月工作收入", "Monthly earned income", "用于 B 客户资料手册。"),
    "financial.monthly_unearned_income": ("每月非工作收入", "Monthly unearned income", "用于 B 客户资料手册。"),
    "financial.monthly_expenses": ("每月支出", "Monthly expenses", "用于 B 客户资料手册。"),
    "financial.liquid_assets": ("流动资产", "Liquid assets", "用于 B 客户资料手册。"),
    "financial.fixed_assets": ("固定资产", "Fixed assets", "用于 B 客户资料手册。"),
    "financial.liabilities": ("负债", "Liabilities", "用于 B 客户资料手册。"),
    "financial.net_worth": ("净资产", "Net worth", "用于 B 客户资料手册。"),
    "financial.objectives": ("投保目标", "Insurance objectives", "用于核对 FNA/客户资料。"),
    "financial.protection_period": ("目标保障期", "Protection period", "用于核对 FNA/客户资料。"),
    "financial.payment_affordability": ("保费承担比例", "Payment affordability", "用于核对 FNA/客户资料。"),
}

PRODUCT_FIELD_LABELS: dict[str, tuple[str, str, str]] = {
    "kind": ("产品类型", "Product type", "区分主险 basic 和附加险 rider。"),
    "name": ("产品名称", "Product name", "用于 B 文件及 C 导入表产品名称。"),
    "code": ("产品代码", "Product code", "用于 C 导入表产品码。"),
    "premium_term": ("缴费年期", "Premium term", "用于 B 文件及 C 导入表。"),
    "benefit_term": ("保障年期", "Benefit term", "用于 B 文件及 C 导入表。"),
    "sum_assured": ("保额", "Sum assured", "用于 B 文件及 C 导入表。"),
    "modal_premium": ("每期保费", "Modal premium", "C 导入表需要；附加险保费若源文件未拆分，必须人工确认。"),
    "ward_level": ("病房等级", "Ward level", "医疗险适用，用于 C 导入表 rider sheet。"),
    "medical_region": ("保障地区", "Medical region", "医疗险适用，用于 C 导入表 rider sheet。"),
    "deductible": ("自付额", "Deductible", "医疗险适用，用于 C 导入表 rider sheet。"),
    "rider_benefit": ("附加保障", "Rider benefit", "医疗险适用，用于 C 导入表 rider sheet。"),
}


def review_rows(case: PolicyCase) -> list[tuple[str, FieldValue]]:
    flat = flatten_case(case)
    rows = [(name, flat[name]) for name in VISIBLE_FIELDS if name in flat]
    for idx, _product in enumerate(case.products):
        prefix = f"products.{idx}"
        for field in [
            "kind",
            "name",
            "code",
            "premium_term",
            "benefit_term",
            "sum_assured",
            "modal_premium",
            "ward_level",
            "medical_region",
            "deductible",
            "rider_benefit",
        ]:
            name = f"{prefix}.{field}"
            if name in flat:
                rows.append((name, flat[name]))
    return rows


def review_sections(case: PolicyCase) -> list[tuple[str, str, list[tuple[str, FieldValue]]]]:
    flat = flatten_case(case)
    sections: list[tuple[str, str, list[tuple[str, FieldValue]]]] = []
    used: set[str] = set()
    for zh, en, fields in FIELD_SECTIONS:
        rows = [(name, flat[name]) for name in fields if name in flat]
        used.update(name for name, _field in rows)
        sections.append((zh, en, rows))

    product_rows: list[tuple[str, FieldValue]] = []
    for idx, _product in enumerate(case.products):
        prefix = f"products.{idx}"
        for field in [
            "kind",
            "name",
            "code",
            "premium_term",
            "benefit_term",
            "sum_assured",
            "modal_premium",
            "ward_level",
            "medical_region",
            "deductible",
            "rider_benefit",
        ]:
            name = f"{prefix}.{field}"
            if name in flat:
                product_rows.append((name, flat[name]))
                used.add(name)
    sections.append(("产品资料", "Products", product_rows))

    return sections


def field_label(path: str) -> str:
    zh, en, _usage = field_meta(path)
    return f"{zh}<br><span class='en'>{en}</span>"


def field_usage(path: str) -> str:
    _zh, _en, usage = field_meta(path)
    return usage


def field_meta(path: str) -> tuple[str, str, str]:
    if path in FIELD_LABELS:
        return FIELD_LABELS[path]
    parts = path.split(".")
    if len(parts) >= 3 and parts[0] == "products" and parts[1].isdigit():
        label = PRODUCT_FIELD_LABELS.get(parts[2])
        if label:
            number = int(parts[1]) + 1
            zh, en, usage = label
            return (f"产品{number} - {zh}", f"Product {number} - {en}", usage)
    return (path, path, "内部字段；用于生成 B 文件或 C 导入表。")


def translated_issue(issue: str) -> str:
    for marker in [" needs review", " is required but missing"]:
        if marker in issue:
            path = _normalize_issue_path(issue.split(marker, 1)[0])
            zh, en, usage = field_meta(path)
            if "required" in marker:
                return f"{zh} / {en}：必填但缺失。用途：{usage}"
            tail = issue.split(marker, 1)[1].lstrip(": ").strip()
            extra = f" 原因：{_translate_note(tail)}" if tail and tail != "." else ""
            return f"{zh} / {en}：需要人工确认。用途：{usage}{extra}"
    return issue


def _normalize_issue_path(path: str) -> str:
    return re.sub(r"products\[(\d+)\]\.", r"products.\1.", path)


def _translate_note(note: str) -> str:
    if "Policy date not found" in note:
        return "A PDF 未明确找到保单日期，暂用签署日期预填。"
    if "low confidence" in note:
        return "系统置信度较低。"
    return note


def apply_updates(case: PolicyCase, updates: dict[str, str]) -> PolicyCase:
    for path, value in updates.items():
        if not path.startswith("field:"):
            continue
        target_path = path.removeprefix("field:")
        field_value = _get(case, target_path)
        if isinstance(field_value, FieldValue):
            field_value.value = _coerce(value)
            field_value.confidence = max(field_value.confidence, 0.99)
            field_value.needs_review = False
            field_value.note = "Confirmed in review UI."
    case.review_issues = []
    for name, field_value in review_rows(case):
        if field_value.required and not field_value.value:
            case.review_issues.append(f"{name} is required but missing.")
        elif field_value.needs_review:
            case.review_issues.append(f"{name} needs review.")
    return case


def _get(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if part.isdigit():
            current = current[int(part)]
        else:
            current = getattr(current, part)
    return current


def _coerce(value: str) -> object:
    stripped = value.strip()
    if stripped == "":
        return ""
    lowered = stripped.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped
