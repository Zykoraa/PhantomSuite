#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[*] Compiling hello_payload.so..."
gcc -shared -fPIC -O2 "${DIR}/hello_payload.c" -o "${DIR}/hello_payload.so"

echo "[*] Compiling dummy_target..."
gcc -O0 "${DIR}/dummy_target.c" -o "${DIR}/dummy_target"

echo "[+] Build complete!"
echo "    Payload: ${DIR}/hello_payload.so"
echo "    Target:  ${DIR}/dummy_target"
echo ""
echo "To test:"
echo "  1. Run the target in a terminal: ${DIR}/dummy_target"
echo "  2. Open PhantomSuite and attach to 'dummy_target'."
echo "  3. Go to the '.so Injector' tab, browse to ${DIR}/hello_payload.so, and click 'Inject Payload'."
echo "  4. Watch for the desktop notification and check: cat /tmp/phantom_test.log"
