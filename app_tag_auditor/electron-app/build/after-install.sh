#!/usr/bin/env bash
# after-install.sh — Post-install script for App Tag Auditor deb package
set -e

APP_DIR="/opt/App Tag Auditor/resources/app"
echo "=== App Tag Auditor Post-Install Setup ==="
echo "Target directory: $APP_DIR"

# 1. Setup Python Virtual Environment and install requirements
echo "--- Setting up Python virtual environment ---"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 2. Install Appium globally and the UIAutomator2 driver
echo "--- Installing Appium and uiautomator2 driver ---"
export APPIUM_HOME="$APP_DIR/.appium"
mkdir -p "$APPIUM_HOME"
chmod -R 777 "$APPIUM_HOME"
npm install -g appium@latest --unsafe-perm=true || true
appium driver install uiautomator2 || true

# 3. Install JADX
echo "--- Installing JADX decompiler ---"
JADX_VERSION="1.5.0"
JADX_DIR="$APP_DIR/jadx"
if [ ! -f "$JADX_DIR/bin/jadx" ]; then
    mkdir -p "$JADX_DIR"
    wget -q "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" -O /tmp/jadx.zip
    unzip -q /tmp/jadx.zip -d "$JADX_DIR"
    chmod +x "$JADX_DIR/bin/jadx"
    rm -f /tmp/jadx.zip
fi

# 4. Install Android SDK (platform-tools only, lean container footprint design)
echo "--- Installing Android platform-tools ---"
ANDROID_HOME="$APP_DIR/android-sdk"
if [ ! -d "$ANDROID_HOME/platform-tools" ]; then
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    wget -q "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" -O /tmp/cmdline-tools.zip
    unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
    rm -f /tmp/cmdline-tools.zip
    # Use sdkmanager to install platform-tools only (excluding build-tools)
    yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$ANDROID_HOME" "platform-tools"
fi

# 5. Create dynamic output, temp, logs, and sessions directories
echo "--- Creating runtime directories ---"
mkdir -p "$APP_DIR/output" "$APP_DIR/tmp" "$APP_DIR/logs" "$APP_DIR/.sessions"
chmod -R 777 "$APP_DIR/output" "$APP_DIR/tmp" "$APP_DIR/logs" "$APP_DIR/.sessions"

# 6. Setup environment files
# Create default .env inside the installation folder if not present
if [ ! -f "$APP_DIR/.env" ]; then
    echo "--- Creating default environment file ---"
    cat > "$APP_DIR/.env" << 'EOF'
GOOGLE_OAUTH_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501
GOOGLE_API_KEY=your-google-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
LOCAL_OUTPUT_PATH=./output/audit_results.xlsx
TEMP_STORAGE_DIR=./tmp
APPIUM_SERVER_URL=http://localhost:4723
EOF
    chmod 666 "$APP_DIR/.env"
fi

# 7. Setup udev rules for Android USB device connectivity
echo "--- Configuring USB/udev rules for Android Debugging ---"
RULES_FILE="/etc/udev/rules.d/51-app-tag-auditor.rules"
cat > "$RULES_FILE" << 'UDEV_RULES'
# Generic Android USB devices
SUBSYSTEM=="usb", ATTR{idVendor}=="0502", MODE="0666", GROUP="plugdev"   # Acer
SUBSYSTEM=="usb", ATTR{idVendor}=="0b05", MODE="0666", GROUP="plugdev"   # ASUS
SUBSYSTEM=="usb", ATTR{idVendor}=="413c", MODE="0666", GROUP="plugdev"   # Dell
SUBSYSTEM=="usb", ATTR{idVendor}=="0489", MODE="0666", GROUP="plugdev"   # Foxconn
SUBSYSTEM=="usb", ATTR{idVendor}=="04c5", MODE="0666", GROUP="plugdev"   # Fujitsu
SUBSYSTEM=="usb", ATTR{idVendor}=="091e", MODE="0666", GROUP="plugdev"   # Garmin-Asus
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"   # Google
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", MODE="0666", GROUP="plugdev"   # HTC
SUBSYSTEM=="usb", ATTR{idVendor}=="12d1", MODE="0666", GROUP="plugdev"   # Huawei
SUBSYSTEM=="usb", ATTR{idVendor}=="1004", MODE="0666", GROUP="plugdev"   # LG
SUBSYSTEM=="usb", ATTR{idVendor}=="22b8", MODE="0666", GROUP="plugdev"   # Motorola
SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666", GROUP="plugdev"   # Samsung
SUBSYSTEM=="usb", ATTR{idVendor}=="054c", MODE="0666", GROUP="plugdev"   # Sony
SUBSYSTEM=="usb", ATTR{idVendor}=="2a70", MODE="0666", GROUP="plugdev"   # OnePlus
SUBSYSTEM=="usb", ATTR{idVendor}=="22d9", MODE="0666", GROUP="plugdev"   # OPPO/Realme
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"   # Xiaomi
UDEV_RULES
chmod a+r "$RULES_FILE"
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

# 8. Set generic permissions for all compiled files
chmod -R 755 "/opt/App Tag Auditor"

echo "=== Post-Install Setup Completed Successfully ==="
