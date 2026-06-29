#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# build_deb.sh — Debian Package Builder for App Tag Auditor
# ──────────────────────────────────────────────────────────────────────────────
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   App Tag Auditor — Debian Package Builder   ${NC}"
echo -e "${BLUE}===============================================${NC}"

# Define version and names
VERSION="1.0.0"
PKG_NAME="app-tag-auditor"
DEB_FILE="${PKG_NAME}_${VERSION}_all.deb"

# Setup temporary build directory within workspace
BUILD_DIR="deb_build_temp"
echo -e "${BLUE}Creating build structure in ./${BUILD_DIR}...${NC}"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/opt/app-tag-auditor/bin"
mkdir -p "$BUILD_DIR/etc/app-tag-auditor"
mkdir -p "$BUILD_DIR/etc/profile.d"
mkdir -p "$BUILD_DIR/etc/systemd/system"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/pixmaps"

# ── 1. Create Control File ────────────────────────────────────────────────────
echo -e "${BLUE}Writing DEBIAN/control...${NC}"
cat > "$BUILD_DIR/DEBIAN/control" << CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: Antigravity <antigravity@google.com>
Depends: python3, python3-pip, python3-venv, openjdk-17-jre-headless, android-tools-adb, udev, nodejs, npm, curl, wget, unzip
Description: App Tag Auditor
 An automated tool for auditing tags, decompiling APKs, and checking app behavior.
 Includes Streamlit frontend, Appium integration, JADX, and Android SDK support.
CONTROL

# ── 2. Create Conffiles ────────────────────────────────────────────────────────
echo -e "${BLUE}Writing DEBIAN/conffiles...${NC}"
cat > "$BUILD_DIR/DEBIAN/conffiles" << CONFFILES
/etc/app-tag-auditor/app-tag-auditor.env
CONFFILES

# Read existing credentials from the workspace or host system if they exist to bake them in
HOST_CLIENT_ID=""
HOST_CLIENT_SECRET=""
HOST_REDIRECT_URI=""
HOST_GOOGLE_API_KEY=""
HOST_ANTHROPIC_API_KEY=""

extract_creds() {
    local file="$1"
    if [ -f "$file" ]; then
        echo -e "${YELLOW}Extracting credentials from $file...${NC}"
        if [ -z "$HOST_CLIENT_ID" ]; then
            HOST_CLIENT_ID=$(grep -E '^GOOGLE_OAUTH_CLIENT_ID=' "$file" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
        fi
        if [ -z "$HOST_CLIENT_SECRET" ]; then
            HOST_CLIENT_SECRET=$(grep -E '^GOOGLE_OAUTH_CLIENT_SECRET=' "$file" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
        fi
        if [ -z "$HOST_REDIRECT_URI" ]; then
            HOST_REDIRECT_URI=$(grep -E '^GOOGLE_OAUTH_REDIRECT_URI=' "$file" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
        fi
        if [ -z "$HOST_GOOGLE_API_KEY" ]; then
            HOST_GOOGLE_API_KEY=$(grep -E '^GOOGLE_API_KEY=' "$file" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
        fi
        if [ -z "$HOST_ANTHROPIC_API_KEY" ]; then
            HOST_ANTHROPIC_API_KEY=$(grep -E '^ANTHROPIC_API_KEY=' "$file" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
        fi
    fi
}

# 1. Check local app_tag_auditor/.env
extract_creds "app_tag_auditor/.env" || true
# 2. Check local .env in workspace root
extract_creds ".env" || true
# 3. Check existing system installation /etc/app-tag-auditor/app-tag-auditor.env
extract_creds "/etc/app-tag-auditor/app-tag-auditor.env" || true

# Fallback to local environment variables if still empty
if [ -z "$HOST_CLIENT_ID" ]; then
    HOST_CLIENT_ID="$GOOGLE_OAUTH_CLIENT_ID"
fi
if [ -z "$HOST_CLIENT_SECRET" ]; then
    HOST_CLIENT_SECRET="$GOOGLE_OAUTH_CLIENT_SECRET"
fi
if [ -z "$HOST_REDIRECT_URI" ]; then
    HOST_REDIRECT_URI="$GOOGLE_OAUTH_REDIRECT_URI"
fi
if [ -z "$HOST_REDIRECT_URI" ]; then
    HOST_REDIRECT_URI="http://localhost:8501"
fi
if [ -z "$HOST_GOOGLE_API_KEY" ]; then
    HOST_GOOGLE_API_KEY="$GOOGLE_API_KEY"
fi
if [ -z "$HOST_ANTHROPIC_API_KEY" ]; then
    HOST_ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"
fi

echo -e "${GREEN}Credentials successfully baked into package configuration:${NC}"
echo "  GOOGLE_OAUTH_CLIENT_ID: ${HOST_CLIENT_ID:-(empty)}"
echo "  GOOGLE_OAUTH_CLIENT_SECRET: ${HOST_CLIENT_SECRET:-(empty)}"
echo "  GOOGLE_OAUTH_REDIRECT_URI: ${HOST_REDIRECT_URI:-(empty)}"
echo "  GOOGLE_API_KEY: ${HOST_GOOGLE_API_KEY:-(empty)}"
echo "  ANTHROPIC_API_KEY: ${HOST_ANTHROPIC_API_KEY:-(empty)}"

# ── 3. Create Configuration Template ──────────────────────────────────────────
echo -e "${BLUE}Writing configuration template to /etc/app-tag-auditor/...${NC}"
cat > "$BUILD_DIR/etc/app-tag-auditor/app-tag-auditor.env" << ENV_TEMPLATE
# ──────────────────────────────────────────────────────────────────────────────
# App Tag Auditor — Configuration File
# ──────────────────────────────────────────────────────────────────────────────

# 1. API Keys & OAuth Credentials
GOOGLE_OAUTH_CLIENT_ID=${HOST_CLIENT_ID}
GOOGLE_OAUTH_CLIENT_SECRET=${HOST_CLIENT_SECRET}
GOOGLE_OAUTH_REDIRECT_URI=${HOST_REDIRECT_URI}
GOOGLE_API_KEY=${HOST_GOOGLE_API_KEY}
ANTHROPIC_API_KEY=${HOST_ANTHROPIC_API_KEY}

# 2. Application Directories & Paths
LOCAL_OUTPUT_PATH=/opt/app-tag-auditor/output/audit_results.xlsx
TEMP_STORAGE_DIR=/opt/app-tag-auditor/tmp
JADX_PATH=/opt/app-tag-auditor/jadx/bin/jadx
APPIUM_SERVER_URL=http://localhost:4723
ANDROID_HOME=/opt/app-tag-auditor/android-sdk
ANDROID_SDK_ROOT=/opt/app-tag-auditor/android-sdk
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
APPIUM_HOME=/opt/app-tag-auditor/.appium

# 3. Environment Search Path
PATH=/opt/app-tag-auditor/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/app-tag-auditor/android-sdk/platform-tools:/opt/app-tag-auditor/android-sdk/cmdline-tools/latest/bin:/opt/app-tag-auditor/android-sdk/build-tools/34.0.0
ENV_TEMPLATE

chmod 700 "$BUILD_DIR/etc/app-tag-auditor"
chmod 600 "$BUILD_DIR/etc/app-tag-auditor/app-tag-auditor.env"

# Create profile.d entry for global user environment variables
echo -e "${BLUE}Writing profile.d environment configuration...${NC}"
cat > "$BUILD_DIR/etc/profile.d/app-tag-auditor.sh" << 'PROFILE'
# App Tag Auditor Environment Variables
export ANDROID_HOME=/opt/app-tag-auditor/android-sdk
export ANDROID_SDK_ROOT=/opt/app-tag-auditor/android-sdk
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export APPIUM_HOME=/opt/app-tag-auditor/.appium
export PATH="$PATH:/opt/app-tag-auditor/android-sdk/platform-tools:/opt/app-tag-auditor/android-sdk/cmdline-tools/latest/bin:/opt/app-tag-auditor/android-sdk/build-tools/34.0.0"
PROFILE
chmod 644 "$BUILD_DIR/etc/profile.d/app-tag-auditor.sh"

# ── 4. Create Appium/ADB/Streamlit Service Launcher ──────────────────────────
echo -e "${BLUE}Writing service launcher to /opt/app-tag-auditor/bin/...${NC}"
cat > "$BUILD_DIR/opt/app-tag-auditor/bin/launcher.sh" << 'LAUNCHER'
#!/usr/bin/env bash
set -e

# Export configuration environment variables
if [ -f /etc/app-tag-auditor/app-tag-auditor.env ]; then
    export $(grep -v '^#' /etc/app-tag-auditor/app-tag-auditor.env | xargs)
fi

# Verify JADX is available
if [ ! -f "$JADX_PATH" ]; then
    echo "Error: JADX not found at $JADX_PATH" >&2
    exit 1
fi

# Verify Android Home is set
if [ ! -d "$ANDROID_HOME" ]; then
    echo "Error: Android SDK not found at $ANDROID_HOME" >&2
    exit 1
fi

# Create dynamic runtime directories
mkdir -p /opt/app-tag-auditor/output /opt/app-tag-auditor/tmp /opt/app-tag-auditor/logs /opt/app-tag-auditor/.sessions
chmod -R 777 /opt/app-tag-auditor/output /opt/app-tag-auditor/tmp /opt/app-tag-auditor/logs /opt/app-tag-auditor/.sessions

# Ensure Android SDK env vars are explicitly set before starting Appium.
# Appium's uiautomator2 driver reads ANDROID_HOME from the server process
# environment at session-creation time — the capability alone is not enough.
export ANDROID_HOME="${ANDROID_HOME:-/opt/app-tag-auditor/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-/opt/app-tag-auditor/android-sdk}"
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/build-tools/34.0.0"

# Start ADB server
echo "Starting ADB server..."
"$ANDROID_HOME/platform-tools/adb" start-server 2>/dev/null || adb start-server || true

# Start Appium server in background
echo "Starting Appium server on port 4723..."
ANDROID_HOME="$ANDROID_HOME" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
    appium --address 127.0.0.1 --log-level error &
APPIUM_PID=$!

# Ensure cleanup on shutdown
cleanup() {
    echo "Stopping Appium (PID $APPIUM_PID)..."
    kill $APPIUM_PID || true
    echo "Stopping ADB server..."
    adb kill-server || true
}
trap cleanup EXIT

# Wait for Appium to become ready
MAX_WAIT=20
WAITED=0
until curl -sf http://localhost:4723/status > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "Warning: Appium did not start within ${MAX_WAIT} seconds"
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done

if curl -sf http://localhost:4723/status > /dev/null 2>&1; then
    echo "Appium server is ready"
fi

# Start Web Server
echo "Starting App Tag Auditor Server..."
exec /opt/app-tag-auditor/venv/bin/python /opt/app-tag-auditor/app_tag_auditor/frontend/app.py
LAUNCHER
chmod +x "$BUILD_DIR/opt/app-tag-auditor/bin/launcher.sh"

# ── 5. Create Systemd Service File ───────────────────────────────────────────
echo -e "${BLUE}Writing systemd service file...${NC}"
cat > "$BUILD_DIR/etc/systemd/system/app-tag-auditor.service" << SERVICE
[Unit]
Description=App Tag Auditor Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/app-tag-auditor
EnvironmentFile=/etc/app-tag-auditor/app-tag-auditor.env
ExecStart=/opt/app-tag-auditor/bin/launcher.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

# ── 6. Create User Space CLI Launcher ──────────────────────────────────────────
echo -e "${BLUE}Writing user launcher to /usr/bin/...${NC}"
cat > "$BUILD_DIR/usr/bin/app-tag-auditor" << 'CLI_LAUNCHER'
#!/usr/bin/env bash
# app-tag-auditor - CLI launcher for App Tag Auditor

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== App Tag Auditor Launcher ===${NC}"

# Check if running as root or normal user
if [ "$EUID" -ne 0 ]; then
    if ! systemctl is-active --quiet app-tag-auditor; then
        echo -e "${YELLOW}App Tag Auditor service is not running.${NC}"
        echo -e "Attempting to start the service (requires authorization)..."
        if command -v pkexec &>/dev/null && [ -n "$DISPLAY" -o -n "$WAYLAND_DISPLAY" ]; then
            if pkexec systemctl start app-tag-auditor; then
                echo -e "${GREEN}Service started successfully.${NC}"
            else
                echo -e "${RED}Failed to start service. Please verify systemd status.${NC}"
                exit 1
            fi
        else
            if sudo systemctl start app-tag-auditor; then
                echo -e "${GREEN}Service started successfully.${NC}"
            else
                echo -e "${RED}Failed to start service. Please verify systemd status.${NC}"
                exit 1
            fi
        fi
    fi
else
    if ! systemctl is-active --quiet app-tag-auditor; then
        echo -e "${YELLOW}Starting App Tag Auditor service...${NC}"
        systemctl start app-tag-auditor
    fi
fi

# Wait for Streamlit port to become active
echo -e "${BLUE}Waiting for App Tag Auditor web interface to become active...${NC}"
for i in {1..15}; do
    if curl -sf http://localhost:8501/ >/dev/null 2>&1; then
        echo -e "${GREEN}App Tag Auditor is running at http://localhost:8501${NC}"
        # Open browser
        if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
            if command -v xdg-open &>/dev/null; then
                nohup xdg-open "http://localhost:8501" >/dev/null 2>&1 &
                disown || true
            elif command -v sensible-browser &>/dev/null; then
                nohup sensible-browser "http://localhost:8501" >/dev/null 2>&1 &
                disown || true
            fi
        else
            echo -e "${YELLOW}No display environment detected. Please open http://localhost:8501 in your browser.${NC}"
        fi
        exit 0
    fi
    sleep 1
done

echo -e "${RED}Error: App Tag Auditor interface did not load in time.${NC}"
echo -e "Please check logs with: journalctl -u app-tag-auditor -n 50"
exit 1
CLI_LAUNCHER
chmod +x "$BUILD_DIR/usr/bin/app-tag-auditor"

# ── 7. Create App Desktop Icon (SVG) ──────────────────────────────────────────
echo -e "${BLUE}Writing app desktop icon to /usr/share/pixmaps/...${NC}"
cat > "$BUILD_DIR/usr/share/pixmaps/app-tag-auditor.svg" << 'SVG_ICON'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#1e3c72;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#2a5298;stop-opacity:1" />
    </linearGradient>
    <!-- Accent Gradient -->
    <linearGradient id="accentGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#00f2fe;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#4facfe;stop-opacity:1" />
    </linearGradient>
    <!-- Success Green Gradient -->
    <linearGradient id="successGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#00b09b;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#96c93d;stop-opacity:1" />
    </linearGradient>
    <!-- Drop Shadow Filter -->
    <filter id="dropShadow" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.4" />
    </filter>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>

  <!-- Base Rounded Rectangle -->
  <rect width="480" height="480" x="16" y="16" rx="96" fill="url(#bgGrad)" filter="url(#dropShadow)" />

  <!-- Outer Ring / Tech Details -->
  <rect width="440" height="440" x="36" y="36" rx="80" fill="none" stroke="url(#accentGrad)" stroke-width="4" stroke-opacity="0.3" />

  <!-- Mobile Device Silhouette -->
  <rect width="180" height="320" x="166" y="96" rx="24" fill="#0f172a" stroke="url(#accentGrad)" stroke-width="6" filter="url(#dropShadow)" />
  <!-- Device Screen -->
  <rect width="160" height="260" x="176" y="116" rx="12" fill="#1e293b" />
  <!-- Device Speaker / Notch -->
  <rect width="60" height="10" x="226" y="102" rx="5" fill="#334155" />
  
  <!-- Audit Checklist Lines on Screen -->
  <line x1="196" y1="146" x2="316" y2="146" stroke="#475569" stroke-width="4" stroke-linecap="round" />
  <line x1="196" y1="176" x2="286" y2="176" stroke="#475569" stroke-width="4" stroke-linecap="round" />
  <line x1="196" y1="206" x2="306" y2="206" stroke="#475569" stroke-width="4" stroke-linecap="round" />
  
  <!-- Magnifying Glass (Analyzing) -->
  <circle cx="280" cy="280" r="60" fill="none" stroke="url(#accentGrad)" stroke-width="14" filter="url(#glow)" />
  <line x1="322" y1="322" x2="380" y2="380" stroke="url(#accentGrad)" stroke-width="14" stroke-linecap="round" filter="url(#glow)" />

  <!-- Glowing Checkmark (Audited & Verified) inside Magnifying Glass -->
  <path d="M255 280 L272 297 L307 262" fill="none" stroke="url(#successGrad)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)" />
  
</svg>
SVG_ICON

# ── 8. Create Desktop Application Entry ────────────────────────────────────────
echo -e "${BLUE}Writing app desktop entry to /usr/share/applications/...${NC}"
cat > "$BUILD_DIR/usr/share/applications/app-tag-auditor.desktop" << DESKTOP_ENTRY
[Desktop Entry]
Name=App Tag Auditor
Comment=Automated tool for auditing tags, decompiling APKs, and checking app behavior
Exec=app-tag-auditor
Icon=app-tag-auditor
Terminal=false
Type=Application
Categories=Development;Utility;
DESKTOP_ENTRY

# ── 9. Copy Project Files to /opt/app-tag-auditor/ ────────────────────────────
echo -e "${BLUE}Copying codebase to /opt/app-tag-auditor/...${NC}"
cp -r app_tag_auditor "$BUILD_DIR/opt/app-tag-auditor/"
cp Makefile "$BUILD_DIR/opt/app-tag-auditor/"
cp DEPLOY.md "$BUILD_DIR/opt/app-tag-auditor/"

# Compile python source code to bytecode (.pyc) and remove raw source files to hide them
echo -e "${BLUE}Compiling python source code to bytecode (.pyc) and removing raw source code...${NC}"
python3 -c "
import os
import py_compile

target_dir = '$BUILD_DIR/opt/app-tag-auditor/app_tag_auditor'
for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith('.py'):
            py_path = os.path.join(root, file)
            # If it is the main frontend/app.py, we compile it to app_compiled.pyc
            # and replace app.py with a raw python loader stub (Streamlit doesn't execute raw .pyc directly)
            if file == 'app.py' and 'frontend' in root:
                pyc_path = os.path.join(root, 'app_compiled.pyc')
                print(f'Compiling entrypoint: {py_path} -> {pyc_path}')
                py_compile.compile(py_path, cfile=pyc_path)
                with open(py_path, 'w') as f:
                    f.write('import sys\nimport os\nsys.path.insert(0, os.path.dirname(__file__))\nimport app_compiled\n')
            else:
                pyc_path = py_path + 'c'
                print(f'Compiling: {py_path} -> {pyc_path}')
                py_compile.compile(py_path, cfile=pyc_path)
                os.remove(py_path)
"

# ── 10. Write DEBIAN maintainer scripts ───────────────────────────────────────

# A. postinst script
echo -e "${BLUE}Writing postinst script...${NC}"
cat > "$BUILD_DIR/DEBIAN/postinst" << 'POSTINST'
#!/usr/bin/env bash
set -e

# Make sure permissions are correct
chmod -R 755 /opt/app-tag-auditor
mkdir -p /opt/app-tag-auditor/output /opt/app-tag-auditor/tmp /opt/app-tag-auditor/logs /opt/app-tag-auditor/.sessions /opt/app-tag-auditor/.appium
chmod -R 777 /opt/app-tag-auditor/output /opt/app-tag-auditor/tmp /opt/app-tag-auditor/logs /opt/app-tag-auditor/.sessions /opt/app-tag-auditor/.appium

# Secure env credentials folder and file so they are only readable by root
chown -R root:root /etc/app-tag-auditor
chmod 700 /etc/app-tag-auditor
chmod 600 /etc/app-tag-auditor/app-tag-auditor.env

# 1. Setup Python Virtual Environment
echo "=== Setting up Python Virtual Environment ==="
python3 -m venv /opt/app-tag-auditor/venv
/opt/app-tag-auditor/venv/bin/pip install --upgrade pip
/opt/app-tag-auditor/venv/bin/pip install -r /opt/app-tag-auditor/app_tag_auditor/requirements.txt

# 2. Check Node.js and npm
echo "=== Checking Node.js Environment ==="
if command -v node >/dev/null 2>&1 && [ "$(node -v | cut -d. -f1 | tr -d 'v')" -ge 18 ]; then
    echo "Found compatible system Node.js: $(node -v)"
    NODE_BIN="node"
    NPM_BIN="npm"
else
    echo "Compatible system Node.js not found (required: >= v18). Installing standalone Node.js v20..."
    NODE_VERSION="20.11.1"
    NODE_DIR="/opt/app-tag-auditor/node"
    if [ ! -f "$NODE_DIR/bin/node" ]; then
        mkdir -p "$NODE_DIR"
        wget -q "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -O /tmp/node.tar.xz
        tar -xf /tmp/node.tar.xz -C "$NODE_DIR" --strip-components=1
        rm -f /tmp/node.tar.xz
    fi
    NODE_BIN="$NODE_DIR/bin/node"
    NPM_BIN="$NODE_DIR/bin/npm"
    # Put standalone node in PATH of environment
    sed -i 's|/usr/local/sbin|/opt/app-tag-auditor/node/bin:/usr/local/sbin|' /etc/app-tag-auditor/app-tag-auditor.env
fi

# Export paths for sub-installation steps
export PATH="/opt/app-tag-auditor/node/bin:$PATH"

# 3. Install Appium & UIAutomator2 driver
echo "=== Installing Appium ==="
export APPIUM_HOME="/opt/app-tag-auditor/.appium"
if [ "$NPM_BIN" = "npm" ]; then
    npm install -g appium@latest --unsafe-perm=true
    appium driver install uiautomator2 || true
else
    "$NPM_BIN" install -g appium@latest --unsafe-perm=true
    /opt/app-tag-auditor/node/bin/appium driver install uiautomator2 || true
fi
chmod -R 777 /opt/app-tag-auditor/.appium

# 4. Download and setup JADX
echo "=== Installing JADX ==="
JADX_VERSION="1.5.0"
JADX_DIR="/opt/app-tag-auditor/jadx"
if [ ! -f "$JADX_DIR/bin/jadx" ]; then
    mkdir -p "$JADX_DIR"
    wget -q "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" -O /tmp/jadx.zip
    unzip -q /tmp/jadx.zip -d "$JADX_DIR"
    chmod +x "$JADX_DIR/bin/jadx"
    rm -f /tmp/jadx.zip
fi

# 5. Download and setup Android SDK
echo "=== Installing Android SDK (Platform & Build Tools) ==="
ANDROID_HOME="/opt/app-tag-auditor/android-sdk"
if [ ! -d "$ANDROID_HOME/platform-tools" ]; then
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    wget -q "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" -O /tmp/cmdline-tools.zip
    unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
    rm -f /tmp/cmdline-tools.zip
    # Run sdkmanager to install platform-tools and build-tools
    yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$ANDROID_HOME" "platform-tools" "build-tools;34.0.0"
fi

# 6. Setup environment symlinks for Streamlit config files
ln -sf /etc/app-tag-auditor/app-tag-auditor.env /opt/app-tag-auditor/.env
ln -sf /etc/app-tag-auditor/app-tag-auditor.env /opt/app-tag-auditor/app_tag_auditor/.env

# 7. Create/Reload udev rules for Android USB device connectivity
echo "=== Configuring USB/udev rules for Android Debugging ==="
RULES_FILE="/etc/udev/rules.d/51-app-tag-auditor.rules"
cat > "$RULES_FILE" << 'UDEV_RULES'
# Generic Android USB devices — covers all common vendors
SUBSYSTEM=="usb", ATTR{idVendor}=="0502", MODE="0666", GROUP="plugdev"   # Acer
SUBSYSTEM=="usb", ATTR{idVendor}=="0b05", MODE="0666", GROUP="plugdev"   # ASUS
SUBSYSTEM=="usb", ATTR{idVendor}=="413c", MODE="0666", GROUP="plugdev"   # Dell
SUBSYSTEM=="usb", ATTR{idVendor}=="0489", MODE="0666", GROUP="plugdev"   # Foxconn
SUBSYSTEM=="usb", ATTR{idVendor}=="04c5", MODE="0666", GROUP="plugdev"   # Fujitsu
SUBSYSTEM=="usb", ATTR{idVendor}=="04c5", MODE="0666", GROUP="plugdev"   # Fujitsu-Toshiba
SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0666", GROUP="plugdev"   # Garmin-Asus
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"   # Google
SUBSYSTEM=="usb", ATTR{idVendor}=="201e", MODE="0666", GROUP="plugdev"   # Haier
SUBSYSTEM=="usb", ATTR{idVendor}=="109b", MODE="0666", GROUP="plugdev"   # Hisense
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", MODE="0666", GROUP="plugdev"   # HTC
SUBSYSTEM=="usb", ATTR{idVendor}=="12d1", MODE="0666", GROUP="plugdev"   # Huawei
SUBSYSTEM=="usb", ATTR{idVendor}=="2314", MODE="0666", GROUP="plugdev"   # INQ Mobile
SUBSYSTEM=="usb", ATTR{idVendor}=="0482", MODE="0666", GROUP="plugdev"   # Kyocera
SUBSYSTEM=="usb", ATTR{idVendor}=="1004", MODE="0666", GROUP="plugdev"   # LG
SUBSYSTEM=="usb", ATTR{idVendor}=="22b8", MODE="0666", GROUP="plugdev"   # Motorola
SUBSYSTEM=="usb", ATTR{idVendor}=="0409", MODE="0666", GROUP="plugdev"   # NEC
SUBSYSTEM=="usb", ATTR{idVendor}=="2080", MODE="0666", GROUP="plugdev"   # Nook
SUBSYSTEM=="usb", ATTR{idVendor}=="0955", MODE="0666", GROUP="plugdev"   # Nvidia
SUBSYSTEM=="usb", ATTR{idVendor}=="2257", MODE="0666", GROUP="plugdev"   # OTGV
SUBSYSTEM=="usb", ATTR{idVendor}=="10a9", MODE="0666", GROUP="plugdev"   # Pantech
SUBSYSTEM=="usb", ATTR{idVendor}=="1d4d", MODE="0666", GROUP="plugdev"   # Pegatron
SUBSYSTEM=="usb", ATTR{idVendor}=="0471", MODE="0666", GROUP="plugdev"   # Philips
SUBSYSTEM=="usb", ATTR{idVendor}=="04da", MODE="0666", GROUP="plugdev"   # PMC-Sierra
SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", MODE="0666", GROUP="plugdev"   # Qualcomm
SUBSYSTEM=="usb", ATTR{idVendor}=="1f53", MODE="0666", GROUP="plugdev"   # SK Telesys
SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666", GROUP="plugdev"   # Samsung
SUBSYSTEM=="usb", ATTR{idVendor}=="04dd", MODE="0666", GROUP="plugdev"   # Sharp
SUBSYSTEM=="usb", ATTR{idVendor}=="054c", MODE="0666", GROUP="plugdev"   # Sony
SUBSYSTEM=="usb", ATTR{idVendor}=="0fce", MODE="0666", GROUP="plugdev"   # Sony Ericsson / Sony Mobile
SUBSYSTEM=="usb", ATTR{idVendor}=="2340", MODE="0666", GROUP="plugdev"   # Teleepoch
SUBSYSTEM=="usb", ATTR{idVendor}=="2a70", MODE="0666", GROUP="plugdev"   # OnePlus
SUBSYSTEM=="usb", ATTR{idVendor}=="22d9", MODE="0666", GROUP="plugdev"   # OPPO/Realme
SUBSYSTEM=="usb", ATTR{idVendor}=="2d95", MODE="0666", GROUP="plugdev"   # Vivo/BBK
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"   # Xiaomi
UDEV_RULES
chmod a+r "$RULES_FILE"
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

# 8. Start and enable systemd service
echo "=== Loading Systemd Service ==="
systemctl daemon-reload
systemctl enable app-tag-auditor.service
systemctl restart app-tag-auditor.service || true

# Refresh desktop application entry database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi

echo "=== Post-Installation Completed Successfully ==="
POSTINST
chmod 755 "$BUILD_DIR/DEBIAN/postinst"

# B. prerm script
echo -e "${BLUE}Writing prerm script...${NC}"
cat > "$BUILD_DIR/DEBIAN/prerm" << 'PRERM'
#!/usr/bin/env bash
set -e

# Stop and disable systemd service
if systemctl is-active --quiet app-tag-auditor; then
    echo "Stopping App Tag Auditor service..."
    systemctl stop app-tag-auditor || true
fi

if systemctl is-enabled --quiet app-tag-auditor 2>/dev/null; then
    echo "Disabling App Tag Auditor service..."
    systemctl disable app-tag-auditor || true
fi

# Clean up symlinks
rm -f /opt/app-tag-auditor/.env
rm -f /opt/app-tag-auditor/app_tag_auditor/.env
PRERM
chmod 755 "$BUILD_DIR/DEBIAN/prerm"

# C. postrm script
echo -e "${BLUE}Writing postrm script...${NC}"
cat > "$BUILD_DIR/DEBIAN/postrm" << 'POSTRM'
#!/usr/bin/env bash
set -e

if [ "$1" = "purge" ]; then
    echo "Purging App Tag Auditor files..."
    rm -rf /opt/app-tag-auditor
    rm -rf /etc/app-tag-auditor
    rm -f /etc/udev/rules.d/51-app-tag-auditor.rules
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger 2>/dev/null || true
fi

# Reload systemd daemon configuration
systemctl daemon-reload || true
POSTRM
chmod 755 "$BUILD_DIR/DEBIAN/postrm"

# ── 11. Build with dpkg-deb and fakeroot ──────────────────────────────────────
echo -e "${BLUE}Building Debian package using fakeroot and dpkg-deb...${NC}"
fakeroot dpkg-deb --build "$BUILD_DIR" "$DEB_FILE"

# Clean up build directory
echo -e "${BLUE}Cleaning up temporary build folder...${NC}"
rm -rf "$BUILD_DIR"

echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN} Package Created: ${DEB_FILE}${NC}"
echo -e "${GREEN}===============================================${NC}"
echo -e "You can install it by running: sudo dpkg -i ${DEB_FILE}"
