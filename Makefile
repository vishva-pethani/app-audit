# ──────────────────────────────────────────────────────────────────────────────
# Makefile — App Tag Auditor convenience targets
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: build up down logs shell status

## Build the Docker image
build:
	docker compose build

## Start the stack (detached)
up:
	docker compose up -d
	@echo ""
	@echo "  ✅  App is starting → http://localhost:8501"
	@echo "  Run 'make logs' to watch startup output."

## Start the stack in the foreground (shows all logs)
up-fg:
	docker compose up

## Stop the stack
down:
	docker compose down

## Follow container logs
logs:
	docker compose logs -f app-tag-auditor

## Open a shell inside the running container
shell:
	docker exec -it app-tag-auditor bash

## Show ADB devices visible inside container
adb-devices:
	docker exec app-tag-auditor adb devices

## Show Appium status
appium-status:
	docker exec app-tag-auditor curl -sf http://localhost:4723/status | python3 -m json.tool

## Container health / status
status:
	docker compose ps

## Run Electron development mode
electron-dev:
	cd app_tag_auditor/electron-app && npm run dev

## Build and package Electron app
electron-build:
	cd app_tag_auditor/electron-app && npm run package
