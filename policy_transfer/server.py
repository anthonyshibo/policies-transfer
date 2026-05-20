from __future__ import annotations

import cgi
import csv
import html
import os
import mimetypes
import platform
import re
import subprocess
import sys
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from policy_transfer.case_store import create_case, load_case, output_dir, save_case, upload_dir
from policy_transfer.config import DEFAULT_TRANSFER_DIR, TR_REPRESENTATIVES_FILE
from policy_transfer.exporters import export_bundle
from policy_transfer.extractors import ExtractionInput, detect_extractor
from policy_transfer.models import FieldValue
from policy_transfer.review import apply_updates, field_label, field_usage, review_sections, translated_issue
from policy_transfer.source_preview import crop_for_field


HOST = os.environ.get("POLICY_TRANSFER_HOST", "127.0.0.1")
PORT = int(os.environ.get("POLICY_TRANSFER_PORT", "8787"))


class Handler(BaseHTTPRequestHandler):
    server_version = "PolicyTransfer/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._html(_layout(_home()))
            elif parsed.path.startswith("/open-file/"):
                self._open_file(parsed.path)
            elif parsed.path.startswith("/review/"):
                case_id = parsed.path.split("/")[-1]
                self._html(_layout(_review(case_id, load_case(case_id))))
            elif parsed.path.startswith("/download/"):
                self._download(parsed.path)
            elif parsed.path.startswith("/download-all/"):
                self._download_all(parsed.path)
            elif parsed.path.startswith("/source/"):
                self._source_pdf(parsed.path)
            elif parsed.path.startswith("/source-crop/"):
                self._source_crop(parsed.path)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._html(_layout(_error(exc)), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/extract":
                self._handle_extract()
            elif parsed.path.startswith("/review/"):
                case_id = parsed.path.split("/")[-1]
                length = int(self.headers.get("content-length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                updates = {key: values[-1] for key, values in parse_qs(body, keep_blank_values=True).items()}
                case = apply_updates(load_case(case_id), updates)
                save_case(case_id, case)
                self._redirect(f"/review/{case_id}")
            elif parsed.path.startswith("/export/"):
                case_id = parsed.path.split("/")[-1]
                files = export_bundle(load_case(case_id), output_dir(case_id))
                self._html(_layout(_exported(case_id, files)))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._html(_layout(_error(exc)), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_extract(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        upload_fields = []
        for field_name in ("policy_files", "financial_files", "files"):
            if field_name not in form:
                continue
            field_items = form[field_name]
            if not isinstance(field_items, list):
                field_items = [field_items]
            upload_fields.extend(field_items)
        files: list[ExtractionInput] = []
        for item in upload_fields:
            if not item.filename:
                continue
            files.append(ExtractionInput(Path(item.filename).name, item.file.read()))
        if not files:
            raise ValueError("请至少上传一份 PDF。")
        extractor = detect_extractor(files)
        case = extractor.extract(files)
        _apply_tr_override(case, form)
        case_id = create_case(case)
        case_upload_dir = upload_dir(case_id)
        for item in files:
            (case_upload_dir / item.filename).write_bytes(item.content)
        self._redirect(f"/review/{case_id}")

    def _download(self, path: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 3:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _, case_id, filename = parts
        base = output_dir(case_id).resolve()
        target = (base / filename).resolve()
        if base not in target.parents or not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", _content_disposition(target.name, attachment=True))
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as handle:
            self.wfile.write(handle.read())

    def _download_all(self, path: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 2:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _, case_id = parts
        base = output_dir(case_id).resolve()
        files = [path for path in base.iterdir() if path.is_file() and path.suffix.lower() != ".zip"]
        if not files:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        zip_name = _zip_name(files)
        zip_path = base / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                archive.write(item, item.name)
        self._send_file(zip_path, attachment=True)

    def _open_file(self, path: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 3:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _, case_id, filename = parts
        target = _resolve_output_file(case_id, filename)
        if not target:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _open_local_file(target)
        encoded = b"OK"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, target: Path, attachment: bool) -> None:
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        disposition = "attachment" if attachment else "inline"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", _content_disposition(target.name, attachment=attachment))
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as handle:
            self.wfile.write(handle.read())

    def _source_pdf(self, path: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 3:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _, case_id, filename = parts
        target = _resolve_source_pdf(case_id, filename)
        if not target:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'inline; filename="{target.name}"')
        self.send_header("Content-Length", str(target.stat().st_size))
        self.end_headers()
        with target.open("rb") as handle:
            self.wfile.write(handle.read())

    def _source_crop(self, path: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 4:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        _, case_id, filename, field_path = parts
        source_pdf = _resolve_source_pdf(case_id, filename)
        if not source_pdf:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        crop = crop_for_field(load_case(case_id), field_path, source_pdf, case_id)
        if not crop or not crop.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(crop.stat().st_size))
        self.end_headers()
        with crop.open("rb") as handle:
            self.wfile.write(handle.read())

    def _html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()


def _layout(content: str) -> str:
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Policy Transfer Tool</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d9deea;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--ink); }}
    header {{ height: 64px; display: flex; align-items: center; justify-content: space-between; padding: 0 28px; background: #fff; border-bottom: 1px solid var(--line); }}
    header a {{ color: var(--ink); text-decoration: none; font-weight: 700; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 24px; box-shadow: 0 12px 30px rgba(15, 23, 42, .05); }}
    h1 {{ margin: 0 0 10px; font-size: 28px; line-height: 1.2; }}
    h2 {{ margin: 24px 0 12px; font-size: 18px; }}
    p {{ color: var(--muted); line-height: 1.6; }}
    .actions {{ display: flex; gap: 12px; align-items: center; margin-top: 18px; flex-wrap: wrap; }}
    button, .button {{ border: 0; background: var(--accent); color: #fff; border-radius: 7px; padding: 10px 14px; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }}
    button.secondary, .button.secondary {{ background: #344054; }}
    input[type=file] {{ display: block; width: 100%; padding: 16px; border: 1px dashed var(--line); border-radius: 8px; background: #fbfcff; }}
    .home-panel {{ overflow: hidden; padding: 0; }}
    .home-hero {{ padding: 30px 28px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, #f0fdfa 0%, #ffffff 54%, #eef4ff 100%); }}
    .home-title {{ display: flex; align-items: center; gap: 14px; margin-bottom: 8px; }}
    .home-mark {{ width: 42px; height: 42px; display: grid; place-items: center; border-radius: 8px; background: #0f766e; color: #fff; font-weight: 900; font-size: 20px; box-shadow: 0 10px 24px rgba(15, 118, 110, .20); }}
    .home-title h1 {{ margin: 0; }}
    .home-hero p {{ margin: 0; max-width: 760px; }}
    .home-content {{ padding: 24px 28px 28px; }}
    .home-actions {{ justify-content: flex-end; margin-top: 20px; }}
    .upload-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 18px; }}
    .upload-box {{ border: 1px solid var(--line); border-radius: 8px; padding: 18px; background: #fff; box-shadow: 0 8px 18px rgba(15, 23, 42, .04); transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease; }}
    .upload-box:hover {{ transform: translateY(-3px); border-color: #99d5ce; box-shadow: 0 16px 34px rgba(15, 23, 42, .10); }}
    .upload-box h2 {{ margin: 0 0 6px; font-size: 16px; }}
    .upload-box p {{ margin: 0 0 12px; font-size: 13px; }}
    .tr-panel {{ margin-top: 18px; border: 1px solid var(--line); border-radius: 8px; padding: 18px; background: #fff; box-shadow: 0 8px 18px rgba(15, 23, 42, .04); }}
    .tr-panel h2 {{ margin: 0 0 6px; font-size: 16px; }}
    .tr-panel p {{ margin: 0 0 12px; font-size: 13px; }}
    .tr-mode {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 10px 0 14px; color: #344054; font-size: 13px; }}
    .tr-mode label {{ display: inline-flex; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 7px; background: #fbfcff; }}
    .tr-fields {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .tr-fields label {{ display: grid; gap: 6px; color: #344054; font-size: 13px; font-weight: 650; }}
    .tr-fields input, .tr-fields select {{ width: 100%; padding: 10px; border: 1px solid var(--line); border-radius: 7px; background: #fff; color: var(--ink); font-size: 14px; }}
    .tr-pane[hidden] {{ display: none; }}
    .home-note {{ margin-top: 20px; padding: 14px 16px; border: 1px solid #dbe7f3; border-radius: 8px; background: #f8fbff; color: var(--muted); font-size: 13px; line-height: 1.55; }}
    .section-title {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 26px 0 10px; padding-bottom: 8px; border-bottom: 2px solid #c7d7fe; }}
    .section-title h2 {{ margin: 0; font-size: 18px; }}
    .section-title .en {{ color: var(--muted); font-weight: 600; font-size: 13px; }}
    .section-title .count {{ color: var(--muted); font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f1f4f9; color: #344054; position: sticky; top: 0; z-index: 1; }}
    tr.review {{ background: #fff7ed; }}
    tr.missing {{ background: #fff1f0; }}
    td.path {{ width: 250px; color: #1d2939; font-weight: 650; }}
    td.path .en {{ display: block; margin-top: 3px; color: var(--muted); font-weight: 500; font-size: 12px; }}
    td.internal {{ width: 190px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #344054; font-size: 12px; }}
    td.usage {{ width: 260px; color: #475467; }}
    td.source {{ width: 260px; color: var(--muted); }}
    .source-hover {{ position: relative; display: inline-block; max-width: 260px; }}
    .source-trigger {{ color: #155eef; text-decoration: underline; text-underline-offset: 2px; cursor: default; }}
    .source-preview {{ display: none; position: absolute; right: 0; top: 22px; z-index: 20; width: 520px; background: #fff; border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 18px 50px rgba(15, 23, 42, .18); padding: 10px; }}
    .source-hover:hover .source-preview, .source-hover.pinned .source-preview {{ display: block; }}
    .source-hover.pinned .source-trigger {{ color: #0f766e; font-weight: 700; }}
    .source-close {{ float: right; border: 1px solid var(--line); background: #fff; color: #344054; border-radius: 5px; padding: 3px 7px; margin-bottom: 8px; font-size: 12px; cursor: pointer; }}
    .source-crop {{ display: block; width: 100%; max-height: 360px; object-fit: contain; border: 1px solid var(--line); border-radius: 6px; background: #f8fafc; }}
    .source-open {{ display: inline-block; margin-top: 7px; color: #155eef; text-decoration: none; font-size: 12px; font-weight: 650; }}
    .source-snippet {{ margin-top: 8px; max-height: 96px; overflow: auto; color: #344054; font-size: 12px; white-space: pre-wrap; }}
    input.field {{ width: 100%; min-width: 180px; padding: 8px; border: 1px solid var(--line); border-radius: 6px; font-size: 13px; }}
    .issues {{ border-left: 4px solid var(--warn); padding: 10px 14px; background: #fffbeb; color: #7c2d12; }}
    .done-panel {{ overflow: hidden; padding: 0; }}
    .done-hero {{ display: grid; grid-template-columns: 1fr auto; gap: 20px; align-items: center; padding: 28px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, #f0fdfa 0%, #ffffff 54%, #eef4ff 100%); }}
    .done-title {{ display: flex; align-items: center; gap: 14px; margin-bottom: 8px; }}
    .done-mark {{ width: 42px; height: 42px; display: grid; place-items: center; border-radius: 50%; background: #0f766e; color: #fff; font-size: 24px; font-weight: 800; box-shadow: 0 10px 24px rgba(15, 118, 110, .22); }}
    .done-title h1 {{ margin: 0; }}
    .done-hero p {{ margin: 0; max-width: 760px; }}
    .done-actions {{ margin-top: 0; justify-content: flex-end; }}
    .button.primary {{ background: #0f766e; box-shadow: 0 10px 22px rgba(15, 118, 110, .18); }}
    .button.primary:hover {{ transform: translateY(-1px); box-shadow: 0 14px 28px rgba(15, 118, 110, .22); }}
    .button, button {{ transition: transform .16s ease, box-shadow .16s ease, background .16s ease; }}
    .done-content {{ padding: 24px 28px 28px; }}
    .done-subhead {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }}
    .done-subhead h2 {{ margin: 0; font-size: 16px; }}
    .done-subhead span {{ color: var(--muted); font-size: 13px; }}
    .downloads {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; padding: 0; margin: 0; list-style: none; }}
    .download-card {{ display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 12px; align-items: center; min-height: 86px; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); text-decoration: none; box-shadow: 0 8px 18px rgba(15, 23, 42, .04); overflow: hidden; transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease; }}
    .download-card:hover {{ transform: translateY(-3px); border-color: #99d5ce; background: #fcfffe; box-shadow: 0 16px 34px rgba(15, 23, 42, .10); }}
    .file-badge {{ width: 44px; height: 44px; display: grid; place-items: center; border-radius: 8px; background: #e6f4f1; color: #0f766e; font-weight: 800; font-size: 12px; }}
    .download-card > span:nth-child(2) {{ min-width: 0; }}
    .download-card strong {{ display: block; margin-bottom: 5px; font-size: 15px; }}
    .download-card code {{ display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: transparent; padding: 0; color: var(--muted); font-size: 12px; }}
    .open-hint {{ color: #0f766e; font-size: 13px; font-weight: 700; opacity: 0; transform: translateX(-4px); transition: opacity .16s ease, transform .16s ease; }}
    .download-card:hover .open-hint {{ opacity: 1; transform: translateX(0); }}
    code {{ background: #edf2f7; padding: 2px 5px; border-radius: 4px; }}
    @media (max-width: 760px) {{ main {{ padding: 16px; }} table {{ display:block; overflow:auto; }} header {{ padding: 0 16px; }} .upload-grid, .tr-fields {{ grid-template-columns: 1fr; }} .done-hero {{ grid-template-columns: 1fr; }} .done-actions, .home-actions {{ justify-content: flex-start; }} }}
  </style>
</head>
<body>
  <header><a href="/">Policy Transfer Tool</a><span>Prudential → B / C</span></header>
  <main>{content}</main>
  <script>
    document.addEventListener('click', function (event) {{
      const opener = event.target.closest('[data-open-file]');
      if (opener) {{
        fetch(opener.getAttribute('href')).catch(function () {{}});
        event.preventDefault();
        return;
      }}
      const close = event.target.closest('.source-close');
      if (close) {{
        close.closest('.source-hover')?.classList.remove('pinned');
        event.preventDefault();
        event.stopPropagation();
        return;
      }}
      const trigger = event.target.closest('.source-trigger');
      if (trigger) {{
        const wrapper = trigger.closest('.source-hover');
        const wasPinned = wrapper.classList.contains('pinned');
        document.querySelectorAll('.source-hover.pinned').forEach(function (node) {{
          if (node !== wrapper) node.classList.remove('pinned');
        }});
        wrapper.classList.toggle('pinned', !wasPinned);
        event.preventDefault();
        event.stopPropagation();
        return;
      }}
      if (!event.target.closest('.source-preview')) {{
        document.querySelectorAll('.source-hover.pinned').forEach(function (node) {{
          node.classList.remove('pinned');
        }});
      }}
    }});
    document.addEventListener('change', function (event) {{
      if (!event.target.matches('input[name="tr_mode"]')) return;
      const mode = event.target.value;
      document.querySelectorAll('.tr-pane').forEach(function (node) {{
        node.hidden = node.getAttribute('data-tr-pane') !== mode;
      }});
    }});
  </script>
</body>
</html>"""


def _home() -> str:
    tr_options = _tr_option_html()
    config_disabled = " disabled" if not tr_options else ""
    return f"""<section class="panel home-panel">
  <div class="home-hero">
    <div class="home-title"><span class="home-mark">PT</span><h1>保单转单工具</h1></div>
    <p>上传 Prudential 保单文件与财务资料，系统会抽取关键字段；确认无误后，一次生成 B 公司文件和 C 系统导入表。</p>
  </div>
  <div class="home-content">
  <form method="post" action="/extract" enctype="multipart/form-data">
    <div class="upload-grid">
      <div class="upload-box">
        <h2>保单文件 / Policy document</h2>
        <p>上传 ePolicy 或正式保单 PDF。用于读取保单号、生效日、首期保费日、产品及正式保费。</p>
        <input type="file" name="policy_files" accept="application/pdf" multiple required>
      </div>
      <div class="upload-box">
        <h2>财务资料 / Financial information</h2>
        <p>上传 Financial Information / FNA PDF。用于读取收入、资产、负债、开支和保障目标。</p>
        <input type="file" name="financial_files" accept="application/pdf" multiple>
      </div>
    </div>
    <div class="tr-panel">
      <h2>业务代表 / Technical representative</h2>
      <p>默认使用原始文档提取的 TR name 和 IA 号码；如本次转单更换了 TR，可在这里指定，指定后会覆盖文档抽取值。</p>
      <div class="tr-mode">
        <label><input type="radio" name="tr_mode" value="document" checked> 从原始文档提取</label>
        <label><input type="radio" name="tr_mode" value="configured"{config_disabled}> 从配置名单选择</label>
        <label><input type="radio" name="tr_mode" value="manual"> 手工输入</label>
      </div>
      <div class="tr-pane" data-tr-pane="configured" hidden>
        <div class="tr-fields">
          <label>选择 TR
            <select name="tr_selected"{config_disabled}>
              <option value="">请选择</option>
              {tr_options}
            </select>
          </label>
        </div>
      </div>
      <div class="tr-pane" data-tr-pane="manual" hidden>
        <div class="tr-fields">
          <label>TR name / 业务代表姓名<input name="manual_tr_name" autocomplete="off"></label>
          <label>IA number / IA 号码<input name="manual_tr_license_no" autocomplete="off"></label>
        </div>
      </div>
    </div>
    <div class="actions home-actions"><button class="primary" type="submit">上传并抽取</button></div>
  </form>
  <div class="home-note">TR 配置文件：<code>{html.escape(str(TR_REPRESENTATIVES_FILE))}</code>。第一版支持当前 Prudential 样本格式；未来新增保险公司时，只需新增 extractor，不需要重写导出逻辑。</div>
  </div>
</section>"""


def _load_tr_representatives() -> list[dict[str, str]]:
    if not TR_REPRESENTATIVES_FILE.exists():
        return []
    with TR_REPRESENTATIVES_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            ia_no = (row.get("ia_no") or row.get("license_no") or "").strip()
            if name or ia_no:
                rows.append({"name": name, "ia_no": ia_no})
        return rows


def _tr_option_html() -> str:
    options = []
    for idx, item in enumerate(_load_tr_representatives()):
        label = " / ".join(part for part in [item["name"], item["ia_no"]] if part)
        options.append(f"<option value='{idx}'>{html.escape(label)}</option>")
    return "".join(options)


def _apply_tr_override(case, form: cgi.FieldStorage) -> None:
    mode = (form.getfirst("tr_mode") or "document").strip()
    name = ""
    license_no = ""
    if mode == "configured":
        selected = (form.getfirst("tr_selected") or "").strip()
        representatives = _load_tr_representatives()
        if selected.isdigit() and int(selected) < len(representatives):
            representative = representatives[int(selected)]
            name = representative["name"]
            license_no = representative["ia_no"]
    elif mode == "manual":
        name = (form.getfirst("manual_tr_name") or "").strip()
        license_no = (form.getfirst("manual_tr_license_no") or "").strip()

    if not name and not license_no:
        return
    source_note = "Manually selected on upload page." if mode == "configured" else "Manually entered on upload page."
    if name:
        case.tr_name = FieldValue(name, 1.0, None, False, False, source_note)
    if license_no:
        case.tr_license_no = FieldValue(license_no, 1.0, None, False, False, source_note)


def _review(case_id: str, case) -> str:
    issue_html = ""
    if case.review_issues:
        items = "".join(f"<li>{html.escape(translated_issue(issue))}</li>" for issue in case.review_issues)
        issue_html = f"<div class='issues'><strong>需要确认</strong><ul>{items}</ul></div>"

    def render_row(path, field_value) -> str:
        css = "missing" if field_value.required and not field_value.value else "review" if field_value.needs_review else ""
        source = ""
        if field_value.source:
            doc = quote(field_value.source.document)
            field = quote(path)
            page = field_value.source.page or 1
            snippet = html.escape(field_value.source.snippet[:400])
            source = (
                "<span class='source-hover'>"
                f"<span class='source-trigger'>{html.escape(field_value.source.document)} p.{page}</span>"
                "<span class='source-preview'>"
                "<button class='source-close' type='button'>关闭</button>"
                f"<img class='source-crop' src='/source-crop/{case_id}/{doc}/{field}' loading='lazy' alt='source crop'>"
                f"<a class='source-open' href='/source/{case_id}/{doc}#page={page}' target='_blank'>打开整页 PDF / Open full page</a>"
                f"<div class='source-snippet'>{snippet}</div>"
                "</span>"
                "</span>"
            )
        return (
            "<tr class='{css}'>"
            "<td class='path'>{label}</td>"
            "<td><input class='field' name='field:{path}' value='{value}'></td>"
            "<td class='usage'>{usage}</td>"
            "<td>{confidence:.2f}</td>"
            "<td>{required}</td>"
            "<td>{note}</td>"
            "<td class='internal'>{path}</td>"
            "<td class='source'>{source}</td>"
            "</tr>".format(
                css=css,
                path=html.escape(path),
                label=field_label(path),
                value=html.escape("" if field_value.value is None else str(field_value.value)),
                usage=html.escape(field_usage(path)),
                confidence=field_value.confidence,
                required="是" if field_value.required else "",
                note=html.escape(field_value.note or ""),
                source=source,
            )
        )

    section_html = []
    for zh, en, section_rows in review_sections(case):
        if not section_rows:
            continue
        rows = "".join(render_row(path, field_value) for path, field_value in section_rows)
        section_html.append(
            "<div class='section-title'>"
            f"<h2>{html.escape(zh)} <span class='en'>{html.escape(en)}</span></h2>"
            f"<span class='count'>{len(section_rows)} fields</span>"
            "</div>"
            "<table>"
            "<thead><tr><th>字段 / Field</th><th>值 / Value</th><th>用途说明</th><th>置信度</th><th>必填</th><th>备注</th><th>内部字段</th><th>来源</th></tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
        )
    return f"""<section class="panel">
  <h1>人工确认</h1>
  <p>低置信度和缺失字段会高亮。修改后先保存确认，再生成文件。</p>
  {issue_html}
  <form method="post" action="/review/{case_id}">
    {''.join(section_html)}
    <div class="actions">
      <button type="submit">保存确认</button>
    </div>
  </form>
  <form method="post" action="/export/{case_id}">
    <div class="actions">
      <button class="secondary" type="submit">生成 B 文件和 C Excel</button>
    </div>
  </form>
</section>"""


def _exported(case_id: str, files: dict[str, Path]) -> str:
    links = []
    visible_files = {label: path for label, path in files.items() if label != "report"}
    for label, path in visible_files.items():
        links.append(
            f"<li><a class='download-card' href='/open-file/{case_id}/{quote(path.name)}' title='打开文件' data-open-file='1'>"
            f"<span class='file-badge'>{html.escape(_file_ext(path))}</span>"
            "<span>"
            f"<strong>{html.escape(_file_label(label))}</strong>"
            f"<code>{html.escape(path.name)}</code>"
            "</span>"
            "<span class='open-hint'>打开</span>"
            "</a></li>"
        )
    return f"""<section class="panel done-panel">
  <div class="done-hero">
    <div>
      <div class="done-title"><span class="done-mark">✓</span><h1>文件已生成</h1></div>
      <p>转换完成。单击文件会用本机默认应用打开；需要转发或备份时，一键下载全部 ZIP。</p>
    </div>
    <div class="actions done-actions">
      <a class="button primary" href="/download-all/{case_id}">下载全部 ZIP</a>
      <a class="button secondary" href="/review/{case_id}">回到确认页</a>
    </div>
  </div>
  <div class="done-content">
    <div class="done-subhead"><h2>输出文件</h2><span>{len(visible_files)} 个文件</span></div>
    <ul class="downloads">{''.join(links)}</ul>
  </div>
</section>"""


def _error(exc: Exception) -> str:
    return f"""<section class="panel">
  <h1>处理失败</h1>
  <p>{html.escape(str(exc))}</p>
  <pre>{html.escape(type(exc).__name__)}</pre>
  <div class="actions"><a class="button secondary" href="/">返回首页</a></div>
</section>"""


def _resolve_source_pdf(case_id: str, filename: str) -> Path | None:
    safe_name = Path(filename).name
    candidates = [
        upload_dir(case_id) / safe_name,
        DEFAULT_TRANSFER_DIR / "A" / safe_name,
        DEFAULT_TRANSFER_DIR / "B" / safe_name,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() == ".pdf":
            return candidate
    return None


def _resolve_output_file(case_id: str, filename: str) -> Path | None:
    safe_name = Path(filename).name
    base = output_dir(case_id).resolve()
    target = (base / safe_name).resolve()
    if base in target.parents and target.exists() and target.is_file():
        return target
    return None


def _open_local_file(target: Path) -> None:
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", str(target)])
        elif system == "Windows":
            os.startfile(str(target))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except OSError:
        pass


def _zip_name(files: list[Path]) -> str:
    first = files[0].stem
    if first.endswith("_client_booklet"):
        first = first.removesuffix("_client_booklet")
    return f"{first}_all.zip"


def _file_label(label: str) -> str:
    labels = {
        "client_booklet": "客户资料手册",
        "client_acknowledgement": "客户确认书",
        "risk_assessment": "风险评估表",
        "service_appointment": "服务委任函",
        "policy_import": "C系统导入表",
        "report": "转换报告",
    }
    return labels.get(label, label)


def _file_ext(path: Path) -> str:
    suffix = path.suffix.replace(".", "").upper()
    if suffix == "JSON":
        return "LOG"
    return suffix or "FILE"


def _content_disposition(filename: str, attachment: bool) -> str:
    disposition = "attachment" if attachment else "inline"
    fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "download"
    encoded = quote(filename, safe="")
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def run(host: str = HOST, port: int = PORT) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Policy Transfer Tool running at http://{host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    chosen_port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run(port=chosen_port)
