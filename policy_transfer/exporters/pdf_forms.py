from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, TextStringObject


def fill_pdf_form(template: Path, output: Path, values: dict[str, object], *, clear_unmapped: bool = False) -> None:
    reader = PdfReader(str(template))
    writer = PdfWriter()
    writer.append(reader)
    writer.set_need_appearances_writer(True)

    for page in writer.pages:
        _update_page_values(page, values, clear_unmapped=clear_unmapped)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def add_diagonal_line_marks(pdf_path: Path, *, first_page: int, last_page: int) -> None:
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append(reader)

    for page_number, page in enumerate(writer.pages, start=1):
        if first_page <= page_number <= last_page:
            _append_diagonal_line(page)

    with pdf_path.open("wb") as handle:
        writer.write(handle)


def _update_page_values(page, values: dict[str, object], *, clear_unmapped: bool) -> None:
    annotations = page.get("/Annots") or []
    for annotation_ref in annotations:
        annotation = annotation_ref.get_object()
        name = annotation.get("/T")
        parent = annotation["/Parent"].get_object() if annotation.get("/Parent") else None
        if name is None and parent:
            name = parent.get("/T")
        if name in values:
            raw_value = values[name]
        elif clear_unmapped:
            raw_value = ""
        else:
            continue
        field_type = _set_field_value(annotation, parent, raw_value)
        # Existing appearance streams often use fonts that cannot encode CJK.
        # Removing AP lets the PDF reader regenerate the visible field appearance.
        if field_type != "/Btn" and "/AP" in annotation:
            del annotation["/AP"]


def _set_field_value(annotation, parent, raw_value: object):
    target = parent or annotation
    field_type = target.get("/FT") or annotation.get("/FT")
    if field_type == "/Btn":
        value = raw_value if raw_value not in (None, "") else "/Off"
        name_value = NameObject(str(value)) if str(value).startswith("/") else TextStringObject(str(value))
        annotation.update({NameObject("/AS"): name_value})
    else:
        name_value = (
            NameObject(raw_value)
            if isinstance(raw_value, str) and raw_value.startswith("/") and raw_value
            else TextStringObject("" if raw_value is None else str(raw_value))
        )
    annotation.update({NameObject("/V"): name_value})
    if parent:
        parent.update({NameObject("/V"): name_value})
    return field_type


def _append_diagonal_line(page) -> None:
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    margin_x = width * 0.14
    margin_y = height * 0.10
    existing = page._get_contents_as_bytes()
    mark = (
        b"\n% policy-transfer diagonal skip mark\n"
        b"q\n"
        b"0.00 0.38 0.88 RG\n"
        b"1.4 w\n"
        b"1 J\n"
        + f"{margin_x:.2f} {margin_y:.2f} m\n".encode("ascii")
        + f"{width - margin_x:.2f} {height - margin_y:.2f} l\n".encode("ascii")
        + b"S\n"
        b"Q\n"
    )
    stream = DecodedStreamObject()
    stream.set_data(existing + mark)
    page.replace_contents(stream)
