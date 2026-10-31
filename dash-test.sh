#!/bin/sh
# Kindle dashboard smoke test. Tap this "book" on the Kindle (Wi-Fi on).
# Proves: (1) which fetcher does HTTPS, (2) eips can paint a 1860x2480 grey PNG.
# Results land in documents/dash-test-log.txt (open it like a book, or via OpenMTP).

URL="https://raw.githubusercontent.com/unborntimecap/kindle-dash/main/dash.png"   # <- edit before copying to the Kindle
PNG=/mnt/us/dash.png
LOG=/mnt/us/documents/dash-test-log.txt

{
echo "=== dash test $(date) ==="
echo "fw: $(cat /etc/version.txt 2>/dev/null | head -1)"
echo "wget: $(which wget)  curl: $(which curl)"
rm -f "$PNG"

# 1. fetch: try curl, then busybox wget (older busybox has no TLS)
if which curl >/dev/null 2>&1; then
  curl -fsSL -o "$PNG" "$URL" && echo "fetch: curl OK" || echo "fetch: curl FAILED rc=$?"
fi
if [ ! -s "$PNG" ]; then
  wget -q -O "$PNG" "$URL" && echo "fetch: wget OK" || echo "fetch: wget FAILED rc=$?"
fi
[ -s "$PNG" ] && echo "png bytes: $(wc -c < "$PNG")" || { echo "NO PNG, stopping"; exit 1; }

# 2. paint: stop the UI repainting over us for 60 s, then eips
# lipc-set-prop com.lab126.powerd preventScreenSaver 1  # uncomment if the screensaver clobbers it
eips -c
eips -g "$PNG" && echo "eips -g OK" || echo "eips -g FAILED rc=$?"
eips -f -g "$PNG" >/dev/null 2>&1 && echo "eips -f -g OK (full refresh)"
echo "painted at $(date). Look at the screen now; it may be overwritten by the UI in a few seconds."
sleep 20
echo "=== end ==="
} >> "$LOG" 2>&1
