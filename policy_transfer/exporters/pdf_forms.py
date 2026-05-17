from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject


def fill_pdf_form(template: Path, output: Path, values: dict[str, object]) -> None:
    reader = PdfReader(str(template))
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)

    for page in writer.pages:
        _update_page_values(page, values)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def _update_page_values(page, values: dict[str, object]) -> None:
    annotations = page.get("/Annots") or []
    for annotation_ref in annotations:
        annotation = annotation_ref.get_object()
        name = annotation.get("/T")
        if name is None and annotation.get("/Parent"):
            name = annotation["/Parent"].get_object().get("/T")
        if name not in values:
            continue
        raw_value = values[name]
        if raw_value is None or raw_value == "":
            continue
        value = NameObject(raw_value) if isinstance(raw_value, str) and raw_value.startswith("/") else TextStringObject(str(raw_value))
        annotation.update({NameObject("/V"): value})
        if annotation.get("/Parent"):
            annotation["/Parent"].get_object().update({NameObject("/V"): value})
        # Existing appearance streams often use fonts that cannot encode CJK.
        # Removing AP lets the PDF reader regenerate the visible field appearance.
        if "/AP" in annotation:
            del annotation["/AP"]
