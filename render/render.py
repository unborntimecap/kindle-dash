"""Kindle dashboard renderer: live sources -> HTML -> 1860x2480 16-grey PNGs in render/out/."""
import json, re, datetime as dt, calendar, html, asyncio
from zoneinfo import ZoneInfo
NOW = dt.datetime.now(ZoneInfo("Australia/Sydney")).strftime("%a %-d %b %H:%M")
from pathlib import Path
from playwright.async_api import async_playwright
from PIL import Image

import sources
HERE = Path(__file__).parent
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
TODAY = dt.datetime.now(ZoneInfo("Australia/Sydney")).date()
EV = sources.events()
if not EV:
    print("[warn] no calendar data at all; using mock events.json")
    EV = json.loads((HERE.parent / "mock" / "events.json").read_text())
for e in EV:
    e["d"] = dt.date.fromisoformat(e["date"])
HIDE = sources.hide_list()

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1860px;height:2480px;background:#fff;color:#000;font-family:'DejaVu Sans',Helvetica,Arial,sans-serif;padding:60px 70px;overflow:hidden}
h1{font-size:64px;font-weight:700;letter-spacing:-1px}
.hdr{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:6px solid #000;padding-bottom:18px;margin-bottom:30px}
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
.btns{display:flex;gap:18px}
.btn{border:5px solid #000;padding:14px 30px;font-size:36px;font-weight:700;min-width:300px;text-align:center}
.hdr .right{display:flex;flex-direction:column;align-items:flex-end;justify-content:flex-end;height:140px}
.body{height:2000px;overflow:hidden}
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
table{width:100%;height:1820px;border-collapse:collapse;table-layout:fixed}
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
    out = [e for e in out if not any(h in e["title"].lower() for h in HIDE)]
    if merge:
        # HosPortal on-call duplicates an Adhoc "O/C" entry for the same hospital that day
        def hosp(t):
            t = t.upper()
            return "POW" if "POW" in t or "PRINCE OF WALES" in t else "RPA" if "RPA" in t or "PRINCE ALFRED" in t else None
        oc = {hosp(e["title"]) for e in out if e["cal"] == "adhoc" and "O/C" in e["title"].upper()}
        out = [e for e in out if not (e["cal"] == "hos" and e["title"].startswith("Call") and hosp(e["title"]) in oc)]
        hos_alloc = [e for e in out if e["cal"] == "hos" and not e.get("allday")]
        hos_hosps = {hosp(e["title"]) for e in hos_alloc}
        # "own" entries: Regular work, or an all-day Adhoc entry naming the same hospital as a HosPortal allocation
        work = [e for e in out if e["cal"] == "work" or (e["cal"] == "adhoc" and e.get("allday")
                and "O/C" not in e["title"].upper() and hosp(e["title"]) in hos_hosps)]
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
    l = e.get("loc") or ""
    l = l if len(l) <= 28 else l[:27] + "…"
    loc = f'<span class="loc">{html.escape(l)}</span>' if l else ""
    return f'<div class="ev {e["cal"]}"><span class="t">{t}</span>{mark(e)}<span>{html.escape(e["title"])}{loc}</span></div>'

def hdr(title, sub, b1, b2):
    return (f'<div class="hdr"><h1>{title}</h1><div class="right"><div class="btns"><span class="btn">{b1}</span><span class="btn">{b2}</span></div>'
            f'<span class="sub">{sub} · rendered {NOW}</span></div></div>')

def agenda(week=0):
    body = ""
    start = TODAY + dt.timedelta(days=7*week)
    for i in range(7):
        d = start + dt.timedelta(days=i)
        evs = events_on(d)
        lbl = ("Today" if i == 0 else "Tomorrow" if i == 1 else d.strftime("%A")) if week == 0 else d.strftime("%A")
        body += f'<div class="day {"today" if d==TODAY else ""}"><h2>{lbl}<span>{d.strftime("%-d %b")}</span></h2>'
        body += "".join(ev_line(e) for e in evs) or '<div class="empty">nothing scheduled</div>'
        body += "</div>"
    title = "This week" if week == 0 else "Next week"
    sub = f'{start.strftime("%a %-d %b")} to {(start+dt.timedelta(6)).strftime("%a %-d %b")}'
    return hdr(title, sub, "Month", "Next week &rsaquo;" if week == 0 else "&lsaquo; This week") + f'<div class="body">{body}</div>' + legend()
def agenda_next(): return agenda(1)

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
    return (f'<div class="hdr"><h1>{TODAY.strftime("%A %-d %B")}</h1><span class="sub">rendered {NOW}</span></div>'
            f'<div class="allday">{allday}</div><div class="grid">{hrs}{blks}</div>{legend()}')

def month(off=0):
    y, m = TODAY.year, TODAY.month + off
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
    rows = ""
    for w in weeks:
        rows += f'<tr style="height:{int(1820/len(weeks))}px">'
        for d in w:
            cls = ("today" if d == TODAY else "") + (" other" if d.month != m else "")
            evs = events_on(d)
            lines = "".join(f'<div class="e {e["cal"]}">{mark(e)}{"" if e.get("allday") else e["start"]+" "}{html.escape(e["title"])}</div>' for e in evs[:7])
            rows += f'<td class="{cls}"><div class="n">{d.day}</div>{lines}</td>'
        rows += "</tr>"
    head = "".join(f"<th>{n}</th>" for n in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
    title = dt.date(y, m, 1).strftime("%B %Y")
    return hdr(title, "", "Week", "Next month &rsaquo;" if off == 0 else "&lsaquo; This month") + f'<table><tr>{head}</tr>{rows}</table>' + legend()
def month_next(): return month(1)

TFC = sources.tfc() or dict(paying="?", trial_live="?", trial_lapsed="?", active_1d="?", active_7d="?", signups_7d="?",
                            flags=0, requests=0, conv_n=0, conv_d=0, exam=None, exam_n=0, series=[0]*14, ending=[])
LOGO = (HERE.parent / "mock" / "tfc-logo.svg").read_text()
CSS_TFC = """
.col{display:flex;flex-direction:column;height:2220px}
.col .grow{flex:1;overflow:hidden}
.tile .v{font-size:150px}
.brand{display:flex;align-items:center;gap:26px}
.brand svg{width:72px;height:72px}
.brand .w{font-size:40px;font-weight:700;letter-spacing:5px;line-height:1}
.tiles{display:grid;grid-template-columns:1fr 1fr 1fr;gap:28px;margin-top:28px}
.tiles.kpi{grid-template-columns:1fr 1fr 1fr 1fr}
.tiles.kpi .tile{padding:22px 26px 20px}
.tiles.kpi .tile .v{font-size:96px}
.tiles.kpi .tile .l{font-size:30px;margin-top:10px}
.li.dim,.li.dim .due{color:#999}
.li .due.n{font-weight:700;color:#000;font-variant-numeric:tabular-nums}
.li .cb.on{background:#000}
.tile{border:5px solid #000;padding:36px 30px 30px}
.tile .v{font-size:130px;font-weight:700;line-height:1;letter-spacing:-3px}
.tile .l{font-size:36px;color:#222;margin-top:16px}
.tile .s{font-size:28px;color:#666;margin-top:6px}
.tile.warn{background:repeating-linear-gradient(45deg,#fff 0 10px,#eee 10px 20px)}
.hero{border:6px solid #000;background:#000;color:#fff;padding:36px 48px;display:flex;justify-content:space-between;align-items:center;margin-top:28px}
.hero .v{font-size:190px;font-weight:700;line-height:1;letter-spacing:-5px}
.hero .l{font-size:42px;text-align:right;line-height:1.3}
.hero.slim{padding:18px 48px;justify-content:flex-start}
.hero.slim .l{font-size:40px;text-align:left}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:28px}
.box{border:5px solid #000;padding:26px 30px}
.box .l{font-size:34px;font-weight:700;margin-bottom:14px}
.bars{display:flex;align-items:flex-end;gap:12px;height:300px}
.bars .c{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%}
.bars .n{font-size:24px;color:#444;text-align:center;line-height:1;margin-bottom:4px}
.bars .b{background:#000}
.box .l span{float:right;font-weight:400;color:#666}
.x{font-size:26px;color:#666;display:flex;justify-content:space-between;margin-top:8px}
.gate{font-size:26px;color:#666;margin-bottom:6px}
.now{font-size:44px;font-weight:700;line-height:1.25;margin-bottom:10px}
.why{font-size:32px;color:#333;line-height:1.4;margin-bottom:8px}
.li{font-size:34px;line-height:1.5;display:flex;gap:16px}
.now+.li,.why+.li{margin-top:16px}
.li .cb{width:34px;height:34px;border:4px solid #000;flex:none;margin-top:12px}
.li .due{margin-left:auto;color:#666;white-space:nowrap;padding-left:20px}
"""
def tfc():
    TFC["actions"] = dict(PRI).get("TFC") or dict(sources.repo_priorities()).get("TFC", [])
    days = (TFC["exam"] - TODAY).days if TFC["exam"] else "–"
    exam_txt = f'{TFC["exam"].strftime("%a %-d %b")} · {TFC["exam_n"]} candidates' if TFC["exam"] else "no sitting scheduled"
    mx = max(TFC["series"]) or 1
    bars = "".join(f'<div class="c"><div class="n">{v}</div><div class="b" style="height:{round(v/mx*260)}px"></div></div>' for v in TFC["series"])
    T = lambda v, l, s="", cls="": f'<div class="tile {cls}"><div class="v">{v}</div><div class="l">{l}</div><div class="s">{s}</div></div>'
    acts = "".join(f'<div class="li"><span class="cb"></span><span>{a}</span><span class="due">{d}</span></div>' for a, d in TFC["actions"])
    NW = sources.tfc_now()
    if NW:
        now = (f'<div class="gate">{NW["gate"]}</div>' if NW["gate"] else "") + f'<div class="now">{NW["headline"]}</div>' \
            + (f'<div class="why"><b>Do first:</b> {NW["do_first"]}</div>' if NW["do_first"] else "") \
            + (f'<div class="why" style="margin-top:14px"><b>Finish now</b></div>' + "".join(f'<div class="li"><span class="cb"></span><span>{x}</span></div>' for x in NW["finish"][:4]) if NW["finish"] else "")
        acts = ""  # the vault TFC block stays on the Priorities page
    else:
        now = '<div class="why">CLAUDE.md unparsed; showing vault TFC block</div>'
    # one live-trial row per person; filled box = reached Stripe checkout (the ones worth chasing)
    ends = "".join(f'<div class="li"><span class="cb{" on" if c else ""}"></span><span>{html.escape(n)}</span><span class="due">{d}</span></div>' for n, d, c in TFC["ending"]) or '<div class="li dim">none</div>'
    # ANZCA sitting (YYYY.1 / YYYY.2) with its written date; greyed once the written has passed
    sitting = "".join(f'<div class="li{" dim" if s.get("passed") or s["label"] == "no date" else ""}"><span>{s["label"]}'
                      + (f'<span style="color:#666"> · written {s["written"]}</span>' if s.get("written") else "")
                      + f'</span><span class="due n">{s["n"]}</span></div>' for s in TFC.get("by_sitting", []))
    conv = f'{round(100*TFC["conv_n"]/TFC["conv_d"])}%' if TFC.get("conv_d") else "–"
    return ('<div class="col">' + f'<div class="hdr"><div class="brand">{LOGO}<span class="w">THE FINAL COUNTDOWN</span></div><div class="right"><div class="btns" style="visibility:hidden"><span class="btn">x</span></div><span class="sub">rendered {NOW}</span></div></div>'
        + (f'<div class="hero"><div class="v">{days}</div><div class="l">days to FANZCA written<br>{exam_txt}</div></div>' if TFC["exam"] and days <= 30
           else f'<div class="hero slim"><span class="l"><b>{days}</b> days to FANZCA written · {exam_txt}</span></div>')
        +
        '<div class="tiles kpi">'
        + T(TFC["paying"], "paying")
        + T(f'{TFC["active_1d"]}<span style="font-size:48px;color:#666"> / {TFC["active_7d"]}</span>', "active today / 7d")
        + T(TFC["signups_7d"], "signups, 7 days")
        + T(conv, "trial conversion", f'{TFC.get("conv_n",0)} of {TFC.get("conv_d",0)}, 30 d')
        + '</div>'
        f'<div class="row2"><div class="box"><div class="l">Paying by sitting<span>{TFC["paying"]}</span></div>{sitting}</div>'
        f'<div class="box"><div class="l">On trial<span>{TFC["trial_live"]} live · {TFC["trial_lapsed"]} lapsed</span></div>{ends}<div class="x" style="justify-content:flex-start;gap:12px;margin-top:12px"><span class="cb on" style="display:inline-block;width:24px;height:24px;border:3px solid #000;background:#000"></span>started checkout</div></div></div>'
        f'<div class="box" style="margin-top:28px"><div class="l">Daily active users, 14 days<span>peak {mx}</span></div><div class="bars">{bars}</div>'
        f'<div class="x"><span>{(TODAY-dt.timedelta(13)).strftime("%-d %b")}</span><span>today</span></div></div>'
        f'<div class="box grow" style="margin-top:28px"><div class="l">Now</div>{now}{acts}</div></div>')


KIDS = json.loads((HERE.parent / "kids.json").read_text())
CSS_KIDS = """
.kg{display:grid;grid-template-columns:150px repeat(7,1fr);border-top:5px solid #000;border-left:3px solid #bbb}
.kg>div{border-right:3px solid #bbb;border-bottom:3px solid #bbb;padding:12px;display:flex;flex-direction:column;gap:12px;min-height:330px}
.kg .kh{min-height:0;font-size:36px;font-weight:700;text-align:center;border-bottom:5px solid #000}
.kg .kb{font-size:32px;font-weight:700;color:#444;justify-content:center}
.ka{border:4px solid #000;padding:10px 12px;font-size:30px;line-height:1.2}
.ka.maybe{border-style:dashed;color:#555}
.ka .who{display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap}
.ka .k{width:44px;height:44px;border-radius:50%;background:#000;color:#fff;font-size:28px;font-weight:700;display:flex;align-items:center;justify-content:center}
.ka .t{font-size:24px;color:#555;letter-spacing:1px}
.kt{display:flex;gap:28px;margin-top:30px}
.kt .tile{flex:1;padding:24px 28px}
.kt .tile .v{font-size:96px}
.kc{border:5px solid #000;padding:20px 28px;margin-top:30px;columns:2;column-gap:60px}
.kc .r{display:flex;font-size:30px;line-height:1.5;break-inside:avoid}
.kc .r span:last-child{margin-left:auto;font-variant-numeric:tabular-nums}
.kc .tot{font-weight:700;border-top:4px solid #000;margin-top:6px}
"""
def kids(who=None):
    acts = [a for a in KIDS["acts"] if who is None or who in a["kids"]]
    g = '<div class="kh"></div>' + "".join(f'<div class="kh">{d}</div>' for d in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"])
    for b, band in enumerate(["Morning", "Lunch", "After school"]):
        g += f'<div class="kb">{band}</div>'
        for d in range(7):
            g += "<div>" + "".join(
                f'<div class="ka{" maybe" if a.get("maybe") else ""}">{html.escape(a["n"])}<div class="who">'
                + "".join(f'<span class="k">{k}</span>' for k in a["kids"] if who is None or k == who)
                + ('<span class="t">LIFT</span>' if a.get("lift") else "") + ('<span class="t">MAYBE</span>' if a.get("maybe") else "")
                + "</div></div>" for a in acts if a["day"] == d and a["band"] == b) + "</div>"
    tiles = ""
    for k, name in KIDS["kids"].items():
        if who and k != who: continue
        firm = [a for a in KIDS["acts"] if k in a["kids"] and not a.get("maybe")]
        tiles += (f'<div class="tile"><div class="v">{len(firm)}</div><div class="l">{name}: sessions</div>'
                  f'<div class="s">{sum(1 for a in firm if a.get("lift"))} lifts · {sum(1 for a in KIDS["acts"] if k in a["kids"] and a.get("maybe"))} maybe</div></div>')
    # term budget: cost per child per term x number of kids in it; unknown prices shown as "?"
    rows, tot, unk = "", 0, 0
    seen = {}
    for a in acts:
        ks = [k for k in a["kids"] if who is None or k == who]
        key = (a["n"], "".join(ks))
        if key in seen: continue
        seen[key] = 1
        c = a.get("term")
        if c is None: unk += 1; val = "?"
        else: tot += c * len(ks); val = f"${c*len(ks):,}"
        rows += f'<div class="r"><span>{html.escape(a["n"])} ({"".join(ks)})</span><span>{val}</span></div>'
    rows += f'<div class="r tot"><span>Per term{f" + {unk} unpriced" if unk else ""}</span><span>${tot:,}</span></div>'
    order = [None] + list(KIDS["kids"])
    nxt = order[(order.index(who) + 1) % len(order)]
    label = "All" if who is None else KIDS["kids"][who]
    return (hdr("Kids week", "L Leah · H Harper · E Elijah", f"Showing: {label}", f'{"All" if nxt is None else KIDS["kids"][nxt]} &rsaquo;')
            + f'<div class="kg">{g}</div><div class="kt">{tiles}</div><div class="kc"><div class="r tot" style="border:0;margin:0"><span>Term budget</span></div>{rows}</div>')

PRI = sources.priorities()
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
    return f'<div class="hdr"><h1>Priorities</h1><div class="right"><div class="btns" style="visibility:hidden"><span class="btn">x</span></div><span class="sub">rendered {NOW}</span></div></div><div class="body">{body}</div>'

def nav(cur):
    return '<div class="nav">' + "".join(f'<div class="{"on" if n==cur else ""}">{n}</div>' for n in ["Agenda","TFC","Priorities","Kids","Kindle"]) + '</div>'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1860, "height": 2480})
        for name, fn in [("agenda", agenda), ("agenda-next", agenda_next), ("month", month), ("month-next", month_next), ("tfc", tfc), ("priorities", priorities), ("kids", kids)] + [(f"kids-{k.lower()}", (lambda k=k: kids(k))) for k in KIDS["kids"]]:
            cur = {"agenda":"Agenda","agenda-next":"Agenda","daily":"Agenda","month":"Agenda","month-next":"Agenda","tfc":"TFC","priorities":"Priorities"}.get(name, "Kids")
            doc = f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}{CSS_TFC}{CSS_PRI}{CSS_KIDS}</style></head><body>{fn()}{nav(cur)}</body></html>"
            
            await pg.set_content(doc); await pg.screenshot(path=str(OUT / f"{name}.png"))
            im = Image.open(OUT / f"{name}.png").convert("L").quantize(16).convert("L")
            im.save(OUT / f"{name}.png", optimize=True); print(name, "ok")
        await b.close()
asyncio.run(main())
