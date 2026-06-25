# ──────────────────────────────────────────────────────────────────────────────
# App Tag Auditor — Docker Image
# Bundles: Python/Streamlit · Node/Appium · Android SDK/ADB · JADX
# Analyst workflow: plug in USB → docker compose up → open browser
# ──────────────────────────────────────────────────────────────────────────────

FROM ubuntu:22.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# ── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utils
    curl wget unzip ca-certificates gnupg \
    # Java (needed for JADX + Appium)
    openjdk-17-jre-headless \
    # Python
    python3 python3-pip python3-venv \
    # ADB / Android debug bridge
    android-tools-adb \
    # udev for USB hot-plug
    udev \
    # Misc
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 (required by Appium 2.x) ──────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Appium 2 + UIAutomator2 driver ───────────────────────────────────────────
RUN npm install -g appium@latest && \
    appium driver install uiautomator2

# ── JADX (APK decompiler) ─────────────────────────────────────────────────────
ARG JADX_VERSION=1.5.0
RUN wget -q "https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip" \
        -O /tmp/jadx.zip \
    && unzip -q /tmp/jadx.zip -d /opt/jadx \
    && chmod +x /opt/jadx/bin/jadx \
    && ln -s /opt/jadx/bin/jadx /usr/local/bin/jadx \
    && rm /tmp/jadx.zip

# ── Android SDK (required by Appium UIAutomator2) ─────────────────────────────
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools && \
    wget -q "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d ${ANDROID_HOME}/cmdline-tools && \
    mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest && \
    rm /tmp/cmdline-tools.zip

# Install platform-tools and build-tools via sdkmanager
RUN yes | ${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager --sdk_root=${ANDROID_HOME} "platform-tools" "build-tools;34.0.0"

# Add to PATH
ENV PATH=${PATH}:${ANDROID_HOME}/platform-tools:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/build-tools/34.0.0

# ── App source code ───────────────────────────────────────────────────────────
WORKDIR /app
COPY app_tag_auditor/ ./app_tag_auditor/

# ── Python dependencies ───────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r app_tag_auditor/requirements.txt

# ── Runtime directories ───────────────────────────────────────────────────────
RUN mkdir -p /app/output /app/logs /app/tmp

# ── udev rule for Android USB devices (applied at runtime via entrypoint) ─────
# The actual udev rule is written by entrypoint.sh so the file is always fresh.

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Streamlit port
EXPOSE 8501
# Appium port
EXPOSE 4723

ENV PYTHONUNBUFFERED=1
ENV JADX_PATH=/usr/local/bin/jadx
ENV APPIUM_SERVER_URL=http://localhost:4723

ENTRYPOINT ["/entrypoint.sh"]
