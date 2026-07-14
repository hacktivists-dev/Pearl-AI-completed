$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ProjectDir
$SdkDir = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "C:\Program Files (x86)\Android\android-sdk" }
$JavaDir = if ($env:JAVA_HOME) { $env:JAVA_HOME } else { "C:\Program Files\Android\openjdk\jdk-21.0.8" }
$BuildTools = Join-Path $SdkDir "build-tools\36.0.0"
$AndroidJar = Join-Path $SdkDir "platforms\android-35\android.jar"
$BuildDir = Join-Path $ProjectDir "build"
$ClassesDir = Join-Path $BuildDir "classes"
$DexDir = Join-Path $BuildDir "dex"
$ResourceArchive = Join-Path $BuildDir "resources.zip"
$SigningDir = Join-Path $ProjectDir "signing"
$Keystore = if ($env:PEARL_ANDROID_KEYSTORE) {
    $env:PEARL_ANDROID_KEYSTORE
} else {
    Join-Path $SigningDir "pearl-agent-development.jks"
}
$KeystorePassword = if ($env:PEARL_ANDROID_KEYSTORE_PASSWORD) {
    $env:PEARL_ANDROID_KEYSTORE_PASSWORD
} else {
    "pearl-agent-development"
}
$KeyAlias = if ($env:PEARL_ANDROID_KEY_ALIAS) {
    $env:PEARL_ANDROID_KEY_ALIAS
} else {
    "pearl-agent"
}

$env:JAVA_HOME = $JavaDir
$env:Path = "$(Join-Path $JavaDir 'bin');$env:Path"

function Assert-NativeSuccess {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

Remove-Item -LiteralPath $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $BuildDir, $ClassesDir, $DexDir, $SigningDir | Out-Null

& (Join-Path $BuildTools "aapt2.exe") compile `
    --dir (Join-Path $ProjectDir "res") `
    -o $ResourceArchive
Assert-NativeSuccess "Android resource compilation"

& (Join-Path $BuildTools "aapt2.exe") link `
    -o (Join-Path $BuildDir "unsigned.apk") `
    -I $AndroidJar `
    --manifest (Join-Path $ProjectDir "AndroidManifest.xml") `
    --min-sdk-version 21 `
    --target-sdk-version 35 `
    --version-code 3 `
    --version-name "2.1.0" `
    --auto-add-overlay `
    $ResourceArchive
Assert-NativeSuccess "Android package linking"
Remove-Item -LiteralPath $ResourceArchive -Force -ErrorAction SilentlyContinue

$JavaSources = Get-ChildItem -LiteralPath (Join-Path $ProjectDir "src") -Recurse -Filter "*.java" |
    ForEach-Object { $_.FullName }
& (Join-Path $JavaDir "bin\javac.exe") `
    -encoding UTF-8 `
    -source 8 `
    -target 8 `
    -bootclasspath $AndroidJar `
    -d $ClassesDir `
    $JavaSources
Assert-NativeSuccess "Java compilation"

$ClassFiles = Get-ChildItem -LiteralPath $ClassesDir -Recurse -Filter "*.class" |
    ForEach-Object { $_.FullName }
& (Join-Path $BuildTools "d8.bat") `
    --lib $AndroidJar `
    --min-api 21 `
    --output $DexDir `
    $ClassFiles
Assert-NativeSuccess "DEX compilation"

& (Join-Path $JavaDir "bin\jar.exe") uf `
    (Join-Path $BuildDir "unsigned.apk") `
    -C $DexDir `
    "classes.dex"
Assert-NativeSuccess "DEX packaging"

& (Join-Path $BuildTools "zipalign.exe") `
    -f `
    4 `
    (Join-Path $BuildDir "unsigned.apk") `
    (Join-Path $BuildDir "aligned.apk")
Assert-NativeSuccess "APK alignment"

if (-not (Test-Path -LiteralPath $Keystore)) {
    & (Join-Path $JavaDir "bin\keytool.exe") `
        -genkeypair `
        -keystore $Keystore `
        -storepass $KeystorePassword `
        -keypass $KeystorePassword `
        -alias $KeyAlias `
        -keyalg RSA `
        -keysize 2048 `
        -validity 10000 `
        -dname "CN=Pearl AI Agent, O=Pearl AI, C=US"
    Assert-NativeSuccess "Signing key generation"
}

$OutputApk = Join-Path $RootDir "downloads\PearlAI-Android-Device-Agent-v2.1.apk"
Remove-Item -LiteralPath $OutputApk, "$OutputApk.idsig" -Force -ErrorAction SilentlyContinue
& (Join-Path $BuildTools "apksigner.bat") sign `
    --ks $Keystore `
    --ks-key-alias $KeyAlias `
    --ks-pass "pass:$KeystorePassword" `
    --key-pass "pass:$KeystorePassword" `
    --v1-signing-enabled true `
    --v2-signing-enabled true `
    --v3-signing-enabled true `
    --v4-signing-enabled false `
    --out $OutputApk `
    (Join-Path $BuildDir "aligned.apk")
Assert-NativeSuccess "APK signing"

& (Join-Path $BuildTools "apksigner.bat") verify --verbose $OutputApk
Assert-NativeSuccess "APK signature verification"
Remove-Item -LiteralPath "$OutputApk.idsig" -Force -ErrorAction SilentlyContinue
Write-Output "Built $OutputApk"
