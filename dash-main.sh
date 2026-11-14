#!/bin/sh
# kindle-dash v2.1. Tap this "book" to enter dashboard mode.
# Footer tabs: Agenda | TFC | Priorities | Fam | Kindle (exit). Fam header button cycles All > Leah > Harper > Elijah. Header buttons on calendar pages: [Month/Week] [Next/Back].
# Tap anywhere else to refresh.
# Pages refresh every REFRESH seconds. Log: documents/dash-log.txt

BASE="https://raw.githubusercontent.com/unborntimecap/kindle-dash/render"
PAGES="agenda agenda-next month month-next tfc priorities kids kids-l kids-h kids-e"
REFRESH=1800
D=/mnt/us
LOG=$D/documents/dash-log.txt
TOUCH=/dev/input/event4
PAGE=agenda
exec >>$LOG 2>&1   # keep eips/curl chatter off the screen

log() { echo "$(date '+%H:%M:%S') $*" >> $LOG; }

wifi_up() {  # $1 = max seconds to wait; Kindle Wi-Fi takes ~60 s to come back from sleep
  lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
  i=0; while [ $i -lt ${1:-30} ]; do
    ping -c1 -W2 1.1.1.1 >/dev/null 2>&1 && return 0
    sleep 1; i=$((i+1))
  done; return 1
}

get() {  # $1 = page name; download only. On failure keep last good copy and mark it old
  curl -fsSL -m 30 -o $D/dash-$1.new "$BASE/$1.png?t=$(date +%s)" \
    && mv $D/dash-$1.new $D/dash-$1.png && rm -f $D/dash-$1.old && log "fetched $1" \
    || { rm -f $D/dash-$1.new; : > $D/dash-$1.old; log "fetch $1 failed"; return 1; }
}

fetch() {  # $1 = page name
  wifi_up 30 || { : > $D/dash-$1.old; log "wifi down, keeping cached $1"; return 1; }
  get $1
}

fetch_all() {  # wake Wi-Fi once (long wait), then pull every page
  wifi_up 90 || { for p in $PAGES; do : > $D/dash-$p.old; done; log "wifi down, all pages cached"; return 1; }
  for p in $PAGES; do get $p; done
}

show() {  # $1 = page name
  PAGE=$1
  [ -s $D/dash-$1.png ] || fetch $1 || return 1
  eips -f -g $D/dash-$1.png
  if [ -e $D/dash-$1.old ]; then eips 36 7 "OLD COPY - offline $(date +%H:%M)"
  else eips 36 7 "fetched $(date +%H:%M)"; fi   # char cells ~17x24 px; row 7 = the "rendered" line (y 167-195 on every page)
  log "shown $1"
}


# --- screensaver: paint the TFC page whenever the Kindle goes to sleep ---
# Runs as its own background process ("sh dash-main.sh saver"), started on every dashboard launch.
# Turn off: put a file named saver-off.txt in documents, then reboot.
if [ "$1" = saver ]; then
  echo $$ > $D/dash-saver.pid; log "saver: watching"
  lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver | while read ev rest; do
    case "$ev" in
      goingToScreenSaver) sleep 2; [ -s $D/dash-tfc.png ] && eips -f -g $D/dash-tfc.png && log "saver: painted tfc" ;;
      outOfScreenSaver)   ( wifi_up 90 && get tfc ) & ;;   # refresh the copy for next sleep
    esac
  done
  exit 0
fi

start_saver() {  # (re)start the watcher so it always runs the latest script
  [ -s $D/dash-saver.pid ] && kill -- -$(cat $D/dash-saver.pid) 2>/dev/null
  rm -f $D/dash-saver.pid
  [ -e $D/documents/saver-off.txt ] && { log "saver: off"; return; }
  if command -v setsid >/dev/null; then setsid sh $D/dash-main.sh saver </dev/null >>$LOG 2>&1 &
  else sh $D/dash-main.sh saver </dev/null >>$LOG 2>&1 & fi
}

enter() {
  log "=== enter dashboard ==="
  lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
  killall -STOP framework 2>/dev/null
  start_saver
  show agenda                 # paint cached copy straight away (no black screen)
  fetch_all; show agenda      # repaint: fresh pages, or OLD COPY stamp if offline
  # background refresher
  ( while sleep $REFRESH; do fetch_all; show $PAGE; done ) &
  REFRESHER=$!
}

leave() {
  trap - INT TERM EXIT
  log "=== leave dashboard ==="
  kill $REFRESHER 2>/dev/null
  killall -CONT framework 2>/dev/null
  lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
  # force the UI to repaint over our image
  lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
  sleep 2; eips -f
  exit 0
}
trap leave INT TERM EXIT

enter
X=0; Y=0
exec 3<$TOUCH    # open once; reopening per event drops events queued in between
# read one 16-byte input event at a time: type code value
while :; do
  set -- $(dd bs=16 count=1 <&3 2>/dev/null | dd bs=8 skip=1 2>/dev/null | hexdump -v -e '1/2 "%u " 1/2 "%u " 1/4 "%u\n"')
  [ -n "$1" ] || { log "touch device closed"; leave; }
  [ "$1" = "3" ] || continue
  case "$2" in
    53) X=$3 ;;                       # ABS_MT_POSITION_X
    54) Y=$3 ;;                       # ABS_MT_POSITION_Y
    57) [ "$3" = "4294967295" ] || continue   # ABS_MT_TRACKING_ID = -1 => finger up
        log "tap $X,$Y"
        if [ $Y -gt 2330 ]; then
          if   [ $X -lt 372 ];  then show agenda
          elif [ $X -lt 744 ];  then show tfc
          elif [ $X -lt 1116 ]; then show priorities
          elif [ $X -lt 1488 ]; then show kids
          else leave; fi
        elif [ $Y -lt 190 ] && [ $X -gt 1080 ]; then
          # header buttons on calendar pages: left = Month/Week toggle, right = Next/Back toggle
          case "$PAGE" in
            agenda)      [ $X -gt 1450 ] && show agenda-next || show month ;;
            agenda-next) [ $X -gt 1450 ] && show agenda      || show month ;;
            month)       [ $X -gt 1450 ] && show month-next  || show agenda ;;
            month-next)  [ $X -gt 1450 ] && show month       || show agenda ;;
            kids)   show kids-l ;;
            kids-l) show kids-h ;;
            kids-h) show kids-e ;;
            kids-e) show kids ;;
            *) fetch $PAGE; show $PAGE ;;
          esac
        else
          fetch $PAGE; show $PAGE
        fi ;;
  esac
done
