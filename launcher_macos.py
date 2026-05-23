# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser

HOST = "127.0.0.1"
PORT = 8787
URL = f"http://{HOST}:{PORT}"
_backend_error = ""


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def app_root() -> str:
    if getattr(sys, "frozen", False):
        exe_path = os.path.abspath(sys.executable)
        parts = exe_path.split(os.sep)
        for index, part in enumerate(parts):
            if part.endswith(".app"):
                return os.sep.join(parts[:index]) or os.sep
        return os.path.dirname(exe_path)
    return os.path.dirname(os.path.abspath(__file__))


def alert(title: str, message: str) -> None:
    script = (
        'display dialog '
        + repr(message)
        + ' with title '
        + repr(title)
        + ' buttons {"OK"} default button "OK"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        pass


def setup_environment() -> None:
    root_dir = app_root()
    os.environ.setdefault("POLICY_TRANSFER_B_DIR", resource_path(os.path.join("templates", "B")))
    os.environ.setdefault(
        "POLICY_TRANSFER_C_TEMPLATE",
        resource_path(os.path.join("templates", "C", "policy-import-v181.xlsx")),
    )
    os.environ.setdefault("POLICY_TRANSFER_HOST", HOST)
    os.environ.setdefault("POLICY_TRANSFER_PORT", str(PORT))

    config_dir = os.path.join(root_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    tr_config = os.path.join(config_dir, "tr_representatives.csv")
    if not os.path.exists(tr_config):
        bundled_tr_config = resource_path(os.path.join("config", "tr_representatives.csv"))
        if os.path.exists(bundled_tr_config):
            shutil.copy2(bundled_tr_config, tr_config)
        else:
            with open(tr_config, "w", encoding="utf-8") as f:
                f.write("name,ia_no\n")
    os.environ.setdefault("POLICY_TRANSFER_TR_REPRESENTATIVES", tr_config)

    data_root = os.path.join(root_dir, "data")
    os.makedirs(os.path.join(data_root, "cases"), exist_ok=True)
    os.makedirs(os.path.join(data_root, "outputs"), exist_ok=True)
    os.chdir(root_dir)


def run_backend() -> None:
    global _backend_error
    try:
        from policy_transfer.server import run as server_run

        server_run(HOST, PORT)
    except Exception:
        tb = traceback.format_exc()
        _backend_error = tb
        try:
            with open(os.path.join(app_root(), "error.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def wait_until_ready(timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(HOST, PORT):
            return True
        time.sleep(0.25)
    return False


def main() -> None:
    setup_environment()
    if port_open(HOST, PORT):
        webbrowser.open(URL)
        return

    threading.Thread(target=run_backend, daemon=True).start()
    if not wait_until_ready():
        detail = _backend_error.strip() if _backend_error else "后端 20 秒内未就绪。"
        short = "\n".join(detail.splitlines()[-8:])
        alert("保单转换工具启动失败", f"{short}\n\n完整日志：{os.path.join(app_root(), 'error.log')}")
        return

    webbrowser.open(URL)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
