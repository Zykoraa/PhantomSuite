#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"

if [ "$1" == "--uninstall" ]; then
    echo "[*] Uninstalling PhantomSuite..."
    rm -f "${BIN_DIR}/phantom-suite"
    rm -f "${DESKTOP_DIR}/phantom-suite.desktop"
    rm -f "${ICON_DIR}/phantom-suite.svg"
    echo "[+] PhantomSuite uninstalled successfully."
    exit 0
fi

echo "[*] Installing PhantomSuite..."

mkdir -p "${BIN_DIR}" "${DESKTOP_DIR}" "${ICON_DIR}"

# 1. Compile native payloads if gcc is available
if command -v gcc &>/dev/null && [ -f "${SCRIPT_DIR}/phantom_suite/payloads/speedhack.c" ]; then
    echo "[*] Building speedhack payload..."
    gcc -shared -fPIC -O2 "${SCRIPT_DIR}/phantom_suite/payloads/speedhack.c" -o "${SCRIPT_DIR}/phantom_suite/payloads/speedhack.so" -lrt 2>/dev/null || true
fi

# 2. Symlink launcher
ln -sf "${SCRIPT_DIR}/phantom-suite" "${BIN_DIR}/phantom-suite"
chmod +x "${SCRIPT_DIR}/phantom-suite" "${SCRIPT_DIR}/phantom_suite/app.py"

# 3. Copy icon
cp -f "${SCRIPT_DIR}/resources/phantom-suite.svg" "${ICON_DIR}/phantom-suite.svg"

# 3. Install desktop file
cp -f "${SCRIPT_DIR}/resources/phantom-suite.desktop" "${DESKTOP_DIR}/phantom-suite.desktop"

# 4. Update desktop database if available
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi

echo "[+] PhantomSuite installed successfully!"
echo "    Launcher: ${BIN_DIR}/phantom-suite"
echo "    You can launch it via application menu or run 'phantom-suite'."
