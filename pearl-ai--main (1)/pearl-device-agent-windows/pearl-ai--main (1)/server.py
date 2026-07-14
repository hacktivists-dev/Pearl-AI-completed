import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import threading
import time
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "Frontend"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
GENERATED_IMAGES_DIR = os.path.join(STATIC_DIR, "generated")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
DEVICE_STATE_FILE = os.path.join(BASE_DIR, "device_control.json")
WINDOWS_AGENT_FILE = os.path.join(BASE_DIR, "downloads", "PearlAI-Agent.exe")
ANDROID_AGENT_FILE = os.path.join(BASE_DIR, "downloads", "PearlAI-Android-Device-Agent-v2.1.apk")
DEVICE_STATE_LOCK = threading.Lock()
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = FastAPI(title="PearlAI")


@app.middleware("http")
async def prevent_stale_frontend_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/agent", "/login", "/static/script.js"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

API_TIMEOUT = int(os.getenv("API_TIMEOUT_SECONDS", "30"))
IMAGE_API_TIMEOUT = int(os.getenv("IMAGE_API_TIMEOUT_SECONDS", "180"))
MAX_CURRENT_MESSAGE_CHARS = int(os.getenv("MAX_CURRENT_MESSAGE_CHARS", "60000"))
MAX_HISTORY_CHARS = int(os.getenv("MAX_HISTORY_CHARS", "18000"))
MAX_HISTORY_MESSAGE_CHARS = int(os.getenv("MAX_HISTORY_MESSAGE_CHARS", "8000"))
DEVICE_PAIRING_TTL_SECONDS = int(os.getenv("DEVICE_PAIRING_TTL_SECONDS", "900"))
DEVICE_JOB_TTL_SECONDS = int(os.getenv("DEVICE_JOB_TTL_SECONDS", "86400"))


def env_value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DEBUG_PROVIDERS = env_value("DEBUG_PROVIDERS", "false").lower() in {"1", "true", "yes"}
COOKIE_SECURE = env_value("COOKIE_SECURE", "true").lower() in {"1", "true", "yes"}
SESSION_COOKIE = "pearl_session"
SESSION_TTL_SECONDS = int(env_value("SESSION_TTL_SECONDS", "604800"))
SESSION_SECRET = env_value("SESSION_SECRET")
if not SESSION_SECRET:
    SESSION_SECRET = secrets.token_urlsafe(48)
    print("Warning: SESSION_SECRET is not configured; sessions will reset when the app restarts.")


def looks_like_xai_key(api_key: str) -> bool:
    return api_key.startswith("xai")


def normalized_xai_key(api_key: str) -> str:
    if api_key.startswith("xai-"):
        return api_key
    if api_key.startswith("xai") and len(api_key) > 3:
        return f"xai-{api_key[3:]}"
    return api_key


def looks_like_openrouter_key(api_key: str) -> bool:
    return api_key.startswith("sk-or-")


def looks_like_openai_key(api_key: str) -> bool:
    return api_key.startswith("sk-") and not looks_like_openrouter_key(api_key)


def looks_like_gemini_key(api_key: str) -> bool:
    return api_key.startswith("AIza")


GROQ_API_KEY = env_value("GROQ_API_KEY")
GEMINI_API_KEY = env_value("GEMINI_API_KEY")
MISTRAL_API_KEY = env_value("MISTRAL_API_KEY")
OPENROUTER_API_KEY = env_value("OPENROUTER_API_KEY")
VIRUSTOTAL_API_KEY = env_value("VIRUSTOTAL_API_KEY")
SHODAN_API_KEY = env_value("SHODAN_API_KEY")
XAI_API_KEY = env_value("XAI_API_KEY", normalized_xai_key(GROQ_API_KEY) if looks_like_xai_key(GROQ_API_KEY) else "")
OPENAI_API_KEY = env_value("OPENAI_API_KEY", OPENROUTER_API_KEY if looks_like_openai_key(OPENROUTER_API_KEY) else "")

GROQ_TEXT_MODEL = env_value("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = env_value("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GEMINI_TEXT_MODEL = env_value("GEMINI_TEXT_MODEL", "gemini-3.5-flash")
GEMINI_VISION_MODEL = env_value("GEMINI_VISION_MODEL", GEMINI_TEXT_MODEL)
MISTRAL_TEXT_MODEL = env_value("MISTRAL_TEXT_MODEL", "mistral-small-latest")
MISTRAL_VISION_MODEL = env_value("MISTRAL_VISION_MODEL", MISTRAL_TEXT_MODEL)
OPENROUTER_TEXT_MODEL = env_value("OPENROUTER_TEXT_MODEL", "openrouter/free")
OPENROUTER_VISION_MODEL = env_value("OPENROUTER_VISION_MODEL", OPENROUTER_TEXT_MODEL)
XAI_TEXT_MODEL = env_value("XAI_TEXT_MODEL", "grok-4.3")
XAI_VISION_MODEL = env_value("XAI_VISION_MODEL", XAI_TEXT_MODEL)
OPENAI_TEXT_MODEL = env_value("OPENAI_TEXT_MODEL", "gpt-5.4-mini")
OPENAI_VISION_MODEL = env_value("OPENAI_VISION_MODEL", OPENAI_TEXT_MODEL)
NANO_BANANA_IMAGE_MODEL = env_value("NANO_BANANA_IMAGE_MODEL", env_value("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"))
NANO_BANANA_IMAGE_SIZE = env_value("NANO_BANANA_IMAGE_SIZE", "2K").upper()
NANO_BANANA_IMAGE_ASPECT_RATIO = env_value("NANO_BANANA_IMAGE_ASPECT_RATIO", "auto").lower()
NANO_BANANA_IMAGE_MIME_TYPE = env_value("NANO_BANANA_IMAGE_MIME_TYPE", "").lower()

groq_client = AsyncGroq(api_key=GROQ_API_KEY) if AsyncGroq and GROQ_API_KEY and not looks_like_xai_key(GROQ_API_KEY) else None


def can_use_xai() -> bool:
    return bool(XAI_API_KEY and XAI_API_KEY.startswith("xai-"))


def can_use_groq() -> bool:
    return bool(GROQ_API_KEY and AsyncGroq and groq_client and not looks_like_xai_key(GROQ_API_KEY))


def can_use_gemini() -> bool:
    return bool(GEMINI_API_KEY and looks_like_gemini_key(GEMINI_API_KEY))


def can_use_mistral() -> bool:
    return bool(MISTRAL_API_KEY)


def can_use_openai() -> bool:
    return bool(OPENAI_API_KEY and looks_like_openai_key(OPENAI_API_KEY))


def can_use_openrouter() -> bool:
    return bool(OPENROUTER_API_KEY and looks_like_openrouter_key(OPENROUTER_API_KEY))


class ProviderError(RuntimeError):
    pass


def require_key(provider: str, api_key: str) -> None:
    if not api_key:
        raise ProviderError(f"{provider} API key is not configured")


def require_groq() -> None:
    require_key("Groq", GROQ_API_KEY)
    if looks_like_xai_key(GROQ_API_KEY):
        raise ProviderError("GROQ_API_KEY is an xAI key, so the xAI provider will use it instead")
    if AsyncGroq is None:
        raise ProviderError("Groq package is not installed")
    if groq_client is None:
        raise ProviderError("Groq client is not available")


def response_error_message(response: requests.Response) -> str:
    message = response.text.strip()
    try:
        error_json = response.json()
    except ValueError:
        return message

    if isinstance(error_json, dict):
        error_value = error_json.get("error")
        if isinstance(error_value, dict):
            return str(error_value.get("message") or error_value.get("type") or message)
        if isinstance(error_value, str):
            return error_value

        detail_value = error_json.get("detail")
        if isinstance(detail_value, str):
            return detail_value
        if isinstance(detail_value, list):
            return json.dumps(detail_value)

        message_value = error_json.get("message")
        if isinstance(message_value, str):
            return message_value

    return message


def request_json(provider: str, method: str, url: str, **kwargs) -> dict:
    try:
        response = requests.request(method, url, timeout=API_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ProviderError(f"{provider} request failed: {exc}") from exc

    if response.status_code >= 400:
        message = response_error_message(response)
        raise ProviderError(f"{provider} returned HTTP {response.status_code}: {message[:300]}")

    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider} returned invalid JSON") from exc


def request_json_with_timeout(provider: str, method: str, url: str, timeout: int, **kwargs) -> dict:
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise ProviderError(f"{provider} request failed: {exc}") from exc

    if response.status_code >= 400:
        message = response_error_message(response)
        raise ProviderError(f"{provider} returned HTTP {response.status_code}: {message[:300]}")

    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider} returned invalid JSON") from exc


def unique_values(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def is_nano_banana_model(model: str) -> bool:
    return model.startswith("gemini-") and "image" in model


def image_generation_fallback_error(exc: Exception) -> bool:
    text = str(exc).lower()
    if any(marker in text for marker in ("content policy", "safety system", "safety", "blocked", "prohibited")):
        return False
    return any(
        marker in text
        for marker in (
            "model",
            "not found",
            "not available",
            "does not exist",
            "unsupported",
            "deprecat",
            "permission",
            "not enabled",
            "parameter",
            "size",
            "aspect",
            "mime",
            "response_format",
        )
    )


def model_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "model",
            "not found",
            "not available",
            "does not exist",
            "unsupported",
            "deprecat",
        )
    )


def extract_chat_completion_text(provider: str, data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError(f"{provider} returned no choices")

    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        raise ProviderError(f"{provider} returned an empty message")
    return content.strip()


def extract_gemini_text(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise ProviderError("Gemini returned no candidates")

    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text.strip():
        finish_reason = candidates[0].get("finishReason", "unknown")
        raise ProviderError(f"Gemini returned an empty response, finish reason: {finish_reason}")
    return text.strip()


def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            print(f"Warning: error loading users.json: {exc}")
    return {}


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)


def default_device_state() -> dict:
    return {"devices": {}, "jobs": {}, "claims": {}, "app_sessions": {}}


def load_device_state_unlocked() -> dict:
    if not os.path.exists(DEVICE_STATE_FILE):
        return default_device_state()
    try:
        with open(DEVICE_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            return default_device_state()
        state.setdefault("devices", {})
        state.setdefault("jobs", {})
        state.setdefault("claims", {})
        state.setdefault("app_sessions", {})
        return state
    except (OSError, ValueError) as exc:
        print(f"Warning: error loading device control state: {exc}")
        return default_device_state()


def save_device_state_unlocked(state: dict) -> None:
    temp_path = f"{DEVICE_STATE_FILE}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(temp_path, DEVICE_STATE_FILE)


def clean_device_state_unlocked(state: dict) -> None:
    now = int(time.time())
    expired_jobs = [
        job_id
        for job_id, job in state["jobs"].items()
        if now - int(job.get("created_at", now)) > DEVICE_JOB_TTL_SECONDS
    ]
    for job_id in expired_jobs:
        state["jobs"].pop(job_id, None)

    expired_unpaired_devices = [
        device_id
        for device_id, device in state["devices"].items()
        if not device.get("user_email")
        and int(device.get("pair_expires_at", 0)) < now
    ]
    for device_id in expired_unpaired_devices:
        state["devices"].pop(device_id, None)

    expired_claims = [
        claim_id
        for claim_id, claim in state["claims"].items()
        if int(claim.get("expires_at", 0)) < now or claim.get("used")
    ]
    for claim_id in expired_claims:
        state["claims"].pop(claim_id, None)

    expired_app_sessions = [
        session_id
        for session_id, session in state["app_sessions"].items()
        if int(session.get("expires_at", 0)) < now or session.get("used")
    ]
    for session_id in expired_app_sessions:
        state["app_sessions"].pop(session_id, None)


def token_digest(token: str) -> str:
    return hmac.new(
        SESSION_SECRET.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def device_from_request(request: Request, state: dict) -> Tuple[Optional[str], Optional[dict]]:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None, None
    supplied_token = authorization.split(" ", 1)[1].strip()
    supplied_digest = token_digest(supplied_token)
    for device_id, device in state["devices"].items():
        stored_digest = str(device.get("token_digest") or "")
        if stored_digest and hmac.compare_digest(stored_digest, supplied_digest):
            return device_id, device
    return None, None


def hash_password(password: str) -> str:
    iterations = 310_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored_password: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = stored_password.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("ascii"),
            int(iterations_text),
        ).hex()
        return hmac.compare_digest(digest, expected_digest)
    except (TypeError, ValueError):
        return False


def create_session_token(email: str) -> str:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = base64.urlsafe_b64encode(f"{email}\n{expires_at}".encode("utf-8")).decode("ascii").rstrip("=")
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def session_email(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        payload, supplied_signature = token.rsplit(".", 1)
        expected_signature = hmac.new(
            SESSION_SECRET.encode("utf-8"),
            payload.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None

        padded_payload = payload + "=" * (-len(payload) % 4)
        email, expires_at_text = base64.urlsafe_b64decode(padded_payload).decode("utf-8").split("\n", 1)
        if int(expires_at_text) < int(time.time()) or email not in MOCK_USERS_DB:
            return None
        return email
    except (ValueError, UnicodeDecodeError):
        return None


def set_session_cookie(response: Response, email: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(email),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


class LoginInput(BaseModel):
    name: Optional[str] = None
    email: str
    password: str


class Message(BaseModel):
    role: str
    content: str


class ChatInput(BaseModel):
    message: str = ""
    history: List[Message] = Field(default_factory=list)
    image: Optional[str] = None


class AgentInput(ChatInput):
    workspace: str = ""
    permission: str = "default"
    target: str = "workspace"
    device_id: str = ""


PEARL_CREATOR_REPLY = "I was created by Sayak Biswas and Swarapradip Paul"


def is_creator_identity_question(message: str) -> bool:
    normalized = "".join(
        character.lower() if character.isalnum() else " "
        for character in message
    )
    text = " ".join(normalized.split())
    if not text:
        return False

    subject_terms = (
        "pearl ai",
        "pearlai",
        "pearl",
        "you",
        "your",
        "this ai",
        "this assistant",
        "the ai",
    )
    creator_terms = (
        "created",
        "creator",
        "made",
        "maker",
        "built",
        "builder",
        "developed",
        "developer",
        "founded",
        "founder",
        "designed",
        "invented",
        "owner",
        "behind",
        "who create",
        "who creates",
        "who make",
        "who makes",
        "who build",
        "who builds",
        "who develop",
        "who develops",
    )
    question_terms = ("who", "whose", "what", "tell me", "name", "credit")

    return (
        any(subject in text for subject in subject_terms)
        and any(term in text for term in creator_terms)
        and any(term in text for term in question_terms)
    )


class DeviceRegisterInput(BaseModel):
    name: str = "Pearl Device"
    platform: str = "unknown"
    version: str = "1"
    capabilities: List[str] = Field(default_factory=list)


class DeviceClaimInput(DeviceRegisterInput):
    claim_token: str


class DevicePairInput(BaseModel):
    pairing_code: str


class DeviceJobInput(BaseModel):
    device_id: str
    permission: str = "default"
    operations: List[dict] = Field(default_factory=list)


class DeviceResultInput(BaseModel):
    job_id: str
    status: str
    results: List[dict] = Field(default_factory=list)
    audit: List[dict] = Field(default_factory=list)
    error: str = ""


MOCK_USERS_DB = load_users()


def scan_virustotal(target: str) -> str:
    if not VIRUSTOTAL_API_KEY:
        return "VirusTotal API key is not configured. Set VIRUSTOTAL_API_KEY and restart the server."
    target = target.strip()
    if not target:
        return "Please provide a URL, domain, IP address, or file hash to scan."

    headers = {"x-apikey": VIRUSTOTAL_API_KEY}
    try:
        if target.startswith(("http://", "https://")):
            url_id = base64.urlsafe_b64encode(target.encode("utf-8")).decode("ascii").strip("=")
            endpoint = f"https://www.virustotal.com/api/v3/urls/{url_id}"
            data = request_json("VirusTotal", "GET", endpoint, headers=headers)
            stats = (data.get("data") or {}).get("attributes", {}).get("last_analysis_stats", {})
        else:
            endpoint = "https://www.virustotal.com/api/v3/search"
            data = request_json("VirusTotal", "GET", endpoint, headers=headers, params={"query": target})
            results = data.get("data") or []
            stats = results[0].get("attributes", {}).get("last_analysis_stats", {}) if results else {}
    except ProviderError as exc:
        if "HTTP 404" in str(exc):
            return f"No scan history was found for `{target}`."
        return f"VirusTotal API error: {exc}"

    if not stats:
        return f"No scan history or threat stats were found for `{target}`."

    malicious = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless = stats.get("harmless", 0)

    result = f"**VirusTotal Scan Report for `{target}`:**\n\n"
    if malicious > 0:
        return result + f"**Alert:** {malicious} engines flagged this as malicious."
    if suspicious > 0:
        return result + f"**Warning:** {suspicious} engines flagged this as suspicious."
    return result + f"**Clean:** No engines detected threats. Harmless count: {harmless}."


def scan_shodan(target: str) -> str:
    if not SHODAN_API_KEY:
        return "Shodan API key is not configured. Set SHODAN_API_KEY and restart the server."
    target = target.strip()
    if not target:
        return "Please provide a domain or IP address to scan."

    try:
        clean_target = urlparse(target).netloc if target.startswith(("http://", "https://")) else target
        clean_target = clean_target.split("/")[0]
        ip_address = socket.gethostbyname(clean_target)
    except socket.gaierror:
        return f"Could not resolve `{target}` to an IP address."

    endpoint = f"https://api.shodan.io/shodan/host/{ip_address}"
    try:
        data = request_json("Shodan", "GET", endpoint, params={"key": SHODAN_API_KEY})
    except ProviderError as exc:
        if "HTTP 404" in str(exc):
            return f"No info was found in Shodan for `{clean_target}` (IP: {ip_address})."
        return f"Shodan API error: {exc}"

    org = data.get("org") or "Unknown"
    os_info = data.get("os") or "Unknown"
    ports = data.get("ports") or []
    vulns = data.get("vulns") or []
    result = (
        f"**Shodan Report for `{clean_target}` (IP: {ip_address}):**\n\n"
        f"**Org:** {org}\n"
        f"**OS:** {os_info}\n"
        f"**Ports:** {', '.join(map(str, ports)) if ports else 'None'}\n"
    )
    if vulns:
        result += f"\n**CVEs Detected:** {len(vulns)}\n" + ", ".join(list(vulns)[:5])
    else:
        result += "\nNo known vulnerabilities were returned by Shodan."
    return result


def call_openai_compatible_chat(
    provider: str,
    api_key: str,
    endpoint: str,
    models: List[str],
    messages: List[dict],
    token_field: str = "max_tokens",
    extra_headers: Optional[dict] = None,
    max_tokens: int = 1024,
) -> str:
    require_key(provider, api_key)
    errors = []

    for model in unique_values(models):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        body = {
            "model": model,
            "messages": messages,
            token_field: max_tokens,
        }
        try:
            data = request_json(provider, "POST", endpoint, headers=headers, json=body)
            return extract_chat_completion_text(provider, data)
        except ProviderError as exc:
            errors.append(f"{model}: {exc}")
            if not model_error(exc):
                break

    raise ProviderError("; ".join(errors))


async def call_groq_text(messages: List[dict], max_tokens: int = 1024) -> str:
    require_groq()
    completion = await groq_client.chat.completions.create(
        model=GROQ_TEXT_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=max_tokens,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ProviderError("Groq returned an empty response")
    return content


def call_xai_text(messages: List[dict], max_tokens: int = 1024) -> str:
    return call_openai_compatible_chat(
        "xAI",
        XAI_API_KEY,
        "https://api.x.ai/v1/chat/completions",
        [XAI_TEXT_MODEL, "grok-4.3", "latest"],
        messages,
        max_tokens=max_tokens,
    )


def call_openai_text(messages: List[dict], max_tokens: int = 1024) -> str:
    return call_openai_compatible_chat(
        "OpenAI",
        OPENAI_API_KEY,
        "https://api.openai.com/v1/chat/completions",
        [OPENAI_TEXT_MODEL, "gpt-5.4-mini", "gpt-5.5", "gpt-4.1-mini", "gpt-4o-mini"],
        messages,
        token_field="max_completion_tokens",
        max_tokens=max_tokens,
    )


def gemini_contents(messages: List[dict], img: Optional[str] = None) -> Tuple[Optional[str], List[dict]]:
    system_instruction = None
    contents = []

    for index, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content") or ""
        if role == "system":
            system_instruction = content
            continue

        parts = [{"text": content or "Analyze the image."}]
        if img and index == len(messages) - 1:
            b64_data = img.split(",", 1)[1] if "," in img else img
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64_data}})

        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": parts,
            }
        )

    return system_instruction, contents


def call_gemini_text(messages: List[dict], max_tokens: int = 1024) -> str:
    require_key("Gemini", GEMINI_API_KEY)
    system_instruction, contents = gemini_contents(messages)
    payload = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    errors = []
    for model in unique_values([GEMINI_TEXT_MODEL, "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]):
        try:
            data = request_json(
                "Gemini",
                "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            return extract_gemini_text(data)
        except ProviderError as exc:
            errors.append(f"{model}: {exc}")
            if not model_error(exc):
                break
    raise ProviderError("; ".join(errors))


def call_mistral_text(messages: List[dict], max_tokens: int = 1024) -> str:
    require_key("Mistral", MISTRAL_API_KEY)
    errors = []
    for model in unique_values([MISTRAL_TEXT_MODEL, "mistral-small-latest", "mistral-medium-latest"]):
        try:
            data = request_json(
                "Mistral",
                "POST",
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "max_tokens": max_tokens},
            )
            return extract_chat_completion_text("Mistral", data)
        except ProviderError as exc:
            errors.append(f"{model}: {exc}")
            if not model_error(exc):
                break
    raise ProviderError("; ".join(errors))


def call_openrouter_text(messages: List[dict], max_tokens: int = 1024) -> str:
    require_key("OpenRouter", OPENROUTER_API_KEY)
    if looks_like_openai_key(OPENROUTER_API_KEY):
        raise ProviderError("OPENROUTER_API_KEY is an OpenAI key, so the OpenAI provider will use it instead")
    data = request_json(
        "OpenRouter",
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-OpenRouter-Title": "PearlAI",
            "X-Title": "PearlAI",
        },
        json={"model": OPENROUTER_TEXT_MODEL, "messages": messages, "max_tokens": max_tokens},
    )
    return extract_chat_completion_text("OpenRouter", data)


async def call_groq_vision(messages: List[dict], img: str) -> str:
    require_groq()
    formatted = openai_vision_messages(messages, img)
    completion = await groq_client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=formatted,
        max_tokens=1024,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ProviderError("Groq vision returned an empty response")
    return content


def openai_vision_messages(messages: List[dict], img: str) -> List[dict]:
    formatted = []
    image_url = img if img.startswith("data:image") else f"data:image/jpeg;base64,{img}"

    for index, msg in enumerate(messages):
        if msg.get("role") == "system":
            continue
        content = [{"type": "text", "text": msg.get("content") or "Analyze the image."}]
        if index == len(messages) - 1:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        formatted.append({"role": msg.get("role", "user"), "content": content})
    return formatted


def call_xai_vision(messages: List[dict], img: str) -> str:
    return call_openai_compatible_chat(
        "xAI",
        XAI_API_KEY,
        "https://api.x.ai/v1/chat/completions",
        [XAI_VISION_MODEL, "grok-4.3", "latest"],
        openai_vision_messages(messages, img),
    )


def call_openai_vision(messages: List[dict], img: str) -> str:
    return call_openai_compatible_chat(
        "OpenAI",
        OPENAI_API_KEY,
        "https://api.openai.com/v1/chat/completions",
        [OPENAI_VISION_MODEL, "gpt-5.4-mini", "gpt-5.5", "gpt-4.1-mini", "gpt-4o-mini"],
        openai_vision_messages(messages, img),
        token_field="max_completion_tokens",
    )


def call_gemini_vision(messages: List[dict], img: str) -> str:
    require_key("Gemini", GEMINI_API_KEY)
    system_instruction, contents = gemini_contents(messages, img)
    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    errors = []
    for model in unique_values([GEMINI_VISION_MODEL, GEMINI_TEXT_MODEL, "gemini-3.5-flash", "gemini-2.5-flash"]):
        try:
            data = request_json(
                "Gemini",
                "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            return extract_gemini_text(data)
        except ProviderError as exc:
            errors.append(f"{model}: {exc}")
            if not model_error(exc):
                break
    raise ProviderError("; ".join(errors))


def call_mistral_vision(messages: List[dict], img: str) -> str:
    require_key("Mistral", MISTRAL_API_KEY)
    errors = []
    for model in unique_values([MISTRAL_VISION_MODEL, MISTRAL_TEXT_MODEL, "mistral-medium-latest", "mistral-small-latest"]):
        try:
            data = request_json(
                "Mistral",
                "POST",
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": openai_vision_messages(messages, img), "max_tokens": 1024},
            )
            return extract_chat_completion_text("Mistral", data)
        except ProviderError as exc:
            errors.append(f"{model}: {exc}")
            if not model_error(exc):
                break
    raise ProviderError("; ".join(errors))


def call_openrouter_vision(messages: List[dict], img: str) -> str:
    require_key("OpenRouter", OPENROUTER_API_KEY)
    if looks_like_openai_key(OPENROUTER_API_KEY):
        raise ProviderError("OPENROUTER_API_KEY is an OpenAI key, so the OpenAI provider will use it instead")
    data = request_json(
        "OpenRouter",
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-OpenRouter-Title": "PearlAI",
            "X-Title": "PearlAI",
        },
        json={"model": OPENROUTER_VISION_MODEL, "messages": openai_vision_messages(messages, img), "max_tokens": 1024},
    )
    return extract_chat_completion_text("OpenRouter", data)


def is_image_generation_request(message: str) -> bool:
    stripped = message.lower().strip()
    text = f" {stripped} "
    if not stripped:
        return False

    if stripped.startswith(("/image ", "/imagine ", "image:", "imagine:")):
        return True

    if stripped.startswith(("how to ", "how do i ", "how can i ", "explain ", "write code", "create code", "debug ")):
        return False

    troubleshooting_markers = (
        " can't generate ",
        " cannot generate ",
        " doesn't generate ",
        " does not generate ",
        " not generating ",
        " fix ",
        " issue ",
        " problem ",
        " broken ",
    )
    if any(marker in text for marker in troubleshooting_markers):
        return False

    image_nouns = (
        " image ",
        " images ",
        " picture ",
        " pictures ",
        " photo ",
        " photos ",
        " illustration ",
        " artwork ",
        " poster ",
        " logo ",
        " wallpaper ",
        " banner ",
        " avatar ",
        " icon ",
        " thumbnail ",
        " portrait ",
        " concept art ",
    )
    action_verbs = (
        " generate ",
        " create ",
        " make ",
        " draw ",
        " design ",
        " illustrate ",
        " render ",
        " paint ",
        " sketch ",
    )
    direct_art_actions = (" draw ", " illustrate ", " paint ", " sketch ")

    has_image_noun = any(noun in text for noun in image_nouns)
    has_action = any(verb in text for verb in action_verbs)
    if has_image_noun and has_action:
        return True

    return any(action in text for action in direct_art_actions)


def image_prompt_from_message(message: str) -> str:
    prompt = message.strip()
    lower_prompt = prompt.lower()
    for prefix in ("/image", "/imagine", "image:", "imagine:"):
        if lower_prompt.startswith(prefix):
            prompt = prompt[len(prefix):].strip(" :-\n\t")
            break
    return prompt or "Create a high-quality image."


def enhanced_image_prompt(message: str) -> str:
    prompt = image_prompt_from_message(message)
    return (
        "Create a polished, high-quality final image. Prioritize sharp details, coherent composition, "
        "professional lighting, accurate textures, and a clean finished result. "
        "Do not add visible text unless the user explicitly asks for text. "
        f"User request: {prompt}"
    )


def infer_image_aspect(prompt: str) -> str:
    text = prompt.lower()
    if any(keyword in text for keyword in ("portrait", "vertical", "phone", "mobile wallpaper", "story", "reel", "poster")):
        return "portrait"
    if any(keyword in text for keyword in ("landscape", "wide", "widescreen", "desktop wallpaper", "banner", "cover", "thumbnail", "cinematic")):
        return "landscape"
    return "square"


def nano_banana_aspect_ratio(prompt: str) -> str:
    configured = NANO_BANANA_IMAGE_ASPECT_RATIO
    valid_ratios = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
    if configured in valid_ratios:
        return configured

    text = prompt.lower()
    if any(keyword in text for keyword in ("logo", "avatar", "icon", "profile picture", "square")):
        return "1:1"
    if any(keyword in text for keyword in ("poster", "flyer", "book cover")):
        return "2:3"
    if any(keyword in text for keyword in ("phone", "mobile", "story", "reel", "vertical wallpaper")):
        return "9:16"
    if any(keyword in text for keyword in ("banner", "desktop", "widescreen", "wide", "landscape", "thumbnail", "cinematic")):
        return "16:9"
    if "portrait" in text:
        return "3:4"
    return "1:1"


def nano_banana_image_size(model: str, prompt: str) -> Optional[str]:
    if model.startswith("gemini-2.5-flash-image"):
        return None

    configured = NANO_BANANA_IMAGE_SIZE
    valid_sizes = {"0.5K", "1K", "2K", "4K"}
    if "4k" in prompt.lower() or "ultra high resolution" in prompt.lower():
        return "4K"
    if configured in valid_sizes:
        if configured == "0.5K" and "pro-image" in model:
            return "1K"
        return configured
    return "2K"


def nano_banana_image_mime_type() -> str:
    if NANO_BANANA_IMAGE_MIME_TYPE in {"image/jpeg", "image/png"}:
        return NANO_BANANA_IMAGE_MIME_TYPE
    return ""


def nano_banana_request_body(model: str, prompt: str, user_email: Optional[str]) -> dict:
    response_format = {
        "type": "image",
        "aspect_ratio": nano_banana_aspect_ratio(prompt),
    }
    requested_size = nano_banana_image_size(model, prompt)
    if requested_size:
        response_format["image_size"] = requested_size
    requested_mime_type = nano_banana_image_mime_type()
    if requested_mime_type:
        response_format["mime_type"] = requested_mime_type

    body = {
        "model": model,
        "input": [{"type": "text", "text": enhanced_image_prompt(prompt)[:32000]}],
        "response_format": response_format,
        "store": False,
    }
    if user_email:
        body["user_metadata"] = {
            "user_hash": hashlib.sha256(user_email.encode("utf-8")).hexdigest()[:32]
        }
    return body


def extension_from_mime_type(mime_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get((mime_type or "").lower(), "jpg")


def store_generated_image(image_b64: str, mime_type: str) -> Tuple[str, str]:
    extension = extension_from_mime_type(mime_type)
    filename = f"pearl-image-{int(time.time())}-{secrets.token_urlsafe(12)}.{extension}"
    path = os.path.join(GENERATED_IMAGES_DIR, filename)
    try:
        image_bytes = base64.b64decode(image_b64)
    except (ValueError, TypeError) as exc:
        raise ProviderError("Nano Banana returned invalid image data") from exc
    with open(path, "wb") as f:
        f.write(image_bytes)
    return filename, f"/static/generated/{filename}"


def extract_nano_banana_image_blocks(data: dict) -> List[dict]:
    image_blocks = []
    seen = set()

    def add_block(block: dict) -> None:
        image_data = block.get("data") or block.get("b64_json")
        image_url = block.get("uri") or block.get("url")
        key = image_url or image_data
        if not key or key in seen:
            return
        seen.add(key)
        image_blocks.append(
            {
                "data": image_data,
                "url": image_url,
                "mime_type": block.get("mime_type") or block.get("mimeType") or "image/jpeg",
            }
        )

    output_image = data.get("output_image")
    if isinstance(output_image, dict):
        add_block(output_image)

    for step in data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if step.get("type") != "model_output":
            continue
        for block in step.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                add_block(block)

    return image_blocks


def nano_banana_model_candidates(prompt: str) -> List[str]:
    text = prompt.lower()
    configured = NANO_BANANA_IMAGE_MODEL
    pro_first = any(keyword in text for keyword in ("4k", "poster", "advertisement", "ad creative", "infographic", "readable text", "exact text"))
    if pro_first and configured in {"gemini-3.1-flash-image", "gemini-3.1-flash-image-preview"}:
        return unique_values([
            "gemini-3-pro-image",
            configured,
            "gemini-3.1-flash-image",
            "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview",
            "gemini-2.5-flash-image",
        ])
    return unique_values([
        configured,
        "gemini-3.1-flash-image",
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image",
        "gemini-3-pro-image-preview",
        "gemini-2.5-flash-image",
    ])


def call_nano_banana_image_generation(prompt: str, user_email: Optional[str] = None) -> dict:
    require_key("Gemini", GEMINI_API_KEY)
    errors = []

    for model in nano_banana_model_candidates(prompt):
        body = nano_banana_request_body(model, prompt, user_email)
        try:
            data = request_json_with_timeout(
                "Nano Banana",
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                IMAGE_API_TIMEOUT,
                headers={
                    "x-goog-api-key": GEMINI_API_KEY,
                    "Content-Type": "application/json",
                },
                json=body,
            )
            generated_images = []
            response_format = body.get("response_format") or {}
            for item in extract_nano_banana_image_blocks(data):
                if item.get("data"):
                    filename, url = store_generated_image(item["data"], item.get("mime_type") or response_format.get("mime_type") or "image/jpeg")
                    generated_images.append(
                        {
                            "url": url,
                            "filename": filename,
                            "alt": image_prompt_from_message(prompt)[:200],
                            "model": model,
                            "quality": "high",
                            "size": response_format.get("image_size") or response_format.get("aspect_ratio") or "auto",
                            "format": item.get("mime_type") or response_format.get("mime_type") or "image/jpeg",
                        }
                    )
                elif item.get("url"):
                    generated_images.append(
                        {
                            "url": item["url"],
                            "filename": "",
                            "alt": image_prompt_from_message(prompt)[:200],
                            "model": model,
                            "quality": "high",
                            "size": response_format.get("image_size") or response_format.get("aspect_ratio") or "auto",
                            "format": item.get("mime_type") or response_format.get("mime_type") or "image/jpeg",
                        }
                    )

            if not generated_images:
                raise ProviderError("Nano Banana returned no image data")

            return {
                "reply": (
                    "Generated a high-quality Nano Banana image. "
                    "Use Open or Download below to view the full-resolution file."
                ),
                "images": generated_images,
            }
        except ProviderError as exc:
            errors.append(f"{model}: {exc}")
            if not image_generation_fallback_error(exc):
                break

    raise ProviderError("; ".join(errors))


async def first_successful_provider(providers: List[Tuple[str, Callable, bool]]) -> Tuple[str, str, List[str]]:
    if not providers:
        raise ProviderError("No usable AI provider keys are configured for this request")

    errors = []
    for name, provider_call, is_async in providers:
        try:
            if is_async:
                return name, await provider_call(), errors
            return name, await asyncio.to_thread(provider_call), errors
        except Exception as exc:
            error = f"{name}: {exc}"
            if DEBUG_PROVIDERS:
                print(f"Provider failed - {error}")
            errors.append(error)
    raise ProviderError("; ".join(errors))


def build_messages(data: ChatInput) -> List[dict]:
    system_prompt = {
        "role": "system",
        "content": (
            f"You are Pearl AI, a smart assistant. If asked who created Pearl AI, "
            f"who your creator is, or anything similar, answer exactly: {PEARL_CREATOR_REPLY}. "
            "You are helpful, clear, and practical. "
            "Whenever you provide code, put it in a fenced Markdown code block with a language label. "
            "When asked about Bengali festivals such as Jamai Sasthi or Durga Puja, "
            "advise checking the Bengali Panji based on Tithi to avoid inaccuracies."
        ),
    }
    history = []
    remaining_history_chars = MAX_HISTORY_CHARS
    for msg in reversed(data.history):
        if remaining_history_chars <= 0:
            break
        content = (msg.content or "").strip()
        if not content:
            continue
        content = content[-min(MAX_HISTORY_MESSAGE_CHARS, remaining_history_chars):]
        remaining_history_chars -= len(content)
        history.append(
            {
                "role": msg.role if msg.role in {"user", "assistant", "system"} else "user",
                "content": content,
            }
        )
    history.reverse()

    current_message = data.message.strip()[:MAX_CURRENT_MESSAGE_CHARS]
    return [system_prompt] + history + [{"role": "user", "content": current_message}]


def build_agent_messages(data: AgentInput) -> List[dict]:
    permission = "full" if data.permission == "full" else "default"
    target = "paired local device" if data.target == "device" else "connected browser workspace"
    system_prompt = {
        "role": "system",
        "content": (
            "You are Pearl Agent, a coding and device-work assistant. "
            "Return exactly one JSON object and no Markdown around it. "
            'The schema is {"reply":"short explanation","operations":[...]}. '
            "Workspace file operations are "
            '{"type":"create_folder","path":"relative/path"}, '
            '{"type":"write_file","path":"relative/path.ext","content":"complete file content"}, '
            '{"type":"delete_file","path":"relative/path.ext"}, and '
            '{"type":"delete_folder","path":"relative/path"}. '
            "Paired-device operations may additionally be "
            '{"type":"list_directory","path":"path"}, '
            '{"type":"read_file","path":"path"}, '
            '{"type":"append_file","path":"path","content":"text"}, '
            '{"type":"copy_path","path":"source","destination":"destination"}, '
            '{"type":"move_path","path":"source","destination":"destination"}, '
            '{"type":"open_path","path":"path"}, '
            '{"type":"open_url","url":"https://..."}, '
            '{"type":"launch_app","app":"approved application name"}, '
            '{"type":"run_command","command":["executable","arg"],"cwd":"optional path"}, '
            '{"type":"type_text","content":"text"}, '
            '{"type":"hotkey","keys":["ctrl","s"]}, '
            '{"type":"clipboard_write","content":"text"}, or '
            '{"type":"screenshot"}. '
            "All workspace paths must be relative, must not contain '..', and must stay inside the connected workspace. "
            "For device operations, use the least-powerful operation needed. Never request credential, browser-cookie, "
            "password-store, authentication-token, or private-key extraction. "
            "Use only operations supported by the selected device capabilities included in the connected-device snapshot. "
            "Android devices use a sandboxed Agent workspace and do not support desktop shell commands. "
            "When changing a file, write its complete final content. "
            "Do not invent file changes when the user only asks a question. "
            "Prefer minimal, coherent changes. "
            f"The selected permission mode is {permission}. "
            f"The selected execution target is the {target}. "
            "The client, not you, decides whether to apply or confirm operations."
        ),
    }

    history = []
    remaining_history_chars = MAX_HISTORY_CHARS
    for msg in reversed(data.history):
        if remaining_history_chars <= 0:
            break
        content = (msg.content or "").strip()
        if not content:
            continue
        content = content[-min(MAX_HISTORY_MESSAGE_CHARS, remaining_history_chars):]
        remaining_history_chars -= len(content)
        history.append(
            {
                "role": msg.role if msg.role in {"user", "assistant"} else "user",
                "content": content,
            }
        )
    history.reverse()

    workspace = data.workspace.strip()[:50000]
    user_content = data.message.strip()[:MAX_CURRENT_MESSAGE_CHARS]
    if workspace:
        user_content += f"\n\n[Connected workspace snapshot]\n{workspace}"
    return [system_prompt] + history + [{"role": "user", "content": user_content}]


def parse_agent_response(raw_response: str, target: str = "workspace") -> dict:
    text = (raw_response or "").strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1:] if first_newline >= 0 else text
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        try:
            parsed = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
        except json.JSONDecodeError:
            return {"reply": raw_response, "operations": []}

    if not isinstance(parsed, dict):
        return {"reply": raw_response, "operations": []}

    reply = str(parsed.get("reply") or "The agent prepared the requested changes.")
    operations = []
    total_content_chars = 0
    workspace_types = {"create_folder", "write_file", "delete_file", "delete_folder"}
    device_types = workspace_types | {
        "list_directory",
        "read_file",
        "append_file",
        "copy_path",
        "move_path",
        "open_path",
        "open_url",
        "launch_app",
        "run_command",
        "type_text",
        "hotkey",
        "clipboard_write",
        "screenshot",
    }
    allowed_types = device_types if target == "device" else workspace_types

    for operation in parsed.get("operations") or []:
        if not isinstance(operation, dict) or len(operations) >= 100:
            continue
        operation_type = str(operation.get("type") or "")
        if operation_type not in allowed_types:
            continue

        clean_operation = {"type": operation_type}
        if operation_type in {
            "create_folder", "write_file", "delete_file", "delete_folder",
            "list_directory", "read_file", "append_file", "copy_path",
            "move_path", "open_path",
        }:
            raw_path = str(operation.get("path") or "").replace("\\", "/").strip()
            path_parts = [part for part in raw_path.split("/") if part]
            if (
                not raw_path
                or any(part in {".", ".."} for part in path_parts)
                or len(raw_path) > 1000
                or (target != "device" and (raw_path.startswith("/") or (len(raw_path) > 1 and raw_path[1] == ":")))
            ):
                continue
            clean_operation["path"] = raw_path.strip("/") if target != "device" else raw_path

        if operation_type in {"copy_path", "move_path"}:
            destination = str(operation.get("destination") or "").replace("\\", "/").strip()
            destination_parts = [part for part in destination.split("/") if part]
            if not destination or any(part in {".", ".."} for part in destination_parts) or len(destination) > 1000:
                continue
            clean_operation["destination"] = destination

        if operation_type in {"write_file", "append_file", "type_text", "clipboard_write"}:
            content = str(operation.get("content") or "")
            remaining = max(0, 1_000_000 - total_content_chars)
            if not remaining:
                continue
            content = content[:remaining]
            total_content_chars += len(content)
            clean_operation["content"] = content

        if operation_type == "open_url":
            url = str(operation.get("url") or "").strip()
            if not url.startswith(("https://", "http://")) or len(url) > 2000:
                continue
            clean_operation["url"] = url

        if operation_type == "launch_app":
            app_name = str(operation.get("app") or "").strip()[:200]
            if not app_name:
                continue
            clean_operation["app"] = app_name

        if operation_type == "run_command":
            command = operation.get("command")
            if isinstance(command, str):
                command = [command]
            if (
                not isinstance(command, list)
                or not command
                or len(command) > 50
                or any(not isinstance(value, str) or len(value) > 2000 for value in command)
            ):
                continue
            clean_operation["command"] = command
            cwd = str(operation.get("cwd") or "").strip()
            if cwd and len(cwd) <= 1000 and ".." not in cwd.replace("\\", "/").split("/"):
                clean_operation["cwd"] = cwd

        if operation_type == "hotkey":
            keys = operation.get("keys")
            if not isinstance(keys, list) or not keys or len(keys) > 8:
                continue
            clean_operation["keys"] = [str(key).lower()[:30] for key in keys]

        operations.append(clean_operation)

    return {"reply": reply[:20000], "operations": operations}


@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "configured": {
            "xai": can_use_xai(),
            "groq": can_use_groq(),
            "gemini": can_use_gemini(),
            "mistral": can_use_mistral(),
            "openai": can_use_openai(),
            "openrouter": can_use_openrouter(),
            "virustotal": bool(VIRUSTOTAL_API_KEY),
            "shodan": bool(SHODAN_API_KEY),
        },
        "models": {
            "xai_text": XAI_TEXT_MODEL,
            "xai_vision": XAI_VISION_MODEL,
            "groq_text": GROQ_TEXT_MODEL,
            "groq_vision": GROQ_VISION_MODEL,
            "gemini_text": GEMINI_TEXT_MODEL,
            "gemini_vision": GEMINI_VISION_MODEL,
            "nano_banana_image": NANO_BANANA_IMAGE_MODEL,
            "nano_banana_image_size": NANO_BANANA_IMAGE_SIZE,
            "nano_banana_image_aspect_ratio": NANO_BANANA_IMAGE_ASPECT_RATIO,
            "mistral_text": MISTRAL_TEXT_MODEL,
            "mistral_vision": MISTRAL_VISION_MODEL,
            "openai_text": OPENAI_TEXT_MODEL,
            "openai_vision": OPENAI_VISION_MODEL,
            "openrouter_text": OPENROUTER_TEXT_MODEL,
            "openrouter_vision": OPENROUTER_VISION_MODEL,
        },
    }


@app.post("/chat")
async def chat(data: ChatInput, request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in to use Pearl AI."}, status_code=401)

    user_message = data.message.strip()
    user_message_lower = user_message.lower()

    if not user_message and not data.image:
        return {"reply": "Please enter a message first."}

    try:
        if is_creator_identity_question(user_message):
            return {"reply": PEARL_CREATOR_REPLY}

        if user_message_lower.startswith("shodan "):
            return {"reply": await asyncio.to_thread(scan_shodan, user_message[7:])}
        if user_message_lower.startswith("scan "):
            return {"reply": await asyncio.to_thread(scan_virustotal, user_message[5:])}

        if is_image_generation_request(user_message) and not data.image:
            if not can_use_gemini():
                return {
                    "reply": (
                        "High-quality Nano Banana image generation requires a valid Gemini API key. "
                        "Set GEMINI_API_KEY on the server, reload the app, then ask Pearl AI to generate the image again."
                    )
                }
            return await asyncio.to_thread(call_nano_banana_image_generation, user_message, email)

        messages = build_messages(data)
        if data.image:
            providers = []
            if can_use_openai():
                providers.append(("OpenAI Vision", lambda: call_openai_vision(messages, data.image), False))
            if can_use_xai():
                providers.append(("xAI Vision", lambda: call_xai_vision(messages, data.image), False))
            if can_use_mistral():
                providers.append(("Mistral Vision", lambda: call_mistral_vision(messages, data.image), False))
            if can_use_gemini():
                providers.append(("Gemini Vision", lambda: call_gemini_vision(messages, data.image), False))
            if can_use_groq():
                providers.append(("Groq Vision", lambda: call_groq_vision(messages, data.image), True))
            if can_use_openrouter():
                providers.append(("OpenRouter Vision", lambda: call_openrouter_vision(messages, data.image), False))
            _, reply, errors = await first_successful_provider(
                providers
            )
        else:
            providers = []
            if can_use_mistral():
                providers.append(("Mistral", lambda: call_mistral_text(messages), False))
            if can_use_openai():
                providers.append(("OpenAI", lambda: call_openai_text(messages), False))
            if can_use_xai():
                providers.append(("xAI", lambda: call_xai_text(messages), False))
            if can_use_gemini():
                providers.append(("Gemini", lambda: call_gemini_text(messages), False))
            if can_use_groq():
                providers.append(("Groq", lambda: call_groq_text(messages), True))
            if can_use_openrouter():
                providers.append(("OpenRouter", lambda: call_openrouter_text(messages), False))
            _, reply, errors = await first_successful_provider(
                providers
            )

        if errors and DEBUG_PROVIDERS:
            print("Fallbacks used before success:", " | ".join(errors))
        return {"reply": reply}
    except ProviderError as exc:
        if DEBUG_PROVIDERS:
            print(f"All providers failed: {exc}")
        if is_image_generation_request(user_message) and not data.image:
            return {
                "reply": (
                    "Pearl AI could not generate the image with Nano Banana. "
                    "Check that GEMINI_API_KEY is valid, billing/quota is available, and the selected Nano Banana model is enabled for the Gemini API."
                )
            }
        return {
            "reply": (
                "Pearl AI could not complete this request. "
                "If files or a folder were attached, try asking about a smaller subset or a specific file."
            )
        }


@app.post("/api/agent")
async def agent_task(data: AgentInput, request: Request):
    if not session_email(request):
        return JSONResponse({"detail": "Please log in to use Pearl Agent."}, status_code=401)

    if not data.message.strip() and not data.image:
        return JSONResponse({"detail": "Please describe a task first."}, status_code=400)

    if is_creator_identity_question(data.message):
        return {"reply": PEARL_CREATOR_REPLY, "operations": []}

    messages = build_agent_messages(data)
    try:
        providers = []
        if data.image:
            if can_use_openai():
                providers.append(("OpenAI Vision", lambda: call_openai_vision(messages, data.image), False))
            if can_use_xai():
                providers.append(("xAI Vision", lambda: call_xai_vision(messages, data.image), False))
            if can_use_mistral():
                providers.append(("Mistral Vision", lambda: call_mistral_vision(messages, data.image), False))
            if can_use_gemini():
                providers.append(("Gemini Vision", lambda: call_gemini_vision(messages, data.image), False))
            if can_use_groq():
                providers.append(("Groq Vision", lambda: call_groq_vision(messages, data.image), True))
            if can_use_openrouter():
                providers.append(("OpenRouter Vision", lambda: call_openrouter_vision(messages, data.image), False))
        else:
            if can_use_mistral():
                providers.append(("Mistral", lambda: call_mistral_text(messages, 4096), False))
            if can_use_openai():
                providers.append(("OpenAI", lambda: call_openai_text(messages, 4096), False))
            if can_use_xai():
                providers.append(("xAI", lambda: call_xai_text(messages, 4096), False))
            if can_use_gemini():
                providers.append(("Gemini", lambda: call_gemini_text(messages, 4096), False))
            if can_use_groq():
                providers.append(("Groq", lambda: call_groq_text(messages, 4096), True))
            if can_use_openrouter():
                providers.append(("OpenRouter", lambda: call_openrouter_text(messages, 4096), False))

        _, raw_response, errors = await first_successful_provider(providers)
        if errors and DEBUG_PROVIDERS:
            print("Agent fallbacks used before success:", " | ".join(errors))
        return parse_agent_response(raw_response, data.target)
    except ProviderError as exc:
        if DEBUG_PROVIDERS:
            print(f"Agent providers failed: {exc}")
        return {
            "reply": "Pearl Agent could not complete this task with the currently available AI providers.",
            "operations": [],
        }


@app.post("/api/device/register")
async def register_device(data: DeviceRegisterInput):
    device_id = secrets.token_urlsafe(18)
    device_token = secrets.token_urlsafe(48)
    pairing_code = f"{secrets.randbelow(100_000_000):08d}"
    now = int(time.time())
    capabilities = [
        str(capability)[:100]
        for capability in data.capabilities[:100]
        if str(capability).strip()
    ]

    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        unpaired_devices = sorted(
            (
                (existing_id, existing)
                for existing_id, existing in state["devices"].items()
                if not existing.get("user_email")
            ),
            key=lambda item: int(item[1].get("created_at", 0)),
        )
        for old_device_id, _ in unpaired_devices[:-100]:
            state["devices"].pop(old_device_id, None)
        existing_codes = {device.get("pairing_code") for device in state["devices"].values()}
        while pairing_code in existing_codes:
            pairing_code = f"{secrets.randbelow(100_000_000):08d}"
        state["devices"][device_id] = {
            "name": data.name.strip()[:120] or "Pearl Device",
            "platform": data.platform.strip()[:120] or "unknown",
            "version": data.version.strip()[:50] or "1",
            "capabilities": capabilities,
            "token_digest": token_digest(device_token),
            "pairing_code": pairing_code,
            "pair_expires_at": now + DEVICE_PAIRING_TTL_SECONDS,
            "user_email": "",
            "created_at": now,
            "last_seen": now,
            "status": "awaiting_pairing",
        }
        save_device_state_unlocked(state)

    return {
        "device_id": device_id,
        "device_token": device_token,
        "pairing_code": pairing_code,
        "pair_expires_in": DEVICE_PAIRING_TTL_SECONDS,
    }


@app.get("/api/device/download")
async def download_device_agent(request: Request, platform_name: str = "windows"):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in before downloading Pearl AI Agent."}, status_code=401)

    normalized_platform = platform_name.lower().strip()
    if normalized_platform in {"android", "apk"}:
        if not os.path.exists(ANDROID_AGENT_FILE):
            return JSONResponse(
                {"detail": "The Android Agent APK is not available on this server yet."},
                status_code=503,
            )
        return FileResponse(
            ANDROID_AGENT_FILE,
            media_type="application/vnd.android.package-archive",
            filename="PearlAI-Android-Device-Agent-v2.1.apk",
            headers={"Cache-Control": "no-store"},
        )

    if normalized_platform not in {"windows", "win", "pc"}:
        return JSONResponse(
            {
                "detail": (
                    "Pearl AI Agent downloads are currently available for Windows and Android. "
                    "iPhone/iPad do not permit unrestricted device control."
                ),
                "limited_access": True,
            },
            status_code=409,
        )
    if not os.path.exists(WINDOWS_AGENT_FILE):
        return JSONResponse({"detail": "The Windows Agent installer is not available on this server yet."}, status_code=503)

    claim_id = secrets.token_urlsafe(10)
    claim_token = secrets.token_urlsafe(32)
    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        state["claims"][claim_id] = {
            "token_digest": token_digest(claim_token),
            "user_email": email,
            "created_at": now,
            "expires_at": now + 3600,
            "used": False,
        }
        save_device_state_unlocked(state)

    filename = f"PearlAI-Agent--{claim_id}--{claim_token}.exe"
    return FileResponse(
        WINDOWS_AGENT_FILE,
        media_type="application/vnd.microsoft.portable-executable",
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/device/claim")
async def claim_downloaded_agent(data: DeviceClaimInput):
    claim_token = data.claim_token.strip()
    claim_digest = token_digest(claim_token)
    now = int(time.time())

    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        matching = [
            (claim_id, claim)
            for claim_id, claim in state["claims"].items()
            if not claim.get("used")
            and int(claim.get("expires_at", 0)) >= now
            and hmac.compare_digest(str(claim.get("token_digest") or ""), claim_digest)
        ]
        if len(matching) != 1:
            return JSONResponse({"detail": "The automatic login claim is invalid or expired."}, status_code=401)

        claim_id, claim = matching[0]
        device_id = secrets.token_urlsafe(18)
        device_token = secrets.token_urlsafe(48)
        capabilities = [
            str(capability)[:100]
            for capability in data.capabilities[:100]
            if str(capability).strip()
        ]
        state["devices"][device_id] = {
            "name": data.name.strip()[:120] or "Pearl Device",
            "platform": data.platform.strip()[:120] or "unknown",
            "version": data.version.strip()[:50] or "1",
            "capabilities": capabilities,
            "token_digest": token_digest(device_token),
            "pairing_code": "",
            "pair_expires_at": 0,
            "user_email": claim["user_email"],
            "created_at": now,
            "last_seen": now,
            "status": "online",
        }
        claim["used"] = True
        state["claims"].pop(claim_id, None)
        save_device_state_unlocked(state)

    return {
        "device_id": device_id,
        "device_token": device_token,
        "account_email": claim["user_email"],
    }


@app.post("/api/device/pair")
async def pair_device(data: DevicePairInput, request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in before pairing a device."}, status_code=401)

    pairing_code = "".join(character for character in data.pairing_code if character.isdigit())
    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        matching = [
            (device_id, device)
            for device_id, device in state["devices"].items()
            if device.get("pairing_code") == pairing_code
            and int(device.get("pair_expires_at", 0)) >= now
        ]
        if len(matching) != 1:
            return JSONResponse({"detail": "The pairing code is invalid or expired."}, status_code=404)

        device_id, device = matching[0]
        device["user_email"] = email
        device["pairing_code"] = ""
        device["pair_expires_at"] = 0
        device["status"] = "online"
        device["last_seen"] = now
        save_device_state_unlocked(state)

    return {
        "status": "paired",
        "device": {
            "id": device_id,
            "name": device["name"],
            "platform": device["platform"],
            "capabilities": device["capabilities"],
        },
    }


@app.get("/api/devices")
async def list_devices(request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in."}, status_code=401)

    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        devices = [
            {
                "id": device_id,
                "name": device.get("name", "Pearl Device"),
                "platform": device.get("platform", "unknown"),
                "version": device.get("version", ""),
                "capabilities": device.get("capabilities", []),
                "last_seen": device.get("last_seen", 0),
                "online": now - int(device.get("last_seen", 0)) < 45,
            }
            for device_id, device in state["devices"].items()
            if device.get("user_email") == email
        ]
        save_device_state_unlocked(state)
    return {"devices": devices}


@app.delete("/api/devices/{device_id}")
async def unpair_device(device_id: str, request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in."}, status_code=401)

    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        device = state["devices"].get(device_id)
        if not device or device.get("user_email") != email:
            return JSONResponse({"detail": "Device not found."}, status_code=404)
        state["devices"].pop(device_id, None)
        for job_id in [
            job_id
            for job_id, job in state["jobs"].items()
            if job.get("device_id") == device_id
        ]:
            state["jobs"].pop(job_id, None)
        save_device_state_unlocked(state)
    return {"status": "unpaired"}


@app.post("/api/device/jobs")
async def create_device_job(data: DeviceJobInput, request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in."}, status_code=401)

    sanitized = parse_agent_response(
        json.dumps({"reply": "", "operations": data.operations}),
        "device",
    )["operations"]
    if not sanitized:
        return JSONResponse({"detail": "No valid device operations were provided."}, status_code=400)

    job_id = secrets.token_urlsafe(18)
    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        device = state["devices"].get(data.device_id)
        if not device or device.get("user_email") != email:
            return JSONResponse({"detail": "The selected device is not paired to this account."}, status_code=404)
        state["jobs"][job_id] = {
            "device_id": data.device_id,
            "user_email": email,
            "permission": "full" if data.permission == "full" else "default",
            "operations": sanitized,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "results": [],
            "audit": [],
            "error": "",
        }
        save_device_state_unlocked(state)
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/device/jobs/{job_id}")
async def get_device_job(job_id: str, request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Please log in."}, status_code=401)
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        job = state["jobs"].get(job_id)
        if not job or job.get("user_email") != email:
            return JSONResponse({"detail": "Job not found."}, status_code=404)
        return {
            "job_id": job_id,
            "status": job.get("status"),
            "results": job.get("results", []),
            "audit": job.get("audit", []),
            "error": job.get("error", ""),
            "updated_at": job.get("updated_at", 0),
        }


@app.post("/api/device/poll")
async def poll_device(request: Request):
    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        device_id, device = device_from_request(request, state)
        if not device_id or not device:
            return JSONResponse({"detail": "Invalid device token."}, status_code=401)
        device["last_seen"] = now
        device["status"] = "online" if device.get("user_email") else "awaiting_pairing"

        pending_jobs = sorted(
            (
                (job_id, job)
                for job_id, job in state["jobs"].items()
                if job.get("device_id") == device_id and job.get("status") == "pending"
            ),
            key=lambda item: int(item[1].get("created_at", 0)),
        )
        job_payload = None
        if pending_jobs and device.get("user_email"):
            job_id, job = pending_jobs[0]
            job["status"] = "running"
            job["updated_at"] = now
            job_payload = {
                "job_id": job_id,
                "permission": job.get("permission", "default"),
                "operations": job.get("operations", []),
            }
        save_device_state_unlocked(state)
    return {"paired": bool(device.get("user_email")), "job": job_payload}


@app.post("/api/device/app-session")
async def create_device_app_session(request: Request):
    now = int(time.time())
    app_token = secrets.token_urlsafe(40)
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        device_id, device = device_from_request(request, state)
        if not device_id or not device or not device.get("user_email"):
            return JSONResponse({"detail": "Invalid or unpaired device token."}, status_code=401)
        state["app_sessions"][token_digest(app_token)] = {
            "user_email": device["user_email"],
            "device_id": device_id,
            "created_at": now,
            "expires_at": now + 120,
            "used": False,
        }
        device["last_seen"] = now
        save_device_state_unlocked(state)
    return {"url": f"/api/device/app-login?token={app_token}"}


@app.get("/api/device/app-login")
async def device_app_login(token: str, response: Response):
    supplied_digest = token_digest(token.strip())
    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        clean_device_state_unlocked(state)
        session = state["app_sessions"].get(supplied_digest)
        if not session or session.get("used") or int(session.get("expires_at", 0)) < now:
            return RedirectResponse("/login")
        email = session["user_email"]
        session["used"] = True
        state["app_sessions"].pop(supplied_digest, None)
        save_device_state_unlocked(state)

    redirect = RedirectResponse("/agent")
    set_session_cookie(redirect, email)
    return redirect


@app.post("/api/device/result")
async def submit_device_result(data: DeviceResultInput, request: Request):
    now = int(time.time())
    with DEVICE_STATE_LOCK:
        state = load_device_state_unlocked()
        device_id, device = device_from_request(request, state)
        if not device_id or not device:
            return JSONResponse({"detail": "Invalid device token."}, status_code=401)
        job = state["jobs"].get(data.job_id)
        if not job or job.get("device_id") != device_id:
            return JSONResponse({"detail": "Job not found."}, status_code=404)
        job["status"] = data.status if data.status in {"completed", "failed", "cancelled"} else "failed"
        job["results"] = [
            {
                "operation": str(result.get("operation") or "")[:1000],
                "status": str(result.get("status") or "")[:50],
                "output": str(result.get("output") or "")[:20000],
                "error": str(result.get("error") or "")[:5000],
            }
            for result in data.results[:200]
            if isinstance(result, dict)
        ]
        job["audit"] = [
            {
                "operation": str(entry.get("operation") or "")[:1000],
                "status": str(entry.get("status") or "")[:50],
                "error": str(entry.get("error") or "")[:2000],
            }
            for entry in data.audit[:500]
            if isinstance(entry, dict)
        ]
        job["error"] = data.error[:5000]
        job["updated_at"] = now
        device["last_seen"] = now
        save_device_state_unlocked(state)
    return {"status": "recorded"}


@app.post("/api/login")
async def api_login(data: LoginInput, response: Response):
    email = str(data.email or "").strip().lower()
    password = str(data.password or "").strip()

    if not email or not password:
        return JSONResponse(
            {"status": "error", "message": "Email and password are required."},
            status_code=400,
        )

    user = MOCK_USERS_DB.get(email)
    if user and verify_password(password, user.get("password", "")):
        set_session_cookie(response, email)
        return {
            "status": "success",
            "message": "Login successful",
            "user": {"name": user.get("name", "User"), "email": email},
        }

    return JSONResponse(
        {"status": "error", "message": "Invalid email or password."},
        status_code=401,
    )


@app.post("/api/register")
async def api_register(data: LoginInput):
    email = str(data.email or "").strip().lower()
    name = str(data.name or "").strip()
    password = str(data.password or "").strip()

    if not name:
        return JSONResponse(
            {"status": "error", "message": "Name is required for registration."},
            status_code=400,
        )
    if not email or "@" not in email:
        return JSONResponse(
            {"status": "error", "message": "A valid email is required."},
            status_code=400,
        )
    if len(password) < 8:
        return JSONResponse(
            {"status": "error", "message": "Password must be at least 8 characters."},
            status_code=400,
        )
    if email in MOCK_USERS_DB:
        return JSONResponse(
            {"status": "error", "message": "This email is already registered. Please login instead."},
            status_code=409,
        )

    MOCK_USERS_DB[email] = {"password": hash_password(password), "name": name}
    save_users(MOCK_USERS_DB)
    return {"status": "success", "message": "Account created successfully"}


@app.get("/api/me")
async def api_me(request: Request):
    email = session_email(request)
    if not email:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    user = MOCK_USERS_DB[email]
    return {"name": user.get("name", "User"), "email": email}


@app.post("/api/logout")
async def api_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "success"}


@app.get("/login")
async def serve_login(request: Request):
    if session_email(request):
        return RedirectResponse("/")
    path = os.path.join(BASE_DIR, "login.html")
    if not os.path.exists(path):
        path = os.path.join(FRONTEND_DIR, "login.html")
    return FileResponse(path)


@app.get("/")
async def serve_index(request: Request):
    if not session_email(request):
        return RedirectResponse("/login")
    path = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(path):
        path = os.path.join(FRONTEND_DIR, "index.html")
    return FileResponse(path)


@app.get("/agent")
async def serve_agent(request: Request):
    if not session_email(request):
        return RedirectResponse("/login")
    path = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(path):
        path = os.path.join(FRONTEND_DIR, "index.html")
    return FileResponse(path)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
