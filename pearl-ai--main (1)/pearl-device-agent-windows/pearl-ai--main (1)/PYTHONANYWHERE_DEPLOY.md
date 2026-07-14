# PearlAI on PythonAnywhere

This project uses FastAPI, so deploy it with PythonAnywhere's ASGI website system.

## Before deploying

1. Keep your existing `.env` file in `/home/hactivists/pearl-ai-main`.
2. Sign in to the US PythonAnywhere service at `https://www.pythonanywhere.com`.
3. Open **Account → API token** and create a token if one does not already exist.

Keep `.env`, `users.json`, and `device_control.json` on PythonAnywhere when copying updated
project files, so API keys, accounts, and device sessions are not replaced.

For image generation, PearlAI uses Nano Banana through the Gemini API. Your `.env` should include:

```env
GEMINI_API_KEY=your_gemini_api_key
NANO_BANANA_IMAGE_MODEL=gemini-3.1-flash-image
NANO_BANANA_IMAGE_SIZE=2K
NANO_BANANA_IMAGE_ASPECT_RATIO=auto
```

Use `NANO_BANANA_IMAGE_MODEL=gemini-3-pro-image` if you want the professional image model by default.

## Upload and install

Copy the project files directly into `~/pearl-ai-main`, keeping your existing `.env`,
`users.json`, and `device_control.json`. Open a Bash console:

```bash
cd ~
mkdir -p pearl-ai-main
mkvirtualenv pearl-ai --python=python3.13
cd ~/pearl-ai-main
pip install -r requirements.txt
pip install --upgrade pythonanywhere
```

## Create the website

Run this as one command:

```bash
pa website create \
  --domain hactivists.pythonanywhere.com \
  --command '/home/hactivists/.virtualenvs/pearl-ai/bin/uvicorn --app-dir /home/hactivists/pearl-ai-main --uds ${DOMAIN_SOCKET} server:app'
```

The site will be available at:

```text
https://hactivists.pythonanywhere.com
```

## Updates and diagnostics

After changing files:

```bash
pa website reload --domain hactivists.pythonanywhere.com
```

Inspect the website configuration:

```bash
pa website get --domain hactivists.pythonanywhere.com
```

Check startup errors:

```bash
tail -n 100 /var/log/hactivists.pythonanywhere.com.error.log
```

Check the health endpoint:

```text
https://hactivists.pythonanywhere.com/api/health
```

PythonAnywhere free accounts restrict outbound requests to allowlisted domains. Upgrade to a paid
account if a configured provider is blocked.
