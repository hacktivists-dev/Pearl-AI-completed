import base64
import json
import os
import platform
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, BooleanVar, StringVar, Tk, messagebox
from tkinter import ttk

import requests

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


APP_VERSION = "1.0.0"
DEFAULT_SERVER = "https://hactivists.pythonanywhere.com"
CONFIG_DIR = Path.home() / ".pearl-device-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
AUDIT_FILE = CONFIG_DIR / "audit.jsonl"
POLL_SECONDS = 3
REQUEST_TIMEOUT = 30
MAX_READ_CHARS = 200_000
MAX_LIST_ENTRIES = 2_000
ALLOWED_COMMANDS = {
    "python", "python3", "py", "node", "npm", "npm.cmd", "npx", "npx.cmd",
    "git", "pytest", "pip", "pip3", "cargo", "go", "dotnet",
}
ALLOWED_APPS = {
    "notepad", "notepad.exe", "calc", "calc.exe", "explorer", "explorer.exe",
    "code", "code.exe", "python", "python.exe", "python3", "py",
}
SENSITIVE_PATH_MARKERS = {
    ".ssh", ".gnupg", "credentials", "password", "login data", "cookies",
    "keychain", "wallet", "private key", "id_rsa", "id_ed25519",
}
MUTATING_ACTIONS = {
    "create_folder", "write_file", "append_file", "copy_path", "move_path",
    "delete_file", "delete_folder", "open_path", "open_url", "launch_app",
    "run_command", "type_text", "hotkey", "clipboard_write",
}
ALWAYS_CONFIRM_ACTIONS = {
    "delete_file", "delete_folder", "run_command", "type_text", "hotkey",
    "clipboard_write",
}
DEFAULT_CONFIG = {
    "server_url": DEFAULT_SERVER,
    "device_name": socket.gethostname(),
    "device_id": "",
    "device_token": "",
    "pairing_code": "",
    "allow_all_drives": False,
    "full_access_enabled": False,
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def append_audit(entry):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": utc_now(), **entry}, ensure_ascii=False) + "\n")


class PearlDeviceAgent:
    def __init__(self):
        self.config = load_config()
        self.root = Tk()
        self.root.title("Pearl Device Agent")
        self.root.geometry("760x620")
        self.root.minsize(640, 500)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.stop_event = threading.Event()
        self.emergency_stop = threading.Event()
        self.worker = None
        self.ui_events = queue.Queue()

        self.server_var = StringVar(value=self.config["server_url"])
        self.name_var = StringVar(value=self.config["device_name"])
        self.status_var = StringVar(value="Stopped")
        self.pairing_var = StringVar(value=self.config.get("pairing_code") or "Not registered")
        self.full_access_var = BooleanVar(value=bool(self.config.get("full_access_enabled")))
        self.all_drives_var = BooleanVar(value=bool(self.config.get("allow_all_drives")))

        self.build_ui()
        self.root.after(100, self.process_ui_events)

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=BOTH, expand=True)

        ttk.Label(outer, text="Pearl Device Agent", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Visible local companion for approved file, app, keyboard, and development actions.",
        ).pack(anchor="w", pady=(2, 14))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        ttk.Label(form, text="PearlAI server").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.server_var).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(form, text="Device name").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.name_var).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)
        form.columnconfigure(1, weight=1)

        status_frame = ttk.LabelFrame(outer, text="Pairing and status", padding=12)
        status_frame.pack(fill="x", pady=14)
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )
        ttk.Label(status_frame, text="Pairing code:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(status_frame, textvariable=self.pairing_var, font=("Consolas", 18, "bold")).grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0)
        )
        ttk.Label(
            status_frame,
            text="Enter this code in Pearl Agent → Pair Device. Pairing codes expire after 15 minutes.",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        permissions = ttk.LabelFrame(outer, text="Local safety controls", padding=12)
        permissions.pack(fill="x")
        ttk.Checkbutton(
            permissions,
            text="Allow website Full Access jobs to run without per-file approval",
            variable=self.full_access_var,
            command=self.save_local_permissions,
        ).pack(anchor="w")
        ttk.Checkbutton(
            permissions,
            text="Allow file operations outside my home folder (all local drives)",
            variable=self.all_drives_var,
            command=self.confirm_all_drives,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            permissions,
            text=(
                "Delete, command execution, keyboard automation, and clipboard changes still receive local confirmation. "
                "Credential stores and private-key locations are blocked."
            ),
            wraplength=700,
        ).pack(anchor="w", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=14)
        self.start_button = ttk.Button(buttons, text="Start Agent", command=self.start)
        self.start_button.pack(side=LEFT)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side=LEFT, padx=(8, 0))
        ttk.Button(buttons, text="EMERGENCY STOP", command=self.trigger_emergency_stop).pack(side=RIGHT)

        log_frame = ttk.LabelFrame(outer, text="Activity and audit log", padding=8)
        log_frame.pack(fill=BOTH, expand=True)
        self.log_text = __import__("tkinter").Text(log_frame, height=14, state="disabled", wrap="word")
        self.log_text.pack(fill=BOTH, expand=True)

    def log(self, message):
        self.ui_events.put(("log", f"{datetime.now().strftime('%H:%M:%S')}  {message}"))

    def set_status(self, message):
        self.ui_events.put(("status", message))

    def process_ui_events(self):
        try:
            while True:
                event = self.ui_events.get_nowait()
                kind, payload = event[0], event[1]
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert(END, payload + "\n")
                    self.log_text.see(END)
                    self.log_text.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "pairing":
                    self.pairing_var.set(payload)
                elif kind == "confirm":
                    prompt, response_event, response_holder = payload
                    response_holder["approved"] = messagebox.askyesno("Pearl Agent approval", prompt)
                    response_event.set()
        except queue.Empty:
            pass
        self.root.after(100, self.process_ui_events)

    def save_local_permissions(self):
        self.config["full_access_enabled"] = bool(self.full_access_var.get())
        self.config["allow_all_drives"] = bool(self.all_drives_var.get())
        save_config(self.config)

    def confirm_all_drives(self):
        if self.all_drives_var.get():
            approved = messagebox.askyesno(
                "Allow all local drives?",
                "This lets approved Pearl Agent jobs modify files outside your home folder. "
                "Credential and private-key locations remain blocked. Enable this?",
            )
            if not approved:
                self.all_drives_var.set(False)
        self.save_local_permissions()

    def confirm(self, prompt):
        response_event = threading.Event()
        response_holder = {"approved": False}
        self.ui_events.put(("confirm", (prompt, response_event, response_holder)))
        while not response_event.wait(0.2):
            if self.stop_event.is_set() or self.emergency_stop.is_set():
                return False
        return response_holder["approved"]

    @property
    def server_url(self):
        return str(self.config.get("server_url") or DEFAULT_SERVER).strip().rstrip("/")

    def headers(self):
        return {"Authorization": f"Bearer {self.config.get('device_token', '')}"}

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self.config["server_url"] = self.server_var.get().strip().rstrip("/") or DEFAULT_SERVER
        self.config["device_name"] = self.name_var.get().strip() or socket.gethostname()
        self.save_local_permissions()
        save_config(self.config)
        self.stop_event.clear()
        self.emergency_stop.clear()
        self.worker = threading.Thread(target=self.run_loop, daemon=True)
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

    def stop(self):
        self.stop_event.set()
        self.set_status("Stopping")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def trigger_emergency_stop(self):
        self.emergency_stop.set()
        self.stop_event.set()
        self.set_status("EMERGENCY STOPPED")
        self.log("Emergency stop activated. No further jobs will run.")
        append_audit({"event": "emergency_stop"})
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def close(self):
        self.stop_event.set()
        self.root.destroy()

    def register(self):
        response = requests.post(
            f"{self.server_url}/api/device/register",
            json={
                "name": self.config["device_name"],
                "platform": f"{platform.system()} {platform.release()}",
                "version": APP_VERSION,
                "capabilities": [
                    "files", "folders", "approved_commands", "open_app", "open_url",
                    "keyboard" if pyautogui else "keyboard_unavailable",
                    "screenshot" if pyautogui else "screenshot_unavailable",
                ],
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        self.config["device_id"] = data["device_id"]
        self.config["device_token"] = data["device_token"]
        self.config["pairing_code"] = data["pairing_code"]
        save_config(self.config)
        self.ui_events.put(("pairing", data["pairing_code"]))
        self.log("Device registered. Pair it from the Pearl Agent web interface.")

    def run_loop(self):
        self.set_status("Connecting")
        self.log(f"Connecting to {self.server_url}")
        while not self.stop_event.is_set():
            try:
                if not self.config.get("device_token"):
                    self.register()

                response = requests.post(
                    f"{self.server_url}/api/device/poll",
                    headers=self.headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code == 401:
                    self.log("Device registration expired or was removed; registering again.")
                    self.config["device_id"] = ""
                    self.config["device_token"] = ""
                    self.config["pairing_code"] = ""
                    save_config(self.config)
                    continue
                response.raise_for_status()
                data = response.json()
                if not data.get("paired"):
                    self.set_status("Waiting for pairing")
                else:
                    self.set_status("Online")
                    self.ui_events.put(("pairing", "Paired"))

                job = data.get("job")
                if job:
                    self.execute_job(job)
            except requests.RequestException as exc:
                self.set_status("Connection error")
                self.log(f"Connection error: {exc}")
            except Exception as exc:
                self.set_status("Agent error")
                self.log(f"Agent error: {exc}")
                append_audit({"event": "agent_error", "error": str(exc)})

            self.stop_event.wait(POLL_SECONDS)

        if not self.emergency_stop.is_set():
            self.set_status("Stopped")

    def resolve_path(self, raw_path, must_exist=False):
        raw_path = str(raw_path or "").strip()
        if not raw_path:
            path = Path.home()
        else:
            expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))
            path = expanded if expanded.is_absolute() else Path.home() / expanded
        path = path.resolve(strict=False)

        lowered = {part.lower() for part in path.parts}
        if any(marker in lowered or marker in str(path).lower() for marker in SENSITIVE_PATH_MARKERS):
            raise PermissionError("Sensitive credential or private-key locations are blocked.")

        if not self.config.get("allow_all_drives", False):
            try:
                path.relative_to(Path.home().resolve())
            except ValueError as exc:
                raise PermissionError("Path is outside the allowed home-folder scope.") from exc
        if must_exist and not path.exists():
            raise FileNotFoundError(path)
        return path

    def operation_needs_confirmation(self, operation, job_permission):
        action = operation.get("type")
        if action in ALWAYS_CONFIRM_ACTIONS:
            return True
        if action not in MUTATING_ACTIONS:
            return False
        return not (job_permission == "full" and self.config.get("full_access_enabled", False))

    def describe_operation(self, operation):
        action = operation.get("type", "unknown")
        target = operation.get("path") or operation.get("url") or operation.get("app") or ""
        if action == "run_command":
            target = " ".join(operation.get("command") or [])
        return f"{action}: {target}".strip()

    def execute_job(self, job):
        job_id = job["job_id"]
        permission = job.get("permission", "default")
        operations = job.get("operations") or []
        results = []
        audit = []
        status = "completed"
        error_message = ""
        self.log(f"Starting job {job_id} with {len(operations)} operation(s).")

        for operation in operations:
            if self.stop_event.is_set() or self.emergency_stop.is_set():
                status = "cancelled"
                break

            description = self.describe_operation(operation)
            approved = True
            if self.operation_needs_confirmation(operation, permission):
                approved = self.confirm(f"Allow this operation?\n\n{description}")
            if not approved:
                result = {"operation": description, "status": "denied"}
                results.append(result)
                audit.append(result)
                self.log(f"Denied: {description}")
                continue

            try:
                output = self.execute_operation(operation)
                result = {"operation": description, "status": "completed", "output": output}
                results.append(result)
                audit.append(result)
                self.log(f"Completed: {description}")
            except Exception as exc:
                result = {"operation": description, "status": "failed", "error": str(exc)}
                results.append(result)
                audit.append(result)
                self.log(f"Failed: {description} — {exc}")
                status = "failed"
                error_message = str(exc)
                break

        append_audit({"event": "job", "job_id": job_id, "status": status, "audit": audit})
        try:
            response = requests.post(
                f"{self.server_url}/api/device/result",
                headers=self.headers(),
                json={
                    "job_id": job_id,
                    "status": status,
                    "results": results,
                    "audit": audit,
                    "error": error_message,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            self.log(f"Could not report job result: {exc}")

    def execute_operation(self, operation):
        action = operation["type"]

        if action == "list_directory":
            path = self.resolve_path(operation.get("path"), must_exist=True)
            entries = []
            for index, child in enumerate(path.iterdir()):
                if index >= MAX_LIST_ENTRIES:
                    entries.append("... truncated")
                    break
                entries.append(f"{'folder' if child.is_dir() else 'file'}: {child.name}")
            return "\n".join(entries)

        if action == "read_file":
            path = self.resolve_path(operation.get("path"), must_exist=True)
            return path.read_text(encoding="utf-8", errors="replace")[:MAX_READ_CHARS]

        if action == "create_folder":
            path = self.resolve_path(operation.get("path"))
            path.mkdir(parents=True, exist_ok=True)
            return str(path)

        if action in {"write_file", "append_file"}:
            path = self.resolve_path(operation.get("path"))
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if action == "append_file" else "w"
            with path.open(mode, encoding="utf-8", newline="") as handle:
                handle.write(str(operation.get("content") or ""))
            return str(path)

        if action in {"copy_path", "move_path"}:
            source = self.resolve_path(operation.get("path"), must_exist=True)
            destination = self.resolve_path(operation.get("destination"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if action == "move_path":
                shutil.move(str(source), str(destination))
            elif source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            return str(destination)

        if action == "delete_file":
            path = self.resolve_path(operation.get("path"), must_exist=True)
            if path.is_dir():
                raise IsADirectoryError(path)
            path.unlink()
            return str(path)

        if action == "delete_folder":
            path = self.resolve_path(operation.get("path"), must_exist=True)
            if path == Path.home().resolve() or path.anchor == str(path):
                raise PermissionError("Refusing to delete a home or drive root.")
            shutil.rmtree(path)
            return str(path)

        if action == "open_path":
            path = self.resolve_path(operation.get("path"), must_exist=True)
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return str(path)

        if action == "open_url":
            url = str(operation.get("url") or "")
            if not url.startswith(("https://", "http://")):
                raise ValueError("Only HTTP and HTTPS URLs are allowed.")
            webbrowser.open(url)
            return url

        if action == "launch_app":
            app = str(operation.get("app") or "").strip()
            if app.lower() not in ALLOWED_APPS:
                raise PermissionError("Application is not in the local allowlist.")
            executable = shutil.which(app)
            if executable:
                subprocess.Popen([executable])
            elif sys.platform == "win32" and app.lower() in {"notepad", "calc", "explorer"}:
                subprocess.Popen([f"{app}.exe"])
            else:
                raise PermissionError("Application is not in the local approved/installed list.")
            return app

        if action == "run_command":
            command = operation.get("command") or []
            if not isinstance(command, list) or not command:
                raise ValueError("Command must be a non-empty argument list.")
            executable_value = str(command[0])
            if "/" in executable_value or "\\" in executable_value:
                raise PermissionError("Commands must use an allowlisted executable name, not a path.")
            executable_name = executable_value.lower()
            if executable_name not in ALLOWED_COMMANDS:
                raise PermissionError(f"Command is not allowlisted: {executable_name}")
            executable = shutil.which(executable_value)
            if not executable:
                raise FileNotFoundError(f"Command is not installed: {executable_value}")
            cwd = self.resolve_path(operation.get("cwd") or str(Path.home()), must_exist=True)
            completed = subprocess.run(
                [executable, *[str(value) for value in command[1:]]],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
                shell=False,
            )
            output = (completed.stdout + "\n" + completed.stderr).strip()[:MAX_READ_CHARS]
            return f"exit={completed.returncode}\n{output}"

        if action == "type_text":
            if not pyautogui:
                raise RuntimeError("Keyboard automation requires pyautogui.")
            pyautogui.write(str(operation.get("content") or ""), interval=0.01)
            return "Text typed"

        if action == "hotkey":
            if not pyautogui:
                raise RuntimeError("Keyboard automation requires pyautogui.")
            pyautogui.hotkey(*[str(key) for key in operation.get("keys") or []])
            return "Hotkey sent"

        if action == "clipboard_write":
            if not pyperclip:
                raise RuntimeError("Clipboard support requires pyperclip.")
            pyperclip.copy(str(operation.get("content") or ""))
            return "Clipboard updated"

        if action == "screenshot":
            if not pyautogui:
                raise RuntimeError("Screenshot support requires pyautogui and Pillow.")
            screenshot_dir = CONFIG_DIR / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"screenshot-{int(time.time())}.png"
            pyautogui.screenshot(str(path))
            return str(path)

        raise ValueError(f"Unsupported operation: {action}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PearlDeviceAgent().run()
