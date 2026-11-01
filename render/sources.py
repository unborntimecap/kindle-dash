"""Data sources for the Kindle dashboard. Every function degrades to a safe fallback so a dead
source produces a stale page, never a missing one. Secrets come from env vars (GitHub Actions secrets)."""
import os, re, json, datetime as dt, base64
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
TZ = ZoneInfo("Australia/Sydney")
CACHE = HERE / "cache"; CACHE.mkdir(exist_ok=True)

CALS = {  # key -> (env var holding the ICS URL, fallback)
    "adhoc": "ICS_ADHOC",
    "work":  "ICS_WORK",
    "hos":   "ICS_HOSPORTAL",
}
HOSP = [  # long hospital names -> short, used for HosPortal titles
    ("Royal Prince Alfred Hospital", "RPA"),
    ("Prince of Wales Public Hospital", "POWPH"),
    ("Prince of Wales Private Hospital", "POWP"),
    ("St George Private Hospital", "StGP"),
    ("Macquarie University Hospital", "MUH"),
]

def _get(url, **kw):
    r = requests.get(url, timeout=30, **kw); r.raise_for_status(); return r

def _cached(name, fetch):
    """Return fetch(); on failure return the last good copy from cache (or None)."""
    f = CACHE / name
    try:
        data = fetch(); f.write_text(data); return data
    except Exception as e:
        print(f"[warn] {name}: {e}; using cache" if f.exists() else f"[warn] {name}: {e}; no cache")
        return f.read_text() if f.exists() else None

# ---------- calendars ----------
def _short_hos(summary, location):
    """'Allocations - Grant - Cardiac OT 2 - Prince of Wales Public Hospital' -> ('Grant - POWPH', 'Cardiac OT 2')"""
    t = summary
    for long, short in HOSP: t = t.replace(long, short)
    parts = [p.strip() for p in t.split(" - ")]
    if parts[0] == "Allocations" and len(parts) >= 4:
        return f"{parts[1]} - {parts[-1]}", location or parts[2]
    if parts[0] == "Allocations" and len(parts) == 3:
        return f"{parts[1]} - {parts[2]}", location
    return t, location

def events(days_back=1, days_fwd=70):
    """All events from the three calendars as the mock's dict format, expanded for recurrence."""
    from icalendar import Calendar
    import recurring_ical_events
    start = dt.datetime.now(TZ).date() - dt.timedelta(days=days_back)
    end = start + dt.timedelta(days=days_fwd + days_back)
    out = []
    for cal, env in CALS.items():
        url = os.environ.get(env)
        if not url:
            print(f"[warn] {env} not set, skipping {cal}"); continue
        url = url.replace("webcal://", "https://")
        text = _cached(f"{cal}.ics", lambda: _get(url).text)
        if not text: continue
        ics = Calendar.from_ical(text)
        for ev in recurring_ical_events.of(ics).between(start, end):
            if str(ev.get("STATUS", "")).upper() == "CANCELLED": continue
            s, e = ev["DTSTART"].dt, ev.get("DTEND", ev["DTSTART"]).dt
            title = str(ev.get("SUMMARY", "")).strip()
            loc = str(ev.get("LOCATION", "") or "").strip()
            if cal == "hos": title, loc = _short_hos(title, loc)
            if isinstance(s, dt.datetime):
                s = s.astimezone(TZ); e = e.astimezone(TZ) if isinstance(e, dt.datetime) else s
                out.append(dict(cal=cal, date=s.date().isoformat(), allday=False,
                                start=s.strftime("%H:%M"), endt=e.strftime("%H:%M"), title=title, loc=loc))
            else:  # all-day; DTEND is exclusive
                out.append(dict(cal=cal, date=s.isoformat(), end=e.isoformat() if e != s else None,
                                allday=True, title=title, loc=loc))
    return out

# ---------- priorities (vault note via GitHub API, fallback priorities.md in this repo) ----------
def _vault_note():
    tok, repo, path = os.environ.get("VAULT_TOKEN"), os.environ.get("VAULT_REPO", "unborntimecap/secondbrain-vault"), \
                      os.environ.get("VAULT_NOTE", "Command-Center/cowork-todo.md")
    if not tok: raise RuntimeError("VAULT_TOKEN not set")
    r = _get(f"https://api.github.com/repos/{repo}/contents/{path}",
             headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    return base64.b64decode(r.json()["content"]).decode()

NOTES = {}  # section -> prose lines (filled by priorities())

def priorities():
    """[(section, [(title, due), ...]), ...]. Reads the vault note's '## Active' block: '### X' sub-headings are
    sections, lines '- [ ] **Title** — detail | due' or '- [ ] text | due'. Falls back to priorities.md (## sections)."""
    text = _cached("cowork-todo.md", _vault_note)
    NOTES.clear()
    if text and "## Active" in text:
        body = text.split("## Active", 1)[1]
        body = re.split(r"\n## ", body)[0]  # stop at the next H2 (e.g. ## Done)
        secs, cur = [], ("Active", [])
        for line in body.splitlines():
            if line.startswith("### "):
                if cur[1]: secs.append(cur)
                cur = (line[4:].strip(), [])
            elif line.startswith("- [ ] "):
                item, _, due = line[6:].partition("|")
                m = re.match(r"\*\*(.+?)\*\*", item.strip())
                title = m.group(1) if m else item.strip()
                cur[1].append((title.strip(), due.strip()))
            elif line.strip() and not line.lstrip().startswith(("-", "#", "[")):
                NOTES.setdefault(cur[0], []).append(line.strip())  # prose under a section, e.g. the TFC "Now" blurb
        if cur[1]: secs.append(cur)
        if secs: return secs
    print("[warn] vault note unavailable or empty, using priorities.md")
    return repo_priorities()

def repo_priorities():
    secs, cur = [], None
    for line in (ROOT / "priorities.md").read_text().splitlines():
        if line.startswith("## "):
            cur = (line[3:].strip(), []); secs.append(cur)
        elif line.startswith("- [ ] ") and cur:
            t, _, due = line[6:].partition("|"); cur[1].append((t.strip(), due.strip()))
    return secs

# ---------- TFC stats (Supabase RPC, service key) ----------
def tfc():
    url, key = os.environ.get("SUPABASE_URL", "https://oxkdndtmcjrthkehztos.supabase.co"), os.environ.get("SUPABASE_SERVICE_KEY")
    def fetch():
        if not key: raise RuntimeError("SUPABASE_SERVICE_KEY not set")
        r = requests.post(f"{url}/rest/v1/rpc/kindle_stats", headers={"apikey": key, "Authorization": f"Bearer {key}"}, json={}, timeout=30)
        r.raise_for_status(); return r.text
    text = _cached("tfc.json", fetch)
    if not text: return None
    d = json.loads(text)
    d["exam"] = dt.date.fromisoformat(d["exam"]) if d.get("exam") else None
    d["ending"] = [(x["name"], x["date"]) for x in d.get("ending", [])]
    return d

def hide_list():
    return [l.strip().lower() for l in (ROOT / "hide.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]


# ---------- TFC "Now" box: next workstream from the TFC repo's CLAUDE.md ----------
def _tfc_claude_md():
    tok, repo = os.environ.get("VAULT_TOKEN"), os.environ.get("TFC_REPO", "unborntimecap/thefinalcountdown")
    if not tok: raise RuntimeError("VAULT_TOKEN not set")
    r = _get(f"https://api.github.com/repos/{repo}/contents/CLAUDE.md",
             headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.raw+json"})
    return r.text

def _short(line, n=78):
    """Strip doc paths to their slug, collapse backticks, cut at n chars."""
    line = re.sub(r"`docs/(?:HANDOFF|RFC|SCOPING|DECISION)-(?:\d{4}-\d{2}-\d{2}-)?([^`]+?)(?:-v\d)?\.md`", r"\1", line)
    line = re.sub(r"`([^`]*)`", r"\1", line).replace(" — ", ": ").replace("—", ",").strip()
    return line if len(line) <= n else line[:n-1].rstrip() + "…"

def tfc_now():
    """dict(gate, headline, do_first, finish) from CLAUDE.md 'Open workstreams', or None if it cannot be parsed.
    Conventions it relies on: a bold '**Build next (…)**' heading with bullets, a '**Finish now**' heading with
    bullets, and a 'Do first (…): …' sentence under '### Architecture health'."""
    text = _cached("tfc-claude.md", _tfc_claude_md)
    if not text: return None
    m = re.search(r"\*\*Build next(?: \(([^)]*)\))?\*\*\n((?:- .*\n?)+)", text)
    if not m: return None
    gate, first = (m.group(1) or "").strip(), m.group(2).splitlines()[0][2:]
    headline = _short(re.split(r"(?<=[.;])\s| \+ ", first, 1)[0], 110)
    f = re.search(r"\*\*Finish now\*\*\n((?:- .*\n?)+)", text)
    finish = [_short(l[2:]) for l in f.group(1).splitlines()] if f else []
    d = re.search(r"Do first[^:]*:\s*(.+?\.)\s", text)
    do_first = _short(re.sub(r"\s*\([^)]*\)", "", d.group(1)), 110) if d else ""
    return dict(gate=gate, headline=headline, do_first=do_first, finish=finish)
