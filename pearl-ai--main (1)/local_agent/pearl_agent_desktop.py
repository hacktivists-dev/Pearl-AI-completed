import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import requests
import webview

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


APP_VERSION = "2.0.0"
DEFAULT_SERVER = "https://hactivists.pythonanywhere.com"
CONFIG_DIR = Path.home() / ".pearl-device-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
AUDIT_FILE = CONFIG_DIR / "audit.jsonl"
WEBVIEW_STORAGE = CONFIG_DIR / "webview"
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
    "account_email": "",
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


class DesktopBridge:
    def __init__(self, agent):
        self.agent = agent

    def status(self):
        return self.agent.public_status()

    def emergency_stop(self):
        self.agent.emergency_stop.set()
        self.agent.stop_event.set()
        self.agent.status = "Emergency stopped"
        append_audit({"event": "emergency_stop"})
        return self.agent.public_status()

    def resume(self):
        self.agent.restart_polling()
        return self.agent.public_status()

    def set_local_permissions(self, full_access=False, allow_all_drives=False):
        self.agent.config["full_access_enabled"] = bool(full_access)
        self.agent.config["allow_all_drives"] = bool(allow_all_drives)
        save_config(self.agent.config)
        return self.agent.public_status()


class PearlAgentDesktop:
    def __init__(self):
        self.config = load_config()
        self.server_url = str(self.config.get("server_url") or DEFAULT_SERVER).rstrip("/")
        self.stop_event = threading.Event()
        self.emergency_stop = threading.Event()
        self.poll_thread = None
        self.window = None
        self.status = "Starting"
        self.last_error = ""
        self.bridge = DesktopBridge(self)

    def public_status(self):
        return {
            "status": self.status,
            "account_email": self.config.get("account_email", ""),
            "device_name": self.config.get("device_name", socket.gethostname()),
            "full_access_enabled": bool(self.config.get("full_access_enabled")),
            "allow_all_drives": bool(self.config.get("allow_all_drives")),
            "last_error": self.last_error,
        }

    def headers(self):
        return {"Authorization": f"Bearer {self.config.get('device_token', '')}"}

    def claim_token_from_filename(self):
        executable_name = Path(sys.executable).name if getattr(sys, "frozen", False) else Path(sys.argv[0]).name
        match = re.search(
            r"PearlAI-Agent--.+?--([A-Za-z0-9_-]+)(?:\s*\(\d+\))?\.exe$",
            executable_name,
            re.IGNORECASE,
        )
        return match.group(1) if match else ""

    def capabilities(self):
        return [
            "files", "folders", "approved_commands", "open_app", "open_url",
            "embedded_agent_ui",
            "keyboard" if pyautogui else "keyboard_unavailable",
            "screenshot" if pyautogui else "screenshot_unavailable",
        ]

    def claim_account(self):
        claim_token = self.claim_token_from_filename()
        if not claim_token:
            raise RuntimeError(
                "Automatic login information was not found. Download Pearl AI Agent again "
                "from the Agent page while signed in."
            )
        response = requests.post(
            f"{self.server_url}/api/device/claim",
            json={
                "claim_token": claim_token,
                "name": self.config.get("device_name") or socket.gethostname(),
                "platform": f"{platform.system()} {platform.release()}",
                "version": APP_VERSION,
                "capabilities": self.capabilities(),
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        self.config.update({
            "device_id": data["device_id"],
            "device_token": data["device_token"],
            "account_email": data["account_email"],
        })
        save_config(self.config)
        append_audit({"event": "account_claimed", "account": data["account_email"]})

    def app_url(self):
        response = requests.post(
            f"{self.server_url}/api/device/app-session",
            headers=self.headers(),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return f"{self.server_url}{response.json()['url']}"

    def ensure_authenticated(self):
        if not self.config.get("device_token"):
            self.claim_account()
        try:
            return self.app_url()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                self.config.update({"device_id": "", "device_token": "", "account_email": ""})
                save_config(self.config)
                self.claim_account()
                return self.app_url()
            raise

    def native_confirm(self, title, message):
        if not self.window:
            return False
        return bool(self.window.create_confirmation_dialog(title, message))

    def operation_needs_confirmation(self, operation, job_permission):
        action = operation.get("type")
        if action in ALWAYS_CONFIRM_ACTIONS:
            return True
        if action not in MUTATING_ACTIONS:
            return False
        return not (
            job_permission == "full"
            and self.config.get("full_access_enabled", False)
        )

    def describe_operation(self, operation):
        action = operation.get("type", "unknown")
        target = operation.get("path") or operation.get("url") or operation.get("app") or ""
        if action == "run_command":
            target = " ".join(operation.get("command") or [])
        return f"{action}: {target}".strip()

    def restart_polling(self):
        if self.poll_thread and self.poll_thread.is_alive() and not self.stop_event.is_set():
            return
        self.stop_event.clear()
        self.emergency_stop.clear()
        self.status = "Online"
        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()

    def poll_loop(self):
        self.status = "Connecting"
        while not self.stop_event.is_set():
            try:
                response = requests.post(
                    f"{self.server_url}/api/device/poll",
                    headers=self.headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code == 401:
                    self.status = "Disconnected"
                    self.last_error = "This installation is no longer connected. Download the Agent again."
                    return
                response.raise_for_status()
                data = response.json()
                self.status = "Online" if data.get("paired") else "Disconnected"
                self.last_error = ""
                if data.get("job"):
                    self.execute_job(data["job"])
            except requests.RequestException as exc:
                self.status = "Connection error"
                self.last_error = str(exc)
            except Exception as exc:
                self.status = "Agent error"
                self.last_error = str(exc)
                append_audit({"event": "agent_error", "error": str(exc)})
            self.stop_event.wait(POLL_SECONDS)

    def execute_job(self, job):
        job_id = job["job_id"]
        permission = job.get("permission", "default")
        operations = job.get("operations") or []
        results, audit = [], []
        status, error_message = "completed", ""

        for operation in operations:
            if self.stop_event.is_set() or self.emergency_stop.is_set():
                status = "cancelled"
                break
            description = self.describe_operation(operation)
            approved = True
            if self.operation_needs_confirmation(operation, permission):
                approved = self.native_confirm(
                    "Pearl Agent approval",
                    f"Allow this operation?\n\n{description}",
                )
            if not approved:
                result = {"operation": description, "status": "denied"}
                results.append(result)
                audit.append(result)
                continue
            try:
                output = self.execute_operation(operation)
                result = {"operation": description, "status": "completed", "output": output}
            except Exception as exc:
                result = {"operation": description, "status": "failed", "error": str(exc)}
                status, error_message = "failed", str(exc)
            results.append(result)
            audit.append(result)
            if status == "failed":
                break

        append_audit({"event": "job", "job_id": job_id, "status": status, "audit": audit})
        try:
            requests.post(
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
            ).raise_for_status()
        except requests.RequestException as exc:
            self.last_error = f"Could not report job result: {exc}"

    def resolve_path(self, raw_path, must_exist=False):
        raw_path = str(raw_path or "").strip()
        expanded = Path(os.path.expandvars(os.path.expanduser(raw_path))) if raw_path else Path.home()
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
            with path.open("a" if action == "append_file" else "w", encoding="utf-8", newline="") as handle:
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
                raise FileNotFoundError(app)
            return app
        if action == "run_command":
            command = operation.get("command") or []
            if not isinstance(command, list) or not command:
                raise ValueError("Command must be a non-empty argument list.")
            executable_value = str(command[0])
            if "/" in executable_value or "\\" in executable_value:
                raise PermissionError("Commands must use an allowlisted executable name.")
            if executable_value.lower() not in ALLOWED_COMMANDS:
                raise PermissionError(f"Command is not allowlisted: {executable_value}")
            executable = shutil.which(executable_value)
            if not executable:
                raise FileNotFoundError(executable_value)
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
                raise RuntimeError("Keyboard automation is unavailable.")
            pyautogui.write(str(operation.get("content") or ""), interval=0.01)
            return "Text typed"
        if action == "hotkey":
            if not pyautogui:
                raise RuntimeError("Keyboard automation is unavailable.")
            pyautogui.hotkey(*[str(key) for key in operation.get("keys") or []])
            return "Hotkey sent"
        if action == "clipboard_write":
            if not pyperclip:
                raise RuntimeError("Clipboard support is unavailable.")
            pyperclip.copy(str(operation.get("content") or ""))
            return "Clipboard updated"
        if action == "screenshot":
            if not pyautogui:
                raise RuntimeError("Screenshot support is unavailable.")
            screenshot_dir = CONFIG_DIR / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"screenshot-{int(time.time())}.png"
            pyautogui.screenshot(str(path))
            return str(path)
        raise ValueError(f"Unsupported operation: {action}")

    def start_background(self):
        self.restart_polling()

    def run(self):
        try:
            url = self.ensure_authenticated()
        except Exception as exc:
            message = (
                "Pearl AI Agent could not connect automatically.\n\n"
                f"{exc}\n\nDownload the Agent again from PearlAI while signed in."
            )
            self.window = webview.create_window(
                "Pearl AI Agent",
                html=f"<h2>Pearl AI Agent</h2><p>{message}</p>",
                width=900,
                height=650,
            )
            webview.start()
            return

        WEBVIEW_STORAGE.mkdir(parents=True, exist_ok=True)
        self.window = webview.create_window(
            "Pearl AI Agent",
            url,
            js_api=self.bridge,
            width=1280,
            height=820,
            min_size=(720, 520),
            confirm_close=True,
        )
        webview.start(
            self.start_background,
            private_mode=False,
            storage_path=str(WEBVIEW_STORAGE),
        )
        self.stop_event.set()


if __name__ == "__main__":
    PearlAgentDesktop().run()
