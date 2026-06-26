#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# entrypoint.sh — App Tag Auditor container startup
# 1. Writes udev rules so ADB sees the connected USB device
# 2. Starts the ADB daemon
# 3. Starts Appium server in background
# 4. Launches Streamlit
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "════════════════════════════════════════════════════════"
echo " 🔍  App Tag Auditor — Container Starting"
echo "════════════════════════════════════════════════════════"

# ── 1. Write generic Android udev rules ──────────────────────────────────────
# These rules allow ADB to access any Android device over USB without root.
# The rules file is written fresh every start in case the container is updated.
RULES_FILE=/etc/udev/rules.d/51-android.rules
if [ ! -f "$RULES_FILE" ]; then
    echo "⚙️  Writing Android udev rules..."
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
SUBSYSTEM=="usb", ATTR{idVendor}=="0930", MODE="0666", GROUP="plugdev"   # Toshiba
SUBSYSTEM=="usb", ATTR{idVendor}=="19d2", MODE="0666", GROUP="plugdev"   # ZTE
# One Plus, Realme, OPPO, Vivo, Xiaomi — use Qualcomm (05c6) or own VID
SUBSYSTEM=="usb", ATTR{idVendor}=="2a70", MODE="0666", GROUP="plugdev"   # OnePlus
SUBSYSTEM=="usb", ATTR{idVendor}=="22d9", MODE="0666", GROUP="plugdev"   # OPPO/Realme
SUBSYSTEM=="usb", ATTR{idVendor}=="2d95", MODE="0666", GROUP="plugdev"   # Vivo/BBK
SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"   # Xiaomi
UDEV_RULES
    chmod a+r "$RULES_FILE"
fi

# Try to reload udev (may silently fail inside Docker — that's OK,
# the host udev handles the actual hotplug in --privileged mode)
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

# ── 2. Start ADB server ───────────────────────────────────────────────────────
echo "📱 Starting ADB server..."
adb start-server 2>&1 || true

# Wait briefly and list devices
sleep 2
echo "── Connected Android devices ──"
adb devices
echo "───────────────────────────────"

# ── 3. Start Appium server in background ─────────────────────────────────────
echo "🤖 Starting Appium server on port 4723 (localhost only)..."
appium --address 127.0.0.1 --log-level error &
APPIUM_PID=$!

# Wait for Appium to be ready
MAX_WAIT=30
WAITED=0
until curl -sf http://localhost:4723/status > /dev/null 2>&1; do
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "⚠️  Appium did not start within ${MAX_WAIT}s — continuing anyway"
        break
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done
if curl -sf http://localhost:4723/status > /dev/null 2>&1; then
    echo "✅ Appium server is ready"
fi

# ── 4. Run the .env file if provided via bind-mount ──────────────────────────
ENV_FILE=/app/app_tag_auditor/.env
if [ -f "$ENV_FILE" ]; then
    echo "🔑 .env file detected — credentials loaded"
else
    echo "⚠️  No .env file found at $ENV_FILE"
    echo "   Create one from .env.example and restart, or set env vars."
fi

# ── 5. Launch Streamlit ───────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo " 🚀  Streamlit starting → http://localhost:8501"
echo "════════════════════════════════════════════════════════"
echo ""

cd /app
STREAMLIT_PORT=${PORT:-8501}
exec streamlit run app_tag_auditor/frontend/app.py \
    --server.port "$STREAMLIT_PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.maxUploadSize 500 \
    --browser.gatherUsageStats false
