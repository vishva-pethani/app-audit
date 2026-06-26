#!/usr/bin/env bash
# build.sh — Render build script
# Installs Python dependencies + downloads JADX binary into the repo
set -e

echo "=== Installing Python dependencies ==="
pip install -r app_tag_auditor/requirements.txt

echo "=== Installing JADX ==="
JADX_VERSION="1.5.0"
# Install into the repo itself so the path is stable between build and runtime
JADX_DIR="$(pwd)/.jadx"
JADX_BIN="$JADX_DIR/bin/jadx"

if [ ! -f "$JADX_BIN" ]; then
    mkdir -p "$JADX_DIR"
    curl -fsSL "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" \
        -o /tmp/jadx.zip
    unzip -q /tmp/jadx.zip -d "$JADX_DIR"
    chmod +x "$JADX_BIN"
    rm /tmp/jadx.zip
    echo "JADX installed at $JADX_BIN"
else
    echo "JADX already cached at $JADX_BIN"
fi

# Also install Java if not present (JADX needs JRE)
if ! command -v java &>/dev/null; then
    echo "=== Java not found — installing OpenJDK 17 ==="
    apt-get update -qq && apt-get install -y --no-install-recommends openjdk-17-jre-headless
fi

echo "=== Build complete ==="
