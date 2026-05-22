from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from policy_transfer.extractors.base import ExtractionInput
from policy_transfer.models import FieldValue, FinancialProfile, Person, PolicyCase, ProductLine, SourceRef


@dataclass
class PageText:
    document: str
    page: int
    text: str


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def money_to_float(value: str) -> float | str:
    value = value.replace(",", "").replace("$", "").strip()
    try:
        return float(value)
    except ValueError:
        return value


def fv(value: object, confidence: float, page: PageText | None = None, snippet: str = "", required: bool = False, note: str = "") -> FieldValue:
    return FieldValue(
        value=value,
        confidence=confidence,
        source=SourceRef(page.document, page.page, snippet[:220]) if page else None,
        required=required,
        needs_review=confidence < 0.85 or (required and (value is None or value == "")),
        note=note,
    )


class PrudentialExtractor:
    company_key = "prudential"
    display_name = "Prudential Hong Kong Limited / 保誠"

    def matches(self, files: list[ExtractionInput]) -> bool:
        sample_pages: list[str] = []
        for item in files:
            if not item.filename.lower().endswith(".pdf"):
                continue
            reader = PdfReader(BytesIO(item.content))
            for page in reader.pages[:6]:
                sample_pages.append(clean_text(page.extract_text() or ""))
        sample = "\n".join(sample_pages)
        compact_sample = compact(sample)
        return any(
            marker in sample or marker in compact_sample
            for marker in [
                "Prudential Hong Kong Limited",
                "保誠保險有限公司",
                "Proposal for Assurance",
                "保單內容",
                "保 單 內 容",
            ]
        )

    def extract(self, files: list[ExtractionInput]) -> PolicyCase:
        pages = self._pages(files)
        joined = "\n".join(page.text for page in pages)
        one_line = compact(joined)

        case = PolicyCase()
        company_page = self._first_company_page(pages)
        case.source_company = fv("PRUDENTIAL", 0.98, company_page, self._company_snippet(company_page), True)
        case.broker_company = self._regex_value(pages, r"Company Name公司姓名 Code編號 Division組別\s+(.+?)\s+([A-Z]\d{4})\s+([A-Z]\d{4})", group=1)
        case.broker_code = self._regex_value(pages, r"Company Name公司姓名 Code編號 Division組別\s+(.+?)\s+([A-Z]\d{4})\s+([A-Z]\d{4})", group=2)
        case.tr_name = self._regex_value(pages, r"Technical Representative Full Name.*?\n([A-Z ]+?)\s+(\d{8})\s+", group=1)
        case.tr_code = self._regex_value(pages, r"Technical Representative Full Name.*?\n([A-Z ]+?)\s+(\d{8})\s+", group=2)
        case.tr_license_no = self._regex_value(pages, r"Licensed Technical Representative.*?-\s*([A-Z]{1,4}[0-9]{3,8})")
        case.proposal_no = self._regex_value(pages, r"Proposal No\.申請書編號\s+(\d+)", required=True)
        case.billing_no = self._regex_value(pages, r"Billing No\.繳費編號\s+(BN\d+)")
        case.policy_no = case.proposal_no
        case.relationship = self._regex_value(pages, r"Relationship of Proposer with Life Proposed\s*投保人與受保人之關係\s*([^\n]+)")
        insured_same_as_proposer = self._insured_same_as_proposer(pages)
        if insured_same_as_proposer and not case.relationship.value:
            case.relationship = fv("SELF", 0.95, insured_same_as_proposer, insured_same_as_proposer.text)
        case.currency = self._regex_value(pages, r"Currency保單貨幣\s+(.+?)(?:\n| Basic Plan)", transform=self._currency_code, required=True)
        case.payment_mode = self._regex_value(pages, r"Payment Mode繳費方式\s+(.+?)(?:\n| Payment Method)", transform=self._payment_mode, required=True)
        case.payment_method = self._regex_value(pages, r"Payment Method繳費方法\s+(.+?)(?:\n| \*)")
        case.total_modal_premium = self._regex_value(pages, r"Total Modal Premium and Levy.*?\*\s*([0-9,]+(?:\.\d+)?)", transform=money_to_float, required=True)
        case.first_premium_date = fv("", 0.0, None, "", False, "Not found in source PDFs; please confirm if required.")
        case.next_premium_date = fv("", 0.0, None, "", False, "Not found in source PDFs; please confirm if required.")

        case.insured = self._extract_person(pages, "Life Proposed Personal Details", "insured")
        if insured_same_as_proposer:
            case.proposer = self._extract_first_person(
                pages,
                [
                    "Life Proposed & Proposer Personal Details",
                    "Life Proposed and Proposer Personal Details",
                    "Proposer Personal Details",
                ],
                "proposer",
            )
        else:
            case.proposer = self._extract_person(pages, "Proposer Personal Details", "proposer")
        case.sign_date = self._extract_sign_date(pages, case)
        case.submission_date = case.sign_date
        case.commission_date = case.sign_date
        case.virtual_meeting_date = fv("", 0.0, None, "", False, "Transfer meeting date is intentionally left blank for TR completion.")
        case.policy_date = fv(case.sign_date.value, 0.55, case.sign_date.source and PageText(case.sign_date.source.document, case.sign_date.source.page or 0, ""), "", True, "Policy date not found in PDFs; defaulted to sign date for review.")
        self._add_contact_and_identity(pages, case)
        if insured_same_as_proposer and not self._has_person_identity(case.insured):
            self._copy_proposer_to_insured(case)
        case.products = self._extract_products(pages, case)
        case.financial = self._extract_financial(pages)
        self._apply_epolicy_policy_content(case, pages)
        case.review_issues = self._build_review_issues(case)
        return case

    def _pages(self, files: list[ExtractionInput]) -> list[PageText]:
        pages: list[PageText] = []
        for item in files:
            if not item.filename.lower().endswith(".pdf"):
                continue
            reader = PdfReader(BytesIO(item.content))
            for idx, page in enumerate(reader.pages, start=1):
                pages.append(PageText(item.filename, idx, clean_text(page.extract_text() or "")))
        return pages

    def _extract_pdf_pages(self, files: list[ExtractionInput]) -> list[str]:
        return [page.text for page in self._pages(files)]

    def _first_page(self, pages: list[PageText]) -> PageText | None:
        return pages[0] if pages else None

    def _insured_same_as_proposer(self, pages: list[PageText]) -> PageText | None:
        patterns = [
            r"Is the Proposer the same as Life Proposed\?\s*投保人是否受保人\?\s*(?:Yes|是)",
            r"(?:投保人是否(?:為|是)?受保人|受保人是否.*?投保人|Proposer.*?(?:same|also).*?(?:Life Proposed|Insured)).{0,80}(?:Yes|是)",
            r"(?:Life Proposed|Insured).*?(?:same as|same).*?(?:Proposer|Policyowner).{0,80}(?:Yes|是)",
        ]
        for page in pages:
            text = compact(page.text)
            if any(re.search(pattern, text, re.I) for pattern in patterns):
                return page
        return None

    def _has_person_identity(self, person: Person) -> bool:
        return any(
            str(getattr(person, field).value or "").strip()
            for field in ("english_family_name", "english_given_name", "chinese_name", "date_of_birth", "id_number")
        )

    def _copy_proposer_to_insured(self, case: PolicyCase) -> None:
        case.insured.role = "insured"
        for field in case.insured.__dataclass_fields__:
            if field == "role":
                continue
            setattr(case.insured, field, deepcopy(getattr(case.proposer, field)))

    def _first_company_page(self, pages: list[PageText]) -> PageText | None:
        for page in pages:
            text = self._squash(page.text)
            if "PrudentialHongKongLimited" in text or "保誠保險有限公司" in text or "保單內容" in text:
                return page
        return self._first_page(pages)

    def _company_snippet(self, page: PageText | None) -> str:
        if not page:
            return "PRUDENTIAL"
        if "保 單 內 容" in page.text or "保單內容" in self._squash(page.text):
            return page.text[:500]
        for marker in ["Prudential Hong Kong Limited", "保誠保險有限公司"]:
            index = page.text.find(marker)
            if index >= 0:
                return page.text[max(0, index - 80) : index + 220]
        return page.text[:500]

    def _regex_value(self, pages: list[PageText], pattern: str, group: int = 1, transform=None, required: bool = False) -> FieldValue:
        flags = re.S | re.I
        for page in pages:
            match = re.search(pattern, page.text, flags)
            if match:
                raw = compact(match.group(group))
                value = transform(raw) if transform else raw
                return fv(value, 0.94, page, match.group(0), required)
        return fv("", 0.0, None, "", required, "Not found in source.")

    def _extract_person(self, pages: list[PageText], heading: str, role: str) -> Person:
        person = Person(role=role)
        pattern = (
            re.escape(heading)
            + r".*?Family Name姓\s+([^\n]+?)\s+Given Name名\s+([^\n]+?)\s+Name in Chinese中文姓名\s+([^\n]+?)\s+"
            + r"Date of Birth.*?(\d{2}/\d{2}/\d{4}).*?Sex性別\s+(.+?)\s+Marital Status婚姻狀況\s+(.+?)\s+"
            + r"Passport / ID Document.*?(.+?)\s+Place of Birth出生地\s+(.+?)(?:\n|LAXX)"
        )
        for page in pages:
            match = re.search(pattern, page.text, re.S | re.I)
            if not match:
                continue
            person.english_family_name = fv(compact(match.group(1)), 0.95, page, match.group(0), True)
            person.english_given_name = fv(compact(match.group(2)), 0.95, page, match.group(0), True)
            person.chinese_name = fv(compact(match.group(3)), 0.93, page, match.group(0), True)
            person.date_of_birth = fv(self._date_to_iso(match.group(4)), 0.95, page, match.group(0), True)
            person.sex = fv(self._sex_code(match.group(5)), 0.94, page, match.group(0), True)
            person.marital_status = fv(compact(match.group(6)), 0.9, page, match.group(0))
            person.nationality = fv(self._country_code(match.group(7)), 0.9, page, match.group(0), True)
            person.place_of_birth = fv(self._country_code(match.group(8)), 0.88, page, match.group(0))
            return person
        person.english_family_name = fv("", 0.0, None, "", True)
        person.english_given_name = fv("", 0.0, None, "", True)
        return person

    def _extract_first_person(self, pages: list[PageText], headings: list[str], role: str) -> Person:
        for heading in headings:
            person = self._extract_person(pages, heading, role)
            if self._has_person_identity(person):
                return person
        return Person(role=role, english_family_name=fv("", 0.0, None, "", True), english_given_name=fv("", 0.0, None, "", True))

    def _add_contact_and_identity(self, pages: list[PageText], case: PolicyCase) -> None:
        all_text = "\n".join(page.text for page in pages)
        # Insured identity appears before proposer identity in the sample.
        insured_id = re.search(r"ID Type身份證明文件類別\s+(.+?Certificate.*?)\s+ID No\.身份證明文件號碼\s+([A-Z0-9]+)", all_text, re.S)
        if insured_id:
            page = self._page_for(pages, insured_id.group(0))
            case.insured.id_type = fv(compact(insured_id.group(1)), 0.9, page, insured_id.group(0), True)
            case.insured.id_number = fv(compact(insured_id.group(2)), 0.96, page, insured_id.group(0), True)
        proposer_id = re.search(r"ID Type身份證明文件類別?\s+China ID.*?ID No\.身份證明文件號碼\s+([0-9A-Z]+).*?ID Type身份證明文件類\s+China Exit-Entry Permit.*?ID No\.身份證明文件號碼\s+([0-9A-Z]+)", all_text, re.S)
        if proposer_id:
            page = self._page_for(pages, proposer_id.group(0))
            case.proposer.id_type = fv("China ID", 0.95, page, proposer_id.group(0), True)
            case.proposer.id_number = fv(compact(proposer_id.group(1)), 0.98, page, proposer_id.group(0), True)
            case.proposer.travel_permit_number = fv(compact(proposer_id.group(2)), 0.95, page, proposer_id.group(0))

        proposer_segment = self._section_after_any(
            all_text,
            [
                "Proposer Personal Details投保人個人資料",
                "Life Proposed & Proposer Personal Details受保人及投保人個人資料",
                "Life Proposed and Proposer Personal Details受保人及投保人個人資料",
            ],
        )
        occupation = re.search(
            r"Occupation Details職業詳情\s+Name of Employer僱主名稱\s+(.+?)\s+Business Nature業務性質\s+(.+?)\s+Occupation & Duties職業及工作性質\s+(.+?)\s+Business Address公司地址\s+(.+?)\s+Address and Contact Information",
            proposer_segment,
            re.S,
        )
        if occupation:
            page = self._page_for(pages, occupation.group(0))
            case.proposer.employer = fv(compact(occupation.group(1)), 0.94, page, occupation.group(0))
            case.proposer.business_nature = fv(compact(occupation.group(2)), 0.94, page, occupation.group(0))
            case.proposer.occupation = fv(self._occupation_title(occupation.group(3)), 0.94, page, occupation.group(0))
            case.proposer.business_address = fv(compact(occupation.group(4)), 0.9, page, occupation.group(0))

        contact = re.search(
            r"Address and Contact Information\s*地址及聯絡資料.*?Residential Address居住地址\s+(.+?)\s+Mobile No\.手提電話\s+(?:\(China\)\s*86-([0-9]+)|N/A\s+不適用)\s+Residential No.*?E-mail Address電郵地址\s+([^\n]+)",
            proposer_segment,
            re.S,
        )
        if contact:
            page = self._page_for(pages, contact.group(0))
            case.proposer.residential_address = fv(compact(contact.group(1)), 0.92, page, contact.group(0), True)
            case.proposer.correspondence_address = case.proposer.residential_address
            if contact.group(2):
                case.proposer.phone_country_code = fv("86", 0.98, page, contact.group(0))
                case.proposer.phone = fv(compact(contact.group(2)), 0.98, page, contact.group(0))
            email = compact(contact.group(3))
            if not email.startswith("N/A"):
                case.proposer.email = fv(email, 0.98, page, contact.group(0))

        education = re.search(r"Education Level\s*教育程度\s+(.+?)\s+\*?Are you holding", all_text, re.S | re.I)
        if education:
            page = self._page_for(pages, education.group(0))
            case.proposer.education_level = fv(compact(education.group(1)), 0.94, page, education.group(0))

        insured_address = re.search(r"Residential Address居住地址\s+(.+?)\s+Mobile No\.手提電話\s+N/A", all_text, re.S)
        if insured_address:
            page = self._page_for(pages, insured_address.group(0))
            case.insured.residential_address = fv(compact(insured_address.group(1)), 0.88, page, insured_address.group(0), True)
            case.insured.correspondence_address = case.insured.residential_address

    def _section_after(self, text: str, marker: str) -> str:
        index = text.find(marker)
        return text[index:] if index >= 0 else text

    def _section_after_any(self, text: str, markers: list[str]) -> str:
        indexes = [text.find(marker) for marker in markers]
        indexes = [index for index in indexes if index >= 0]
        return text[min(indexes) :] if indexes else text

    def _occupation_title(self, value: str) -> str:
        text = compact(value)
        text = re.sub(r"^Profession\s+專業人士\s*", "", text, flags=re.I)
        chinese_parts = re.findall(r"[\u3400-\u9fff]+", text)
        return chinese_parts[-1] if chinese_parts else text

    def _extract_products(self, pages: list[PageText], case: PolicyCase) -> list[ProductLine]:
        assurance_pages = [page for page in pages if "Details of Assurance保險計劃詳情" in page.text or "Premium Payment Details保費資料詳情" in page.text]
        text = "\n".join(page.text for page in (assurance_pages or pages))
        products: list[ProductLine] = []
        basic = re.search(r"Basic Plan基本計劃.*?\n([「].+?\([A-Z0-9]+\))\s+([0-9]+)\s+(\S+)\s+([0-9,]+(?:\.\d+)?)", text, re.S)
        if basic:
            page = self._page_for(pages, basic.group(0))
            product = ProductLine("basic")
            product.name = fv(compact(basic.group(1).split("(")[0]), 0.9, page, basic.group(0), True)
            product.code = fv(basic.group(1).split("(")[-1].replace(")", "").strip(), 0.9, page, basic.group(0))
            product.premium_term = fv(compact(basic.group(2)), 0.95, page, basic.group(0), True)
            product.benefit_term = fv(compact(basic.group(3)), 0.9, page, basic.group(0))
            product.sum_assured = fv(money_to_float(basic.group(4)), 0.95, page, basic.group(0), True)
            product.modal_premium = fv("", 0.0, None, "", True, "Source PDF only contains total modal premium; split premium must be confirmed.")
            products.append(product)
        rider = re.search(r"Riders附加契約.*?\n(.+?\([A-Z0-9]+\).*?)(?:LAXX|Premium Payment Details)", text, re.S)
        if rider:
            page = self._page_for(pages, rider.group(0))
            product = ProductLine("rider")
            block = compact(rider.group(1))
            product.name = fv("終身保醫療計劃", 0.85, page, rider.group(0), True)
            product.code = fv("MLP", 0.9, page, rider.group(0))
            product.premium_term = fv("WL", 0.82, page, rider.group(0), True)
            product.benefit_term = fv("WL", 0.82, page, rider.group(0))
            product.sum_assured = fv("N/A", 0.86, page, rider.group(0), True)
            product.ward_level = fv("WARD" if "普通病房" in block else "", 0.86, page, rider.group(0))
            product.rider_benefit = fv("SMM" if "附加額外醫療" in block else "", 0.84, page, rider.group(0))
            product.modal_premium = fv("", 0.0, None, "", True, "Source PDF only contains total modal premium; split rider premium must be confirmed.")
            products.append(product)
        if products and case.total_modal_premium.value and not products[0].modal_premium.value:
            products[0].modal_premium = fv(case.total_modal_premium.value, 0.55, case.total_modal_premium.source and PageText(case.total_modal_premium.source.document, case.total_modal_premium.source.page or 0, ""), "", True, "Temporarily assigned total premium to basic plan; confirm split before import.")
        return products

    def _apply_epolicy_policy_content(self, case: PolicyCase, pages: list[PageText]) -> None:
        policy_page = next((page for page in pages if "保單內容" in self._squash(page.text) and "保單生效日" in self._squash(page.text)), None)
        if not policy_page:
            return
        text = policy_page.text
        compact_text = self._squash(text)

        policy_no = re.search(r"保單號碼([0-9]+)", compact_text)
        if policy_no:
            official_no = compact(policy_no.group(1))
            case.policy_no = fv(official_no, 0.98, policy_page, text, True)
            if not case.proposal_no.value:
                case.proposal_no = fv(official_no, 0.9, policy_page, text, True)

        billing_no = re.search(r"繳費編號(BN[0-9]+)", compact_text)
        if billing_no:
            case.billing_no = fv(compact(billing_no.group(1)), 0.98, policy_page, text)

        policy_date = re.search(r"保單生效日([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)", compact_text)
        if policy_date:
            case.policy_date = fv(self._chinese_date_to_iso(policy_date.group(1)), 0.98, policy_page, text, True)

        first_premium_date = re.search(r"首期保費日([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)", compact_text)
        if first_premium_date:
            case.first_premium_date = fv(self._chinese_date_to_iso(first_premium_date.group(1)), 0.98, policy_page, text)

        payment_mode = re.search(r"每年繳費形式(.+?)(?:貨幣|受保人|保障及保費細則)", compact_text)
        if payment_mode:
            case.payment_mode = fv(self._payment_mode(payment_mode.group(1)), 0.96, policy_page, text, True)

        currency = re.search(r"貨幣(.+?)(?:受保人|保障及保費細則)", compact_text)
        if currency:
            case.currency = fv(self._currency_code(currency.group(1)), 0.96, policy_page, text, True)

        total_premium = re.search(r"每期保費總額([0-9,]+(?:\.\d+)?)", compact_text)
        if total_premium:
            case.total_modal_premium = fv(money_to_float(total_premium.group(1)), 0.98, policy_page, text, True)

        for product in case.products:
            product_name = self._squash(str(product.name.value or ""))
            if not product_name:
                continue
            match = re.search(re.escape(product_name) + r".{0,180}?([0-9,]+\.\d{1,2})", compact_text)
            if match:
                product.modal_premium = fv(money_to_float(match.group(1)), 0.98, policy_page, text, True)

    def _extract_financial(self, pages: list[PageText]) -> FinancialProfile:
        fin = FinancialProfile()
        fin.monthly_income = self._regex_value(pages, r"5\.\(ai\) Monthly Earned Income.*?Total not less than\s*總數不少於\s*HKD 港元\s+([0-9,]+(?:\.\d+)?)", transform=money_to_float)
        fin.monthly_unearned_income = self._regex_value(pages, r"5\.\(aiii\) Monthly Unearned Income.*?Total not less than\s*總數不少於\s*HKD 港元\s+([0-9,]+(?:\.\d+)?)", transform=money_to_float)
        fin.liquid_assets = self._regex_value(pages, r"5\.\(b\) What is the approximate value.*?Total not less than\s*總數不少於\s*HKD 港元\s+([0-9,]+(?:\.\d+)?)", transform=money_to_float)
        fin.fixed_assets = self._regex_value(pages, r"5\.\(c\) What is the approximate value.*?Total not less than\s*總數不少於\s*HKD 港元\s+([0-9,]+(?:\.\d+)?)", transform=money_to_float)
        fin.monthly_expenses = self._regex_value(pages, r"5\.\(d\) What is Proposer.*?average\s+monthly expenses.*?Total about\s*總數大約\s*HKD 港元\s+([0-9,]+(?:\.\d+)?)", transform=money_to_float)
        fin.liabilities = self._regex_value(pages, r"5\.\(e\) What is the approximate amount.*?existing liabilities.*?Total about\s*總數大約\s*HKD 港元\s+([0-9,]+(?:\.\d+)?)", transform=money_to_float)
        try:
            fin.net_worth = fv(float(fin.liquid_assets.value or 0) + float(fin.fixed_assets.value or 0) - float(fin.liabilities.value or 0), 0.88, fin.liquid_assets.source and PageText(fin.liquid_assets.source.document, fin.liquid_assets.source.page or 0, ""), "", False)
        except (TypeError, ValueError):
            fin.net_worth = fv("", 0.0)
        fin.objectives = self._regex_value(pages, r"What is Proposer.*?objective.*?\?.*?(\nFinancial protection.*?Saving up for the future.*?)2\.\(a\)", transform=lambda v: compact(v))
        fin.protection_period = self._regex_value(pages, r"target benefit /.*?protection period.*?\n(Whole of Life 終身)")
        fin.payment_affordability = self._regex_value(pages, r"Monthly disposable income.*?\n([0-9]+ - [0-9]+ %)")
        return fin

    def _page_for(self, pages: list[PageText], snippet: str) -> PageText | None:
        part = compact(snippet)[:80]
        for page in pages:
            if part and part in compact(page.text):
                return page
        return pages[0] if pages else None

    def _extract_sign_date(self, pages: list[PageText], case: PolicyCase) -> FieldValue:
        names = [
            self._full_english_name(case.proposer),
            str(case.proposer.chinese_name.value or ""),
        ]
        for name in names:
            if name:
                value = self._last_date_after_name(pages, name)
                if value.value:
                    return value
        value = self._date_near_signature_name(pages)
        if value.value:
            return value
        return fv("", 0.0)

    def _last_date_after_name(self, pages: list[PageText], name: str) -> FieldValue:
        for page in reversed(pages):
            if name not in page.text:
                continue
            dates = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", page.text)
            if dates:
                return fv(self._date_to_iso(dates[-1]), 0.82, page, page.text[-500:])
        return fv("", 0.0)

    def _date_near_signature_name(self, pages: list[PageText]) -> FieldValue:
        for page in reversed(pages):
            if "Sign Date" not in page.text or "Name 姓名" not in page.text:
                continue
            dates = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", page.text)
            if dates:
                return fv(self._date_to_iso(dates[-1]), 0.7, page, page.text[-500:], False, "Fallback date from signature page; please confirm.")
        return fv("", 0.0)

    def _full_english_name(self, person: Person) -> str:
        parts = [str(person.english_family_name.value or "").strip(), str(person.english_given_name.value or "").strip()]
        return " ".join(part for part in parts if part)

    def _build_review_issues(self, case: PolicyCase) -> list[str]:
        issues: list[str] = []
        required = {
            "proposal_no": case.proposal_no,
            "currency": case.currency,
            "payment_mode": case.payment_mode,
            "proposer.id_number": case.proposer.id_number,
            "insured.id_number": case.insured.id_number,
            "policy_date": case.policy_date,
        }
        for key, field_value in required.items():
            if not field_value.value:
                issues.append(f"{key} is required but missing.")
            elif field_value.needs_review:
                issues.append(f"{key} needs review: {field_value.note or 'low confidence'}")
        for idx, product in enumerate(case.products):
            if not product.modal_premium.value:
                issues.append(f"products[{idx}].modal_premium needs review.")
        return issues

    def _date_to_iso(self, value: str) -> str:
        match = re.search(r"(\d{2})/(\d{2})/(\d{4})", value)
        if not match:
            return value
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    def _chinese_date_to_iso(self, value: str) -> str:
        match = re.search(r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日", self._squash(value))
        if not match:
            return value
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    def _squash(self, value: str) -> str:
        return re.sub(r"\s+", "", clean_text(value))

    def _currency_code(self, value: str) -> str:
        if "United States" in value or "美元" in value:
            return "USD"
        if "Hong Kong" in value or "港元" in value:
            return "HKD"
        return compact(value)

    def _payment_mode(self, value: str) -> str:
        if "Annually" in value or "每年" in value or "年繳" in value:
            return "ANNUALLY"
        if "Monthly" in value or "每月" in value:
            return "MONTHLY"
        return compact(value).upper()

    def _sex_code(self, value: str) -> str:
        if "Female" in value or "女" in value:
            return "FEMALE"
        if "Male" in value or "男" in value:
            return "MALE"
        return compact(value)

    def _country_code(self, value: str) -> str:
        if "China" in value or "中國" in value:
            return "China"
        return compact(value)
