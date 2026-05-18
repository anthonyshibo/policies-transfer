from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

from policy_transfer.config import DATA_DIR
from policy_transfer.models import FieldValue, PolicyCase, flatten_case


PREVIEW_DIR = DATA_DIR / "previews"
PREVIEW_CACHE_VERSION = "v2"


def crop_for_field(case: PolicyCase, field_path: str, pdf_path: Path, case_id: str) -> Path | None:
    field = flatten_case(case).get(field_path)
    if not isinstance(field, FieldValue) or not field.source or not field.source.page:
        return None
    page_number = field.source.page
    snippet = field.source.snippet or str(field.value or "")
    if field_path == "source_company":
        snippet = f"{snippet}\n保單內容\n保單號碼\n保誠保險有限公司"
    cache_key = hashlib.sha1(f"{PREVIEW_CACHE_VERSION}:{pdf_path}:{pdf_path.stat().st_mtime}:{page_number}:{field_path}:{snippet}".encode()).hexdigest()[:16]
    out_dir = PREVIEW_DIR / case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{cache_key}.png"
    if output.exists():
        return output

    page_image = _render_page(pdf_path, page_number, out_dir, cache_key)
    if not page_image:
        return _placeholder_preview(out_dir, cache_key)
    region = _find_region(pdf_path, page_number, snippet, str(field.value or ""))

    with Image.open(page_image) as image:
        if region:
            reader = PdfReader(str(pdf_path))
            page = reader.pages[page_number - 1]
            page_w = float(page.mediabox.width)
            page_h = float(page.mediabox.height)
            x1, y1, x2, y2 = region
            sx = image.width / page_w
            sy = image.height / page_h
            left = max(0, int((x1 - 70) * sx))
            right = min(image.width, int((x2 + 260) * sx))
            top = max(0, int((page_h - y2 - 60) * sy))
            bottom = min(image.height, int((page_h - y1 + 80) * sy))
            if right - left < image.width * 0.45:
                pad = int(image.width * 0.2)
                left = max(0, left - pad)
                right = min(image.width, right + pad)
            crop = image.crop((left, top, right, bottom))
        else:
            # Fallback: upper-middle full-width slice is more readable than a full page thumbnail.
            crop = image.crop((0, 0, image.width, min(image.height, int(image.height * 0.45))))
        crop.save(output)
    return output


def _placeholder_preview(out_dir: Path, cache_key: str) -> Path:
    output = out_dir / f"{cache_key}-placeholder.png"
    if output.exists():
        return output
    image = Image.new("RGB", (900, 520), "#f8fafc")
    image.save(output)
    return output


def _render_page(pdf_path: Path, page_number: int, out_dir: Path, cache_key: str) -> Path | None:
    if not shutil.which("qlmanage"):
        return None
    one_page_pdf = out_dir / f"{cache_key}-page.pdf"
    rendered = out_dir / f"{one_page_pdf.name}.png"
    if not rendered.exists():
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()
        writer.add_page(reader.pages[page_number - 1])
        with one_page_pdf.open("wb") as handle:
            writer.write(handle)
        subprocess.run(
            ["qlmanage", "-t", "-s", "1800", "-o", str(out_dir), str(one_page_pdf)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return rendered if rendered.exists() else None


def _find_region(pdf_path: Path, page_number: int, snippet: str, value: str) -> tuple[float, float, float, float] | None:
    reader = PdfReader(str(pdf_path))
    page = reader.pages[page_number - 1]
    fragments: list[tuple[str, float, float]] = []

    def visit(text, _cm, tm, _font, _size):
        text = text.strip()
        if text:
            fragments.append((text, float(tm[4]), float(tm[5])))

    page.extract_text(visitor_text=visit)
    lines = _group_lines(fragments)
    needles = _needles(snippet, value)
    best: tuple[int, tuple[str, float, float, float, float]] | None = None
    for line in lines:
        text, x1, y1, x2, y2 = line
        haystack = _norm(text)
        score = 0
        for needle in needles:
            if needle and needle in haystack:
                score = max(score, len(needle))
            elif needle:
                score = max(score, _overlap_score(haystack, needle))
        if score and (best is None or score > best[0]):
            best = (score, line)
    if not best:
        return None
    _text, x1, y1, x2, y2 = best[1]
    return x1, y1, x2, y2


def _group_lines(fragments: list[tuple[str, float, float]]) -> list[tuple[str, float, float, float, float]]:
    buckets: dict[int, list[tuple[str, float, float]]] = {}
    for text, x, y in fragments:
        buckets.setdefault(round(y / 4), []).append((text, x, y))
    lines = []
    for items in buckets.values():
        items.sort(key=lambda item: item[1])
        text = " ".join(item[0] for item in items)
        x1 = min(item[1] for item in items)
        x2 = max(item[1] + max(12, len(item[0]) * 5) for item in items)
        y = sum(item[2] for item in items) / len(items)
        lines.append((text, x1, y - 6, x2, y + 12))
    return lines


def _needles(snippet: str, value: str) -> list[str]:
    raw = [value, snippet, compact_first_line(snippet)]
    tokens = re.findall(r"[A-Za-z0-9]{4,}|[\u4e00-\u9fff]{2,}", snippet)
    raw.extend(tokens)
    result = []
    for item in raw:
        normed = _norm(item)
        if len(normed) >= 2 and normed not in result:
            result.append(normed[:80])
    return sorted(result, key=len, reverse=True)


def compact_first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return text.strip()


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text)).lower()


def _overlap_score(haystack: str, needle: str) -> int:
    best = 0
    for size in range(min(len(needle), 40), 3, -1):
        for start in range(0, len(needle) - size + 1):
            if needle[start : start + size] in haystack:
                return size
    return best
