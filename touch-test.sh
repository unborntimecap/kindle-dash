#!/bin/sh
# Touch input diagnostics v2. Tap this "book", then within 15 s:
# tap TOP-LEFT, tap BOTTOM-RIGHT, press the POWER button once.
# Results in documents/touch-test-log.txt

LOG=/mnt/us/documents/touch-test-log.txt
{
echo "=== touch test v2 $(date) ==="
echo "--- touch (event4) and power (event0), 15 s ---"
hexdump -v -e '4/4 "%08x " "\n"' /dev/input/event4 2>&1 | sed 's/^/T /' >> "$LOG" &
P1=$!
hexdump -v -e '4/4 "%08x " "\n"' /dev/input/event0 2>&1 | sed 's/^/P /' >> "$LOG" &
P2=$!
sleep 15
kill $P1 $P2 2>/dev/null
killall hexdump 2>/dev/null
echo "--- screen geometry ---"
eips -i 2>/dev/null | head -20
echo "=== end ==="
} >> "$LOG" 2>&1
