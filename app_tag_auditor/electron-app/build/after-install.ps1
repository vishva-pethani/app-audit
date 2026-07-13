# after-install.ps1
# Post-install setup script for App Tag Auditor on Windows.
# Equivalent to after-install.sh for Linux.
# Run by NSIS after the app files are copied to $INSTDIR.

param(
    [string]$InstallDir = "$PSScriptRoot\.."
)

# ── Resolve installation directory ────────────────────────────────────────────
$APP_DIR = (Resolve-Path $InstallDir -ErrorAction SilentlyContinue)?.Path
if (-not $APP_DIR) {
    $APP_DIR = $InstallDir
}
$LOG_DIR  = "$APP_DIR\logs"
$LOG_FILE = "$LOG_DIR\install.log"

New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

function Log {
    param([string]$msg)
    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line
}

Log "=== App Tag Auditor Windows Post-Install Setup ==="
Log "Install directory: $APP_DIR"

# ── 1. Python virtual environment ─────────────────────────────────────────────
Log "--- Setting up Python virtual environment ---"
$pythonCmd = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pythonCmd) {
    $pythonCmd = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
}
if (-not $pythonCmd) {
    Log "ERROR: Python not found. Please install Python 3.10+ from https://python.org and re-run setup."
    exit 1
}
Log "Using Python: $pythonCmd"

& $pythonCmd -m venv "$APP_DIR\venv"
& "$APP_DIR\venv\Scripts\pip.exe" install --upgrade pip
& "$APP_DIR\venv\Scripts\pip.exe" install -r "$APP_DIR\requirements.txt"
Log "Python venv ready."

# ── 2. Node.js / npm check ────────────────────────────────────────────────────
Log "--- Checking Node.js and npm ---"
$nodeCmd = (Get-Command node -ErrorAction SilentlyContinue)?.Source
$npmCmd  = (Get-Command npm  -ErrorAction SilentlyContinue)?.Source
if (-not $nodeCmd -or -not $npmCmd) {
    Log "ERROR: Node.js / npm not found. Please install from https://nodejs.org (LTS) and re-run setup."
    exit 1
}
Log "Node.js: $(& node --version)  npm: $(& npm --version)"

# ── 3. Appium + uiautomator2 ─────────────────────────────────────────────────
Log "--- Installing Appium globally ---"
$APPIUM_HOME = "$APP_DIR\.appium"
New-Item -ItemType Directory -Force -Path $APPIUM_HOME | Out-Null
$env:APPIUM_HOME = $APPIUM_HOME

& npm install -g appium@latest 2>&1 | ForEach-Object { Log $_ }

$appiumBin = (Get-Command appium -ErrorAction SilentlyContinue)?.Source
if (-not $appiumBin) {
    $npmPrefix = (& npm config get prefix).Trim()
    $appiumBin = "$npmPrefix\appium.cmd"
}

if (Test-Path $appiumBin) {
    Log "Installing uiautomator2 driver..."
    & $appiumBin driver install uiautomator2 2>&1 | ForEach-Object { Log $_ }
} else {
    Log "WARNING: Appium binary not found at $appiumBin — skipping uiautomator2 install."
}

# ── 4. JADX decompiler ────────────────────────────────────────────────────────
Log "--- Installing JADX decompiler ---"
$JADX_VERSION = "1.5.0"
$JADX_ROOT    = "$APP_DIR\jadx"
if (-not (Test-Path "$JADX_ROOT\bin\jadx.bat")) {
    New-Item -ItemType Directory -Force -Path $JADX_ROOT | Out-Null
    $jadxZip = "$env:TEMP\jadx.zip"
    Invoke-WebRequest "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" -OutFile $jadxZip
    Expand-Archive -Path $jadxZip -DestinationPath $JADX_ROOT -Force
    Remove-Item $jadxZip
    Log "JADX installed at $JADX_ROOT"
} else {
    Log "JADX already installed."
}

# ── 5. Android SDK command-line tools + platform-tools ───────────────────────
Log "--- Installing Android SDK platform-tools ---"
$ANDROID_ROOT = "$APP_DIR\android-sdk"
if (-not (Test-Path "$ANDROID_ROOT\platform-tools\adb.exe")) {
    New-Item -ItemType Directory -Force -Path "$ANDROID_ROOT\cmdline-tools" | Out-Null
    $cmdToolsZip = "$env:TEMP\cmdline-tools.zip"
    Invoke-WebRequest "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -OutFile $cmdToolsZip
    Expand-Archive -Path $cmdToolsZip -DestinationPath "$ANDROID_ROOT\cmdline-tools" -Force
    # electron-builder wants the folder at cmdline-tools\latest
    if (Test-Path "$ANDROID_ROOT\cmdline-tools\cmdline-tools") {
        Rename-Item "$ANDROID_ROOT\cmdline-tools\cmdline-tools" "latest"
    }
    Remove-Item $cmdToolsZip

    # Accept licenses non-interactively
    $sdkmgr = "$ANDROID_ROOT\cmdline-tools\latest\bin\sdkmanager.bat"
    "y" * 10 | & $sdkmgr --sdk_root="$ANDROID_ROOT" "platform-tools" "build-tools;34.0.0"
    Log "Android SDK installed at $ANDROID_ROOT"
} else {
    Log "Android SDK already installed."
}

# ── 6. Create runtime directories ─────────────────────────────────────────────
Log "--- Creating runtime directories ---"
foreach ($dir in @("output", "tmp", "logs", ".sessions")) {
    New-Item -ItemType Directory -Force -Path "$APP_DIR\$dir" | Out-Null
}

# ── 7. Default .env file ──────────────────────────────────────────────────────
Log "--- Creating default .env file ---"
$envFile = "$APP_DIR\.env"
if (-not (Test-Path $envFile)) {
    @"
GOOGLE_OAUTH_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501
GOOGLE_API_KEY=your-google-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
LOCAL_OUTPUT_PATH=./output/audit_results.xlsx
TEMP_STORAGE_DIR=./tmp
APPIUM_SERVER_URL=http://localhost:4723
FLASK_PORT=8501
"@ | Set-Content -Path $envFile -Encoding UTF8
    Log ".env created."
}

Log "=== Post-Install Setup Completed Successfully ==="
exit 0
