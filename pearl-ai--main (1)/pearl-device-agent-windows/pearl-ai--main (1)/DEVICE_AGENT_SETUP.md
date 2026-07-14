# Pearl Device Agent setup

## 1. Update PythonAnywhere

Copy the updated project files directly into `/home/hactivists/pearl-ai-main`, then run:

```bash
cd ~/pearl-ai-main
pa website reload --domain hactivists.pythonanywhere.com
```

Refresh PearlAI with `Ctrl+Shift+R`.

## 2. Download and open the companion app

1. Sign in to PearlAI in the browser.
2. Click **Agent**.
3. Click **Download Pearl AI Agent**.
4. Windows downloads the installer as an `.exe`; Android downloads the mobile app as an `.apk`.
5. On Windows, open the downloaded installer without renaming it and finish installation. On
   Android, allow installation from the browser if prompted, then install
   `PearlAI-Android-Device-Agent-v2.1.apk`. This compatibility release can install alongside an
   earlier Pearl APK; remove the old one afterward.
6. The Windows Agent uses a one-time claim embedded in the downloaded filename and automatically
   connects to the same account. The Android app asks the user to sign in because installed apps
   do not share browser cookies.
7. Both apps open the complete Pearl Agent frontend. Android automatically registers and pairs
   after sign-in. Tap **Enable device control** in the Android app and enable **Pearl AI Device
   Control** in Accessibility settings for typing, navigation, and screenshots.

No Python installation, BAT file, or connection code is required.

The downloadable file is built as a conventional installer from a directory-based application
package. Microsoft Defender scanned this replacement installer with no threats found. The installer
is not digitally signed, so Windows may still display **Unknown publisher** or a SmartScreen
reputation warning until a trusted code-signing certificate is added.

## Permission modes

- **Default Access:** the Windows companion asks locally before important changes.
- **Full Access:** ordinary file creation and editing can run automatically only if the
  companion's local **Allow website Full Access jobs** option is also enabled.
- Deletes, development-command execution, keyboard automation, and clipboard changes always
  require local confirmation.
- Home-folder file access is the default. Access to all local drives requires a separate local
  opt-in.

## Emergency stop

Click **EMERGENCY STOP** in the local companion. The companion stops polling immediately and
does not accept further work until restarted.

## Platform limitations

- Windows and Android are supported targets for packaged companion apps.
- macOS and Linux can run the Python companion with additional OS permissions and minor setup.
- The Android APK includes a native Device Agent foreground service. It supports sandboxed Agent
  files, URLs, approved app launches, clipboard changes, Accessibility-based typing/navigation,
  and screenshots on Android 11 or newer.
- Android does not permit unrestricted desktop shell commands or silent access to every user file.
  Sensitive actions require local approval.
- iPhone and iPad do not permit unrestricted full-device control. iOS supports only
  app-specific APIs, Shortcuts, and user-approved files.
