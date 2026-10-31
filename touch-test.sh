#!/bin/sh
# Touch input diagnostics v3. Tap this "book", then within 15 s:
# tap TOP-LEFT, tap BOTTOM-RIGHT, press the POWER button once.
# Raw bytes go to documents/touch-raw.bin and power-raw.bin; decoded log in touch-test-log.txt

D=/mnt/us/documents
LOG=$D/touch-test-log.txt
rm -f $D/touch-raw.bin $D/power-raw.bin
cat /dev/input/event4 > $D/touch-raw.bin &
P1=$!
cat /dev/input/event0 > $D/power-raw.bin &
P2=$!
sleep 15
kill $P1 $P2 2>/dev/null
{
echo "=== touch test v3 $(date) ==="
echo "touch bytes: $(wc -c < $D/touch-raw.bin)  power bytes: $(wc -c < $D/power-raw.bin)"
echo "--- touch events (type code value) ---"
hexdump -v -e '2/4 "" 1/2 "%04x " 1/2 "%04x " 1/4 "%08x\n"' $D/touch-raw.bin | head -300
echo "--- power events ---"
hexdump -v -e '2/4 "" 1/2 "%04x " 1/2 "%04x " 1/4 "%08x\n"' $D/power-raw.bin | head -50
echo "=== end ==="
} > "$LOG" 2>&1
