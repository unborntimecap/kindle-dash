#!/bin/bash
# Kindle-ish harness: busybox ash + stubbed device commands, replay touch-raw.bin as the touchscreen.
T=$(mktemp -d); mkdir -p $T/bin $T/mnt/us/documents
cp /usr/bin/busybox $T/bin/busybox
for c in sh ash dd hexdump sleep cp killall date mv rm wc cat head echo kill grep mktemp; do ln -sf $T/bin/busybox $T/bin/$c; done
for c in eips lipc-set-prop; do printf '#!/bin/sh\necho "STUB $0 $*" >> %s/stub.log\n' $T > $T/bin/$c; chmod +x $T/bin/$c; done
printf '#!/bin/sh\n# stub curl: copy the mock png to the -o target\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && { out=$2; shift; }; shift; done\ncp %s/../mock/agenda.png "$out"\n' "$PWD" > $T/bin/curl; chmod +x $T/bin/curl
printf '#!/bin/sh\necho "STUB ping" >> %s/stub.log\n' $T > $T/bin/ping; chmod +x $T/bin/ping
# patch paths: /mnt/us -> $T/mnt/us, touch device -> replay file (appended with a Kindle-tab tap to exit)
python3 - "$T" <<'PY'
import sys,struct
T=sys.argv[1]
b=open('touch-raw.bin','rb').read()
# synth taps: TFC tab, Priorities tab, then Kindle tab (x>1395, y>2330)
def tap(x,y):
    ev=lambda t,c,v: struct.pack('<IIHHi',0,0,t,c,v)
    return ev(3,0x39,0)+ev(3,0x35,x)+ev(3,0x36,y)+ev(0,0,0)+ev(3,0x39,-1)+ev(0,0,0)
open(f'{T}/touch.bin','wb').write(b+tap(1600,100)+tap(1200,100)+tap(1600,100)+tap(1200,100)+tap(700,2400)+tap(1100,2400)+tap(1600,2400))
s=open('../dash-main.sh').read().replace('ping -c1 -W2 1.1.1.1','true').replace('D=/mnt/us',f'D={T}/mnt/us').replace('TOUCH=/dev/input/event4',f'TOUCH={T}/touch.bin')
open(f'{T}/dash.sh','w').write(s)
PY
PATH=$T/bin /usr/bin/timeout 20 $T/bin/sh $T/dash.sh; rc=$?
echo "exit=$rc"; echo "--- dash-log ---"; cat $T/mnt/us/documents/dash-log.txt; echo "--- stubs ---"; grep -v ping $T/stub.log | sed 's#'$T'##g'
