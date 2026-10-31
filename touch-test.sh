#!/bin/sh
# Touch input diagnostics. Tap this "book", then during the next 15 s tap the
# screen: once top-left, once bottom-right. Results in documents/touch-test-log.txt

LOG=/mnt/us/documents/touch-test-log.txt
{
echo "=== touch test $(date) ==="
echo "--- /proc/bus/input/devices ---"
cat /proc/bus/input/devices 2>/dev/null
echo "--- /dev/input ---"
ls -l /dev/input 2>/dev/null
echo "--- framework processes ---"
ps | grep -iE 'cvm|framework|blanket|pillow|lipc' | grep -v grep
echo "--- events (15 s): tap TOP-LEFT then BOTTOM-RIGHT now ---"
for d in /dev/input/event*; do
  ( timeout -t 15 hexdump -v -e '4/4 "%08x " "\n"' "$d" 2>/dev/null | head -200 | sed "s#^#$d #" ) &
done
sleep 16
echo "=== end ==="
} >> "$LOG" 2>&1
