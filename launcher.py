# -*- coding: utf-8 -*-
import os, sys, time, socket, threading, webbrowser, traceback, shutil, tkinter as tk
from tkinter import messagebox

# ── 必须在最顶部，其他 import 之前 ──────────────────────────────────────────
# PyInstaller --windowed 模式下，Windows 不分配控制台，Python 把
# sys.stdout / sys.stderr 置为 None。http.server 的 log_message()
# 会往 sys.stderr 写日志，None.write() 直接崩溃，导致每个请求
# 都以空响应结束（浏览器显示 ERR_EMPTY_RESPONSE）。
# 重定向到 NUL 即可解决。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
# ────────────────────────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 8787
URL  = f"http://{HOST}:{PORT}"

_backend_error: str = ""


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def exe_dir() -> str:
    if getattr(sys, "frozen", False):
        exe_path = os.path.abspath(sys.executable)
        parts = exe_path.split(os.sep)
        for index, part in enumerate(parts):
            if part.endswith(".app"):
                return os.sep.join(parts[:index]) or os.sep
        return os.path.dirname(exe_path)
    return os.path.dirname(os.path.abspath(__file__))


def setup_environment():
    os.environ.setdefault("POLICY_TRANSFER_B_DIR",
                          resource_path(os.path.join("templates", "B")))
    os.environ.setdefault("POLICY_TRANSFER_C_TEMPLATE",
                          resource_path(os.path.join("templates", "C",
                                                     "policy-import-v181.xlsx")))
    os.environ.setdefault("POLICY_TRANSFER_HOST", HOST)
    os.environ.setdefault("POLICY_TRANSFER_PORT", str(PORT))

    root_dir = exe_dir()
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
    os.makedirs(os.path.join(data_root, "cases"),   exist_ok=True)
    os.makedirs(os.path.join(data_root, "outputs"), exist_ok=True)
    os.chdir(root_dir)


def run_backend():
    global _backend_error
    try:
        from policy_transfer.server import run as server_run
        server_run(HOST, PORT)
    except Exception:
        tb = traceback.format_exc()
        _backend_error = tb
        log_path = os.path.join(exe_dir(), "error.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
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


class LauncherUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._started = False

        root.title("保单转换工具")
        root.geometry("360x210")
        root.resizable(False, False)

        tk.Label(root, text="保单转换工具", font=("Microsoft YaHei", 13, "bold")).pack(pady=(22, 4))
        tk.Label(root, text="Prudential → B公司文件 + C系统Excel",
                 font=("Microsoft YaHei", 9), fg="#6b7280").pack()

        self.status = tk.Label(root, text="● 未启动", fg="#9ca3af",
                               font=("Microsoft YaHei", 10))
        self.status.pack(pady=(12, 10))

        self.btn = tk.Button(root, text="启动并打开网页", width=22, height=2,
                             font=("Microsoft YaHei", 10), command=self.on_start)
        self.btn.pack()

        tk.Button(root, text="退出", width=22,
                  font=("Microsoft YaHei", 9), command=self.quit_app).pack(pady=(8, 0))

        root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def on_start(self):
        if self._started or port_open(HOST, PORT):
            webbrowser.open(URL)
            return
        self.btn.config(state="disabled", text="正在启动…")
        self.status.config(text="● 启动中", fg="#d97706")
        threading.Thread(target=run_backend, daemon=True).start()
        threading.Thread(target=self._wait_then_open, daemon=True).start()

    def _wait_then_open(self):
        ok = wait_until_ready()
        self.root.after(0, lambda: self._on_ready(ok))

    def _on_ready(self, ok: bool):
        if ok:
            self._started = True
            webbrowser.open(URL)
            self.status.config(text="● 运行中  |  输出: data/outputs/", fg="#16a34a")
            self.btn.config(state="normal", text="打开网页")
        else:
            self.status.config(text="● 启动失败", fg="#dc2626")
            self.btn.config(state="normal", text="启动并打开网页")
            log_path = os.path.join(exe_dir(), "error.log")
            detail = _backend_error.strip() if _backend_error else "未知原因"
            short = "\n".join(detail.splitlines()[-8:]) if detail else detail
            messagebox.showerror(
                "启动失败",
                f"后端 20 秒内未就绪。\n\n错误信息:\n{short}\n\n完整日志: {log_path}"
            )

    def quit_app(self):
        self.root.destroy()
        os._exit(0)


if __name__ == "__main__":
    setup_environment()
    root = tk.Tk()
    LauncherUI(root)
    root.mainloop()
