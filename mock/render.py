"""Mockup renderer: events.json -> agenda/daily/month HTML -> 1860x2480 greyscale PNG."""
import json, datetime as dt, calendar, html, asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

HERE = Path(__file__).parent
TODAY = dt.date.today()  # real date; the live renderer does the same
EV = json.loads((HERE / "events.json").read_text())
for e in EV:
    e["d"] = dt.date.fromisoformat(e["date"])

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1860px;height:2480px;background:#fff;color:#000;font-family:'DejaVu Sans',Helvetica,Arial,sans-serif;padding:60px 70px;overflow:hidden}
h1{font-size:64px;font-weight:700;letter-spacing:-1px}
.hdr{display:flex;justify-content:space-between;align-items:baseline;border-bottom:6px solid #000;padding-bottom:18px;margin-bottom:30px}
.hdr .sub{font-size:34px;color:#555}
.day{margin-bottom:26px;padding-left:24px;border-left:8px solid #fff}
.day.today{border-left-color:#000}
.day h2{font-size:42px;font-weight:700;margin-bottom:8px}
.day h2 span{font-weight:400;color:#555;font-size:34px;margin-left:16px}
.ev{display:flex;font-size:36px;line-height:1.35;padding:4px 0 4px 0}
.ev .t{width:230px;flex:none;color:#333;font-variant-numeric:tabular-nums}
.ev .m{width:34px;height:34px;flex:none;margin:8px 18px 0 0;border:4px solid #000}
.work .m{background:#000}
.hos .m{background:repeating-linear-gradient(45deg,#000 0 4px,#fff 4px 8px)}
.adhoc .m{background:#fff}
.ev .loc{color:#666;margin-left:14px}
.empty{font-size:34px;color:#888;font-style:italic;padding:4px 0}
.legend{position:absolute;bottom:200px;left:70px;right:70px;display:flex;gap:48px;font-size:30px;color:#444;border-top:3px solid #000;padding-top:16px}
.legend .m{margin-top:4px}
.nav{position:absolute;left:0;right:0;bottom:0;height:150px;border-top:6px solid #000;display:flex}
.nav div{flex:1;display:flex;align-items:center;justify-content:center;font-size:40px;font-weight:700;border-right:6px solid #000}
.nav div:last-child{border-right:0}
.nav .on{background:#000;color:#fff}
.foot{position:absolute;bottom:60px;right:70px;font-size:28px;color:#888}
/* daily */
.grid{position:relative;height:1840px;border-top:3px solid #ccc}
.hr{position:absolute;left:0;right:0;border-top:3px solid #ddd;font-size:30px;color:#777;padding-left:6px}
.hr.now{border-top:6px solid #000}
.blk{position:absolute;left:170px;right:20px;border:5px solid #000;padding:10px 18px;font-size:38px;background:#fff;overflow:hidden}
.blk.hos{background:repeating-linear-gradient(45deg,#fff 0 10px,#e6e6e6 10px 20px)}
.blk .loc{font-size:30px;color:#444}
.allday{font-size:36px;margin-bottom:24px;display:flex;flex-wrap:wrap;gap:14px 40px}
/* month */
table{width:100%;height:1940px;border-collapse:collapse;table-layout:fixed}
th{font-size:34px;padding:10px 0;border-bottom:5px solid #000}
td{vertical-align:top;border:3px solid #bbb;padding:10px 12px;font-size:28px;line-height:1.3}
td .n{font-size:40px;font-weight:700;margin-bottom:6px}
td.today{border:8px solid #000}
td.other .n{color:#aaa}
td .e{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center}
td .m{width:20px;height:20px;border:3px solid #000;margin:0 10px 0 0;flex:none}
"""

def mark(e): return f'<span class="m"></span>'
def legend(): return ('<div class="legend"><span class="ev work"><span class="m"></span>Regular work</span>'
                      '<span class="ev hos"><span class="m"></span>HosPortal</span>'
                      '<span class="ev adhoc"><span class="m"></span>Adhoc</span></div>')

def events_on(d, merge=True):
    out = [dict(e) for e in EV if e["d"] == d or (e.get("end") and e["d"] <= d < dt.date.fromisoformat(e["end"]))]
    hide = [l.strip().lower() for l in (HERE.parent / "hide.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    out = [e for e in out if not any(h in e["title"].lower() for h in hide)]
    if merge:
        # HosPortal on-call duplicates an Adhoc "O/C" entry for the same hospital that day
        def hosp(t):
            t = t.upper()
            return "POW" if "POW" in t or "PRINCE OF WALES" in t else "RPA" if "RPA" in t or "PRINCE ALFRED" in t else None
        oc = {hosp(e["title"]) for e in out if e["cal"] == "adhoc" and "O/C" in e["title"].upper()}
        out = [e for e in out if not (e["cal"] == "hos" and e["title"].startswith("Call") and hosp(e["title"]) in oc)]
        work = [e for e in out if e["cal"] == "work"]
        hos_alloc = [e for e in out if e["cal"] == "hos" and not e.get("allday")]
        if work and hos_alloc:
            first = min(hos_alloc, key=lambda e: e["start"])
            for w in work:
                w["allday"] = False; w["start"] = first["start"]; w["endt"] = max(hos_alloc, key=lambda e: e["endt"])["endt"]
                w["loc"] = first.get("loc", "")
            out = [e for e in out if e not in hos_alloc]
        elif hos_alloc and not work:
            for e in hos_alloc: e["title"] = "! " + e["title"]
    return sorted(out, key=lambda e: (not e.get("allday"), e.get("start", "")))

def ev_line(e):
    t = "all day" if e.get("allday") else f'{e["start"]}–{e["endt"]}'
    loc = f'<span class="loc">{html.escape(e["loc"])}</span>' if e.get("loc") else ""
    return f'<div class="ev {e["cal"]}"><span class="t">{t}</span>{mark(e)}<span>{html.escape(e["title"])}{loc}</span></div>'

def agenda():
    body = ""
    for i in range(7):
        d = TODAY + dt.timedelta(days=i)
        evs = events_on(d)
        lbl = "Today" if i == 0 else "Tomorrow" if i == 1 else d.strftime("%A")
        body += f'<div class="day {"today" if i==0 else ""}"><h2>{lbl}<span>{d.strftime("%-d %b")}</span></h2>'
        body += "".join(ev_line(e) for e in evs) or '<div class="empty">nothing scheduled</div>'
        body += "</div>"
    return f'<div class="hdr"><h1>This week</h1><span class="sub">{TODAY.strftime("%a %-d %b %Y")} · updated 07:30</span></div>{body}{legend()}'

def daily():
    evs = events_on(TODAY)
    allday = "".join(f'<span class="ev {e["cal"]}">{mark(e)}{html.escape(e["title"])}</span>' for e in evs if e.get("allday"))
    H0, H1 = 7, 21; px = 1840 / (H1 - H0)
    hrs = "".join(f'<div class="hr" style="top:{(h-H0)*px}px">{h:02d}:00</div>' for h in range(H0, H1))
    now = 10.4; hrs += f'<div class="hr now" style="top:{(now-H0)*px}px"></div>'
    blks = ""
    for e in evs:
        if e.get("allday"): continue
        s = int(e["start"][:2]) + int(e["start"][3:]) / 60; en = int(e["endt"][:2]) + int(e["endt"][3:]) / 60
        blks += f'<div class="blk {e["cal"]}" style="top:{(s-H0)*px+2}px;height:{(en-s)*px-6}px"><b>{e["start"]}</b> {html.escape(e["title"])}<div class="loc">{html.escape(e.get("loc",""))}</div></div>'
    return (f'<div class="hdr"><h1>{TODAY.strftime("%A %-d %B")}</h1><span class="sub">updated 10:24</span></div>'
            f'<div class="allday">{allday}</div><div class="grid">{hrs}{blks}</div>{legend()}')

def month():
    y, m = TODAY.year, TODAY.month
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
    rows = ""
    for w in weeks:
        rows += f'<tr style="height:{int(1940/len(weeks))}px">'
        for d in w:
            cls = ("today" if d == TODAY else "") + (" other" if d.month != m else "")
            evs = events_on(d)
            lines = "".join(f'<div class="e {e["cal"]}">{mark(e)}{"" if e.get("allday") else e["start"]+" "}{html.escape(e["title"])}</div>' for e in evs[:7])
            rows += f'<td class="{cls}"><div class="n">{d.day}</div>{lines}</td>'
        rows += "</tr>"
    head = "".join(f"<th>{n}</th>" for n in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
    return (f'<div class="hdr"><h1>{TODAY.strftime("%B %Y")}</h1><span class="sub">updated 07:30</span></div>'
            f'<table><tr>{head}</tr>{rows}</table>{legend()}')


TFC = dict(paying=22, trial_live=6, trial_lapsed=30, active_1d=8, active_7d=22, signups_7d=1,
           flags=9, requests=0, exam=dt.date(2026, 11, 5), exam_n=7, series=[7,11,8,10,9,9,9,8,14,13,7,6,6,6],
           ending=[("haz", "10 Nov"), ("Chengus", "12 Nov")],
           actions=None)
LOGO = (HERE / "tfc-logo.svg").read_text()
CSS_TFC = """
.col{display:flex;flex-direction:column;height:2220px}
.col .grow{flex:1}
.tile .v{font-size:150px}
.brand{display:flex;align-items:center;gap:26px}
.brand svg{width:96px;height:96px}
.brand .w{font-size:46px;font-weight:700;letter-spacing:6px}
.tiles{display:grid;grid-template-columns:1fr 1fr 1fr;gap:28px;margin-top:28px}
.tile{border:5px solid #000;padding:36px 30px 30px}
.tile .v{font-size:130px;font-weight:700;line-height:1;letter-spacing:-3px}
.tile .l{font-size:36px;color:#222;margin-top:16px}
.tile .s{font-size:28px;color:#666;margin-top:6px}
.tile.warn{background:repeating-linear-gradient(45deg,#fff 0 10px,#eee 10px 20px)}
.hero{border:6px solid #000;background:#000;color:#fff;padding:36px 48px;display:flex;justify-content:space-between;align-items:center;margin-top:28px}
.hero .v{font-size:190px;font-weight:700;line-height:1;letter-spacing:-5px}
.hero .l{font-size:42px;text-align:right;line-height:1.3}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:28px}
.box{border:5px solid #000;padding:26px 30px}
.box .l{font-size:34px;font-weight:700;margin-bottom:14px}
.bars{display:flex;align-items:flex-end;gap:12px;height:340px}
.bars div{flex:1;background:#000}
.x{font-size:26px;color:#666;display:flex;justify-content:space-between;margin-top:8px}
.li{font-size:34px;line-height:1.5;display:flex;gap:16px}
.li .cb{width:34px;height:34px;border:4px solid #000;flex:none;margin-top:12px}
.li .due{margin-left:auto;color:#666;white-space:nowrap;padding-left:20px}
"""
def tfc():
    TFC["actions"] = dict(load_pri()).get("TFC", [])
    days = (TFC["exam"] - TOday()).days
    mx = max(TFC["series"])
    bars = "".join(f'<div style="height:{v/mx*100}%"></div>' for v in TFC["series"])
    T = lambda v, l, s="", cls="": f'<div class="tile {cls}"><div class="v">{v}</div><div class="l">{l}</div><div class="s">{s}</div></div>'
    acts = "".join(f'<div class="li"><span class="cb"></span><span>{a}</span><span class="due">{d}</span></div>' for a, d in TFC["actions"])
    ends = "".join(f'<div class="li"><span>{n}</span><span class="due">{d}</span></div>' for n, d in TFC["ending"])
    return ('<div class="col">' + f'<div class="hdr"><div class="brand">{LOGO}<span class="w">THE FINAL COUNTDOWN</span></div><span class="sub">updated 07:30</span></div>'
        f'<div class="hero"><div class="v">{days}</div><div class="l">days to FANZCA written<br>{TFC["exam"].strftime("%a %-d %b")} · {TFC["exam_n"]} candidates</div></div>'
        '<div class="tiles">'
        + T(TFC["paying"], "paying", "subscriptions active")
        + T(TFC["trial_live"], "live trials", f'{TFC["trial_lapsed"]} lapsed, never converted')
        + T(TFC["signups_7d"], "signups", "last 7 days")
        + T(f'{TFC["active_1d"]}<span style="font-size:64px;color:#666"> / {TFC["active_7d"]}</span>', "active users", "today / 7 days")
        + T(TFC["flags"], "open SAQ flags", "user-reported errors", "warn" if TFC["flags"] else "")
        + T(TFC["requests"], "feature requests", "open")
        + '</div>'
        f'<div class="row2"><div class="box"><div class="l">Daily active users, 14 days</div><div class="bars">{bars}</div>'
        f'<div class="x"><span>{(TOday()-dt.timedelta(13)).strftime("%-d %b")}</span><span>today</span></div></div>'
        f'<div class="box"><div class="l">Trials ending this fortnight</div>{ends}</div></div>'
        f'<div class="box grow" style="margin-top:28px"><div class="l">Pricing to-do</div>{acts}</div></div>')
def TOday(): return dt.date.today()

def load_pri():
    secs, cur = [], None
    for line in (HERE.parent / "priorities.md").read_text().splitlines():
        if line.startswith("## "):
            cur = (line[3:].strip(), []); secs.append(cur)
        elif line.startswith("- [ ] ") and cur:
            t, _, due = line[6:].partition("|"); cur[1].append((t.strip(), due.strip()))
    return secs
PRI = load_pri()
CSS_PRI = """
.sec{margin-top:30px}
.sec h2{font-size:44px;font-weight:700;border-bottom:4px solid #000;padding-bottom:8px;margin-bottom:12px}
.sec.dec h2{border-bottom-style:dashed;color:#444}
.pi{font-size:36px;line-height:1.45;display:flex;gap:18px;padding:8px 0}
.pi .cb{width:36px;height:36px;border:4px solid #000;flex:none;margin-top:12px}
.sec.dec .pi .cb{border-radius:50%}
.pi .due{margin-left:auto;color:#666;white-space:nowrap;padding-left:20px}
"""
def priorities():
    body = ""
    for title, items in PRI:
        if title == "TFC": continue
        cls = "dec" if title.startswith("Decisions") else ""
        body += f'<div class="sec {cls}"><h2>{title}</h2>' + "".join(
            f'<div class="pi"><span class="cb"></span><span>{html.escape(t)}</span><span class="due">{d}</span></div>' for t, d in items) + "</div>"
    return f'<div class="hdr"><h1>Priorities</h1><span class="sub">from handoffs 23-31 Oct · updated 07:30</span></div>{body}'

def nav(cur):
    return '<div class="nav">' + "".join(f'<div class="{"on" if n==cur else ""}">{n}</div>' for n in ["Agenda","TFC","Priorities","Kindle"]) + '</div>'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1860, "height": 2480})
        for name, fn in [("agenda", agenda), ("daily", daily), ("month", month), ("tfc", tfc), ("priorities", priorities)]:
            cur = {"agenda":"Agenda","daily":"Agenda","month":"Agenda","tfc":"TFC","priorities":"Priorities"}[name]
            doc = f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}{CSS_TFC}{CSS_PRI}</style></head><body>{fn()}{nav(cur)}</body></html>"
            (HERE / f"{name}.html").write_text(doc)
            await pg.set_content(doc); await pg.screenshot(path=str(HERE / f"{name}.png"))
            im = Image.open(HERE / f"{name}.png").convert("L").quantize(16).convert("L")
            im.save(HERE / f"{name}.png", optimize=True); print(name, "ok")
        await b.close()
asyncio.run(main())
