# Pearl Device Agent

This visible Windows companion lets a paired PearlAI account perform approved local actions.

## Install and start

1. Install Python 3.11 or newer from `https://www.python.org/downloads/`.
2. Extract this folder to a location you control.
3. Double-click `start_agent.bat`.
4. Keep the Pearl Device Agent window open.
5. Copy its eight-digit pairing code.
6. In PearlAI, open **Agent**, choose **Device Agent**, click **Pair Device**, and enter the code.

The companion does not install itself at startup, hide in the background, or bypass operating-system permissions.

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

Do not share `config.json`; it contains the device authentication token.

## Platform limits

This implementation targets Windows. macOS and Linux can use most file and command actions,
but may require additional operating-system accessibility permissions.

iPhone and iPad do not permit this form of full-device automation. iOS users remain limited
to downloadable files, Shortcuts, and app-specific capabilities approved by Apple.
