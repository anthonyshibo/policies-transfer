from __future__ import annotations

import cgi
import html
import os
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from policy_transfer.case_store import create_case, load_case, output_dir, save_case, upload_dir
from policy_transfer.config import DEFAULT_TRANSFER_DIR
from policy_transfer.exporters import export_bundle
from policy_transfer.extractors import ExtractionInput, detect_extractor
from policy_transfer.review import apply_updates, field_label, field_usage, review_rows, translated_issue
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
            elif parsed.path.startswith("/review/"):
                case_id = parsed.path.split("/")[-1]
                self._html(_layout(_review(case_id, load_case(case_id))))
            elif parsed.path.startswith("/download/"):
                self._download(parsed.path)
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
        upload_fields = form["files"] if "files" in form else []
        if not isinstance(upload_fields, list):
            upload_fields = [upload_fields]
        files: list[ExtractionInput] = []
        for item in upload_fields:
            if not item.filename:
                continue
            files.append(ExtractionInput(Path(item.filename).name, item.file.read()))
        if not files:
            raise ValueError("请至少上传一份 PDF。")
        extractor = detect_extractor(files)
        case = extractor.extract(files)
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
        self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
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
    .downloads {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; padding: 0; list-style: none; }}
    .downloads a {{ display: block; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); text-decoration: none; }}
    code {{ background: #edf2f7; padding: 2px 5px; border-radius: 4px; }}
    @media (max-width: 760px) {{ main {{ padding: 16px; }} table {{ display:block; overflow:auto; }} header {{ padding: 0 16px; }} }}
  </style>
</head>
<body>
  <header><a href="/">Policy Transfer Tool</a><span>Prudential → B / C</span></header>
  <main>{content}</main>
  <script>
    document.addEventListener('click', function (event) {{
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
  </script>
</body>
</html>"""


def _home() -> str:
    return """<section class="panel">
  <h1>保单转单工具</h1>
  <p>上传 A 公司 Prudential PDF，系统会抽取关键字段到统一模型。你确认后，可一次生成 B 公司文件和 C 系统 Excel。</p>
  <form method="post" action="/extract" enctype="multipart/form-data">
    <input type="file" name="files" accept="application/pdf" multiple required>
    <div class="actions"><button type="submit">上传并抽取</button></div>
  </form>
  <h2>第一版范围</h2>
  <p>支持当前样本格式的 <code>Document.pdf</code> 和 <code>Document-3.pdf</code>。未来新增保险公司时，只需新增 extractor，不需要重写导出逻辑。</p>
</section>"""


def _review(case_id: str, case) -> str:
    issue_html = ""
    if case.review_issues:
        items = "".join(f"<li>{html.escape(translated_issue(issue))}</li>" for issue in case.review_issues)
        issue_html = f"<div class='issues'><strong>需要确认</strong><ul>{items}</ul></div>"

    rows = []
    for path, field_value in review_rows(case):
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
        rows.append(
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
    return f"""<section class="panel">
  <h1>人工确认</h1>
  <p>低置信度和缺失字段会高亮。修改后先保存确认，再生成文件。</p>
  {issue_html}
  <form method="post" action="/review/{case_id}">
    <table>
      <thead><tr><th>字段 / Field</th><th>值 / Value</th><th>用途说明</th><th>置信度</th><th>必填</th><th>备注</th><th>内部字段</th><th>来源</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
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
    for label, path in files.items():
        links.append(f"<li><a href='/download/{case_id}/{html.escape(path.name)}'>{html.escape(label)}<br><code>{html.escape(path.name)}</code></a></li>")
    return f"""<section class="panel">
  <h1>文件已生成</h1>
  <p>输出文件已写入本地工作区，也可以从下面下载打开。</p>
  <ul class="downloads">{''.join(links)}</ul>
  <div class="actions"><a class="button secondary" href="/review/{case_id}">回到确认页</a></div>
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


def run(host: str = HOST, port: int = PORT) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Policy Transfer Tool running at http://{host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    chosen_port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run(port=chosen_port)
