# after-install.ps1 — Post-install setup for App Tag Auditor on Windows
# Run by the NSIS installer after files are copied

param(
    [string]$InstallDir = "$PSScriptRoot\.."
)

$LogFile = "$env:TEMP\AppTagAuditor-install.log"
function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $LogFile -Append | Write-Host
}

Log "=== App Tag Auditor Post-Install Setup (Windows) ==="
Log "Install directory: $InstallDir"

# ── 1. Python Virtual Environment ───────────────────────────────────────────
Log "--- Setting up Python virtual environment ---"
$Python = "python"
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    $Python = "python3"
}
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    Log "ERROR: Python not found. Please install Python 3.10+ from https://python.org"
    exit 1
}

$VenvDir = Join-Path $InstallDir "venv"
if (-not (Test-Path $VenvDir)) {
    & $Python -m venv $VenvDir
}
$PipExe   = Join-Path $VenvDir "Scripts\pip.exe"
$ReqsFile = Join-Path $InstallDir "requirements.txt"
& $PipExe install --upgrade pip | Out-Null
& $PipExe install -r $ReqsFile
Log "Python environment ready."

# ── 2. Appium & UIAutomator2 driver ─────────────────────────────────────────
Log "--- Installing Appium and uiautomator2 driver ---"
$AppiumHome = Join-Path $InstallDir ".appium"
New-Item -ItemType Directory -Force -Path $AppiumHome | Out-Null
$env:APPIUM_HOME = $AppiumHome

$NpmCmd = "npm"
if (-not (Get-Command $NpmCmd -ErrorAction SilentlyContinue)) {
    Log "ERROR: Node.js / npm not found. Please install from https://nodejs.org"
    exit 1
}

npm install -g appium@latest 2>&1 | Out-Null
appium driver install uiautomator2 2>&1 | Out-Null
Log "Appium ready."

# ── 3. Android SDK (platform-tools + build-tools) ───────────────────────────
Log "--- Setting up Android platform-tools ---"
# Check if user already has an Android SDK
$UserSdk = "$env:LOCALAPPDATA\Android\Sdk"
if (Test-Path (Join-Path $UserSdk "platform-tools\adb.exe")) {
    Log "Found existing Android SDK at $UserSdk — skipping download."
} else {
    $AndroidRoot = Join-Path $env:ProgramFiles "AppTagAuditor\android-sdk"
    New-Item -ItemType Directory -Force -Path $AndroidRoot | Out-Null

    $CmdToolsZip = "$env:TEMP\cmdline-tools.zip"
    Log "Downloading Android command-line tools..."
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" `
        -OutFile $CmdToolsZip -UseBasicParsing

    $CmdToolsDir = Join-Path $AndroidRoot "cmdline-tools"
    Expand-Archive -Path $CmdToolsZip -DestinationPath $CmdToolsDir -Force
    Rename-Item -Path (Join-Path $CmdToolsDir "cmdline-tools") -NewName "latest" -ErrorAction SilentlyContinue
    Remove-Item $CmdToolsZip

    $SdkManager = Join-Path $CmdToolsDir "latest\bin\sdkmanager.bat"
    Log "Installing platform-tools and build-tools via sdkmanager..."
    & $SdkManager --sdk_root="$AndroidRoot" "platform-tools" "build-tools;34.0.0" 2>&1 | Out-Null

    # Symlink into app resources
    $LinkTarget = Join-Path $InstallDir "android-sdk"
    if (Test-Path $LinkTarget) { Remove-Item $LinkTarget -Force }
    New-Item -ItemType Junction -Path $LinkTarget -Target $AndroidRoot | Out-Null
    Log "Android SDK installed to $AndroidRoot."
}

# ── 4. Create runtime directories ───────────────────────────────────────────
Log "--- Creating runtime directories ---"
foreach ($dir in @("output","tmp","logs",".sessions",".appium")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir $dir) | Out-Null
}

# ── 5. Create default .env file ─────────────────────────────────────────────
$EnvFile = Join-Path $InstallDir ".env"
if (-not (Test-Path $EnvFile)) {
    Log "--- Creating default .env file ---"
    @"
GOOGLE_OAUTH_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501
GOOGLE_API_KEY=your-google-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
LOCAL_OUTPUT_PATH=./output/audit_results.xlsx
TEMP_STORAGE_DIR=./tmp
APPIUM_SERVER_URL=http://localhost:4723
"@ | Set-Content -Path $EnvFile -Encoding UTF8
}

Log "=== Post-Install Setup Completed Successfully ==="
