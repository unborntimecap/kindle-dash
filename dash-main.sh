#!/bin/sh
# kindle-dash v2.0. Tap this "book" to enter dashboard mode.
# Footer tabs: Agenda | TFC | Priorities | Kids | Kindle (exit). Kids header button cycles All > Leah > Harper > Elijah. Header buttons on calendar pages: [Month/Week] [Next/Back].
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

wifi_up() {
  lipc-set-prop com.lab126.cmd wirelessEnable 1 2>/dev/null
  i=0; while [ $i -lt 20 ]; do
    ping -c1 -W2 1.1.1.1 >/dev/null 2>&1 && return 0
    sleep 1; i=$((i+1))
  done; return 1
}

fetch() {  # $1 = page name; keeps last good copy on failure
  wifi_up || { log "wifi down, keeping cached $1"; return 1; }
  curl -fsSL -m 30 -o $D/dash-$1.new "$BASE/$1.png?t=$(date +%s)" \
    && mv $D/dash-$1.new $D/dash-$1.png && log "fetched $1" \
    || { rm -f $D/dash-$1.new; log "fetch $1 failed"; return 1; }
}

show() {  # $1 = page name
  PAGE=$1
  [ -s $D/dash-$1.png ] || fetch $1 || return 1
  eips -f -g $D/dash-$1.png
  eips 36 7 "fetched $(date +%H:%M)"   # char cells ~17x24 px; row 7 = the "rendered" line (y 167-195 on every page)
  log "shown $1"
}

enter() {
  log "=== enter dashboard ==="
  lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
  killall -STOP framework 2>/dev/null
  for p in $PAGES; do fetch $p; done
  show agenda
  # background refresher
  ( while sleep $REFRESH; do for p in $PAGES; do fetch $p; done; show $PAGE; done ) &
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
