from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from policy_transfer.models import PolicyCase


@dataclass
class ExtractionInput:
    filename: str
    content: bytes


class Extractor(Protocol):
    company_key: str
    display_name: str

    def matches(self, files: list[ExtractionInput]) -> bool:
        ...

    def extract(self, files: list[ExtractionInput]) -> PolicyCase:
        ...


def detect_extractor(files: list[ExtractionInput]) -> Extractor:
    from .prudential import PrudentialExtractor

    extractors: list[Extractor] = [PrudentialExtractor()]
    for extractor in extractors:
        if extractor.matches(files):
            return extractor
    raise ValueError("暂时无法识别保险公司。第一版支持 Prudential / 保诚 PDF。")

