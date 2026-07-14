# Pearl Device Agent

This visible Windows companion lets a paired PearlAI account perform approved local actions.

## Install and start

1. Sign in to PearlAI in your browser.
2. Open **Agent**.
3. Choose **Download Pearl AI Agent**.
4. Run the downloaded `PearlAI-Agent--...exe` installer without renaming it.
5. Finish installation. Pearl AI Agent automatically connects to the same account using a
   one-time claim retained from that downloaded filename.
6. The application opens the complete Pearl Agent interface in its own desktop window. Users
   can chat, attach files, manage history, choose permissions, and send device tasks directly
   from the application.

No connection code is required. Do not rename the EXE before opening it for the first time.

The companion does not install itself at startup, hide in the background, or bypass operating-system permissions.

The Windows package uses a conventional installer around a directory-based executable. This avoids
the self-extracting one-file packaging pattern that triggered a Microsoft Defender machine-learning
detection in the previous build. A trusted code-signing certificate is still required to replace
Windows' **Unknown publisher** label in a public production release.

## Permission model

- **Default Access:** asks locally before changes.
- **Full Access:** automatically allows ordinary file creation and edits only when the local
  **Allow website Full Access jobs** switch is also enabled.
- Deletes, command execution, keyboard automation, and clipboard actions always require a
  local confirmation.
- File operations are limited to the current user's home folder unless the user explicitly
  enables **Allow all local drives**.
- Credential stores, browser cookies, password databases, wallets, and private-key locations
  are blocked.
- **EMERGENCY STOP** immediately stops polling and prevents further jobs.

## Supported actions

- Read/list files and folders
- Create, update, append, copy, move, and delete files or folders
- Open a file, folder, URL, or approved installed application
- Run allowlisted development tools without a command shell
- Type text, send a hotkey, and capture a screenshot when optional desktop automation
  dependencies are available

## Logs

Local configuration and audit logs are stored in:

```text
%USERPROFILE%\.pearl-device-agent
```

Do not share the downloaded EXE before first launch or `config.json`; each contains a short-lived
claim or device authentication token.

## Platform limits

This implementation targets Windows. macOS and Linux can use most file and command actions,
but may require additional operating-system accessibility permissions.

iPhone and iPad do not permit this form of full-device automation. iOS users remain limited
to downloadable files, Shortcuts, and app-specific capabilities approved by Apple.
