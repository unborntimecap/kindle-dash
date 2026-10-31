#!/bin/sh
# kindle-dash launcher. Fetches the latest dash-main.sh from the repo, then runs it.
# This is the only file that needs copying to the Kindle. Falls back to the last good copy if offline.
URL="https://raw.githubusercontent.com/unborntimecap/kindle-dash/main/dash-main.sh"
D=/mnt/us
LOG=$D/documents/dash-log.txt
exec >>$LOG 2>&1
lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
sleep 3
if curl -fsSL -m 20 -o $D/dash-main.new "$URL?t=$(date +%s)" && sh -n $D/dash-main.new; then
  mv $D/dash-main.new $D/dash-main.sh && echo "$(date '+%H:%M:%S') launcher: updated dash-main.sh"
else
  rm -f $D/dash-main.new; echo "$(date '+%H:%M:%S') launcher: using cached dash-main.sh"
fi
[ -s $D/dash-main.sh ] && exec sh $D/dash-main.sh
echo "$(date '+%H:%M:%S') launcher: no dash-main.sh available"
