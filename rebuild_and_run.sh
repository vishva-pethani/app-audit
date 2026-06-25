#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# rebuild_and_run.sh — Rebuilds and launches the App Tag Auditor container
# 1. Kills and stops any running containers
# 2. Rebuilds the docker image
# 3. Spins up the stack in detached mode
# 4. Follows the logs
# ──────────────────────────────────────────────────────────────────────────────
set -e

# Change directory to the script directory to ensure path consistency
cd "$(dirname "$0")"

echo "🛑 Stopping and removing running container..."
docker compose down

echo "🏗️  Rebuilding docker image (using cache)..."
docker compose build

echo "🚀 Starting App Tag Auditor..."
docker compose up -d

echo "📊 Attaching to logs..."
docker compose logs -f app-tag-auditor
