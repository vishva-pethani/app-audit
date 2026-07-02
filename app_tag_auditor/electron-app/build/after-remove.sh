#!/usr/bin/env bash
# after-remove.sh — Post-remove cleanup script for App Tag Auditor deb package
set -e

if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
    echo "--- Cleaning up App Tag Auditor files ---"
    rm -rf "/opt/App Tag Auditor"
    rm -f /etc/udev/rules.d/51-app-tag-auditor.rules
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger 2>/dev/null || true
fi
