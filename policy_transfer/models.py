from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceRef:
    document: str
    page: int | None = None
    snippet: str = ""


@dataclass
class FieldValue:
    value: Any = ""
    confidence: float = 0.0
    source: SourceRef | None = None
    required: bool = False
    needs_review: bool = False
    note: str = ""


@dataclass
class Person:
    role: str
    english_family_name: FieldValue = field(default_factory=FieldValue)
    english_given_name: FieldValue = field(default_factory=FieldValue)
    chinese_name: FieldValue = field(default_factory=FieldValue)
    date_of_birth: FieldValue = field(default_factory=FieldValue)
    sex: FieldValue = field(default_factory=FieldValue)
    marital_status: FieldValue = field(default_factory=FieldValue)
    nationality: FieldValue = field(default_factory=FieldValue)
    place_of_birth: FieldValue = field(default_factory=FieldValue)
    id_type: FieldValue = field(default_factory=FieldValue)
    id_number: FieldValue = field(default_factory=FieldValue)
    travel_permit_number: FieldValue = field(default_factory=FieldValue)
    phone_country_code: FieldValue = field(default_factory=FieldValue)
    phone: FieldValue = field(default_factory=FieldValue)
    email: FieldValue = field(default_factory=FieldValue)
    residential_address: FieldValue = field(default_factory=FieldValue)
    correspondence_address: FieldValue = field(default_factory=FieldValue)
    employer: FieldValue = field(default_factory=FieldValue)
    business_nature: FieldValue = field(default_factory=FieldValue)
    occupation: FieldValue = field(default_factory=FieldValue)
    business_address: FieldValue = field(default_factory=FieldValue)


@dataclass
class ProductLine:
    kind: str
    name: FieldValue = field(default_factory=FieldValue)
    code: FieldValue = field(default_factory=FieldValue)
    premium_term: FieldValue = field(default_factory=FieldValue)
    benefit_term: FieldValue = field(default_factory=FieldValue)
    sum_assured: FieldValue = field(default_factory=FieldValue)
    modal_premium: FieldValue = field(default_factory=FieldValue)
    ward_level: FieldValue = field(default_factory=FieldValue)
    medical_region: FieldValue = field(default_factory=FieldValue)
    deductible: FieldValue = field(default_factory=FieldValue)
    rider_benefit: FieldValue = field(default_factory=FieldValue)


@dataclass
class FinancialProfile:
    monthly_income: FieldValue = field(default_factory=FieldValue)
    monthly_unearned_income: FieldValue = field(default_factory=FieldValue)
    monthly_expenses: FieldValue = field(default_factory=FieldValue)
    liquid_assets: FieldValue = field(default_factory=FieldValue)
    fixed_assets: FieldValue = field(default_factory=FieldValue)
    liabilities: FieldValue = field(default_factory=FieldValue)
    net_worth: FieldValue = field(default_factory=FieldValue)
    objectives: FieldValue = field(default_factory=FieldValue)
    protection_period: FieldValue = field(default_factory=FieldValue)
    payment_affordability: FieldValue = field(default_factory=FieldValue)
    risk_notes: FieldValue = field(default_factory=FieldValue)


@dataclass
class PolicyCase:
    source_company: FieldValue = field(default_factory=FieldValue)
    proposal_no: FieldValue = field(default_factory=FieldValue)
    billing_no: FieldValue = field(default_factory=FieldValue)
    policy_no: FieldValue = field(default_factory=FieldValue)
    policy_status: FieldValue = field(default_factory=lambda: FieldValue("INFORCE", 0.7))
    sign_date: FieldValue = field(default_factory=FieldValue)
    submission_date: FieldValue = field(default_factory=FieldValue)
    issue_date: FieldValue = field(default_factory=FieldValue)
    policy_date: FieldValue = field(default_factory=FieldValue)
    first_premium_date: FieldValue = field(default_factory=FieldValue)
    next_premium_date: FieldValue = field(default_factory=FieldValue)
    commission_date: FieldValue = field(default_factory=FieldValue)
    cooling_off_end_date: FieldValue = field(default_factory=FieldValue)
    currency: FieldValue = field(default_factory=FieldValue)
    payment_mode: FieldValue = field(default_factory=FieldValue)
    payment_method: FieldValue = field(default_factory=FieldValue)
    total_modal_premium: FieldValue = field(default_factory=FieldValue)
    relationship: FieldValue = field(default_factory=FieldValue)
    broker_company: FieldValue = field(default_factory=FieldValue)
    broker_code: FieldValue = field(default_factory=FieldValue)
    tr_name: FieldValue = field(default_factory=FieldValue)
    tr_code: FieldValue = field(default_factory=FieldValue)
    tr_license_no: FieldValue = field(default_factory=lambda: FieldValue("IA8673", 0.5, None, False, True, "Default from B template; please confirm."))
    virtual_meeting_date: FieldValue = field(default_factory=FieldValue)
    proposer: Person = field(default_factory=lambda: Person(role="proposer"))
    insured: Person = field(default_factory=lambda: Person(role="insured"))
    beneficiary_name: FieldValue = field(default_factory=FieldValue)
    beneficiary_relationship: FieldValue = field(default_factory=FieldValue)
    beneficiary_id_number: FieldValue = field(default_factory=FieldValue)
    beneficiary_share: FieldValue = field(default_factory=lambda: FieldValue("100", 0.6, None, False, True, "Defaulted because no beneficiary was designated."))
    products: list[ProductLine] = field(default_factory=list)
    financial: FinancialProfile = field(default_factory=FinancialProfile)
    review_issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PolicyCase":
        def src(raw: dict[str, Any] | None) -> SourceRef | None:
            if not raw:
                return None
            return SourceRef(**raw)

        def fv(raw: Any) -> FieldValue:
            if isinstance(raw, dict):
                raw = dict(raw)
                raw["source"] = src(raw.get("source"))
                return FieldValue(**raw)
            return FieldValue(raw, 0.5)

        def person(raw: dict[str, Any], role: str) -> Person:
            p = Person(role=raw.get("role", role))
            for key in p.__dataclass_fields__:
                if key != "role" and key in raw:
                    setattr(p, key, fv(raw[key]))
            return p

        def product(raw: dict[str, Any]) -> ProductLine:
            item = ProductLine(kind=raw.get("kind", "rider"))
            for key in item.__dataclass_fields__:
                if key != "kind" and key in raw:
                    setattr(item, key, fv(raw[key]))
            return item

        case = PolicyCase()
        for key in case.__dataclass_fields__:
            if key in {"proposer", "insured", "products", "financial", "review_issues"}:
                continue
            if key in data:
                setattr(case, key, fv(data[key]))
        if not case.virtual_meeting_date.value and case.sign_date.value:
            case.virtual_meeting_date = FieldValue(
                case.sign_date.value,
                0.55,
                case.sign_date.source,
                False,
                True,
                "Virtual meeting date is not explicit in source PDFs; defaulted to sign date for review.",
            )
        case.proposer = person(data.get("proposer", {}), "proposer")
        case.insured = person(data.get("insured", {}), "insured")
        case.products = [product(p) for p in data.get("products", [])]
        fin = FinancialProfile()
        for key in fin.__dataclass_fields__:
            if key in data.get("financial", {}):
                setattr(fin, key, fv(data["financial"][key]))
        case.financial = fin
        case.review_issues = list(data.get("review_issues", []))
        return case


def flatten_case(case: PolicyCase) -> dict[str, FieldValue]:
    flat: dict[str, FieldValue] = {}

    def walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, FieldValue):
            flat[prefix] = obj
            return
        if isinstance(obj, list):
            for idx, item in enumerate(obj):
                walk(f"{prefix}.{idx}" if prefix else str(idx), item)
            return
        if hasattr(obj, "__dataclass_fields__"):
            for key in obj.__dataclass_fields__:
                if key == "role":
                    continue
                value = getattr(obj, key)
                walk(f"{prefix}.{key}" if prefix else key, value)

    walk("", case)
    return flat
