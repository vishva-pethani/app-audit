# 🚀 Deployment Guide — App Tag Auditor

## Prerequisites (one-time setup on any machine)

| Requirement | Notes |
|---|---|
| Docker Engine ≥ 24 | [Install Docker](https://docs.docker.com/engine/install/) |
| Docker Compose v2 | Bundled with Docker Desktop; `docker compose version` to verify |
| Linux host | Required for USB passthrough. Windows users: use WSL2 |
| USB Debugging enabled | On the Android device: Settings → Developer Options → USB Debugging |

---

## Step 1 — Clone the Repository

```bash
git clone <repo-url> app-audit
cd app-audit
```

---

## Step 2 — Create Your `.env` File

```bash
cp app_tag_auditor/.env.example app_tag_auditor/.env
```

Then edit `.env` and fill in:

```env
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_API_KEY=your-api-key
ANTHROPIC_API_KEY=your-anthropic-key
```

> **Note**: The `.env` file is **never** baked into the Docker image — it is bind-mounted at runtime, so secrets stay on your machine.

---

## Step 3 — Build the Image

```bash
docker compose build
# or: make build
```

This only needs to be done once (or after a code update).  
Build time is ~5–10 minutes on first run (downloads JADX, Appium, Node.js).

---

## Step 4 — Connect Android Device & Start

1. **Plug in the USB cable** (device must have USB Debugging enabled)
2. Start the stack:

```bash
docker compose up -d
# or: make up
```

3. Open **http://localhost:8501** in your browser
4. Sign in with Google, then upload the APK and schema — done! ✅

---

## Analyst Workflow (Day-to-Day)

```
1. Connect USB cable to Android device
2. docker compose up -d        ← start everything
3. Open http://localhost:8501
4. Upload APK + schema CSV
5. Click "Run Audit"
6. When done: docker compose down
```

---

## Verify ADB Sees the Device

```bash
# Check from the host
adb devices

# Check from inside the container
make adb-devices
# or: docker exec app-tag-auditor adb devices
```

Expected output:
```
List of devices attached
XXXXXXXXXXXXXXXX	device
```

If the device shows `unauthorized`, accept the RSA fingerprint prompt on the Android device.

---

## Verify Appium is Running

```bash
make appium-status
# or: docker exec app-tag-auditor curl -sf http://localhost:4723/status
```

---

## View Logs

```bash
make logs
# or: docker compose logs -f app-tag-auditor
```

---

## Troubleshooting

### Device not found inside container

- Ensure the host's udev rules allow non-root USB access:
  ```bash
  # On the host (not the container):
  echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="XXXX", MODE="0666"' \
      | sudo tee /etc/udev/rules.d/51-android.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger
  ```
- Try restarting the ADB server on the host:
  ```bash
  adb kill-server && adb start-server
  ```
- On some systems you may need to add your user to the `plugdev` group:
  ```bash
  sudo usermod -aG plugdev $USER && newgrp plugdev
  ```

### Appium not starting

- Check the container logs: `make logs`
- Ensure port 4723 is not occupied on the host

### Permission denied on /dev/bus/usb

- The compose file uses `privileged: true` which gives the container full device access. If your security policy blocks this, alternatively mount only the specific USB bus:
  ```yaml
  devices:
    - /dev/bus/usb/001/XXX:/dev/bus/usb/001/XXX
  ```

---

## Output Files

Audit results (Excel) are written to `./output/audit_results.xlsx` on the **host** machine via volume mount.  
Decompiled APK cache is persisted in `./tmp/` for faster re-runs.

---

## Updating the App

```bash
git pull
docker compose build   # rebuild image with latest code
docker compose up -d
```
