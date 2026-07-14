# Pearl AI Agent for Android

This is the native Pearl AI Device Agent for Android. It:

- registers and pairs with the signed-in Pearl AI account;
- polls for device jobs in a foreground service;
- works with files inside its protected Android Agent workspace;
- opens approved URLs and installed applications;
- updates the clipboard after local approval;
- types into the focused field and performs Android navigation through an explicitly enabled
  Accessibility service;
- captures screenshots on Android 11 or newer after local approval;
- provides emergency stop and resume controls.

Android does not allow unrestricted desktop-style shell execution or silent access to all user
files. The Agent intentionally follows Android's scoped-storage and Accessibility permission model.

Build the signed APK from PowerShell:

```powershell
.\build.ps1
```

The build script uses the Android SDK installed under `C:\Program Files (x86)\Android\android-sdk`
and the JDK under `C:\Program Files\Android\openjdk\jdk-21.0.8`. Override those locations with
`ANDROID_HOME` and `JAVA_HOME` when needed.

The generated APK is copied to `downloads\PearlAI-Android-Device-Agent-v2.1.apk`. It supports
Android 5.0 and newer and carries both legacy and modern APK signatures for broad installer
compatibility. It uses a new Android package identity so it does not conflict with the earlier
wrapper APK.

The default local signing key is for development deployments. Set `PEARL_ANDROID_KEYSTORE`,
`PEARL_ANDROID_KEYSTORE_PASSWORD`, and `PEARL_ANDROID_KEY_ALIAS` to use a production signing key.

After installation:

1. Open the app and sign in.
2. The app automatically pairs itself to that account.
3. Tap **Enable device control** and enable **Pearl AI Device Control** in Android Accessibility
   settings.
4. Keep notification permission enabled so approval requests and the emergency-stop control remain
   visible.
