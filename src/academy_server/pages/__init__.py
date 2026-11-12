"""Server-rendered HTML pages, all styled by /static/academy.css.

The home page, the styled 401 page (served before any session exists), the /design
style guide, the lab page where a step is run, the flash cards, and /meridian: the data
the mock Meridian API serves.

Every dynamic value goes through html.escape. Lesson markdown is rendered with raw HTML
disabled, so step.md can't inject markup either.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .. import __version__, paths

HERE = Path(__file__).resolve().parent
THEMES = ("light", "dark")

# Runs in <head> before first paint: a stored choice wins over the OS setting,
# but never over a server-stamped data-theme (e.g. ?theme=dark for screenshots).
_THEME_BOOT = ("(function(){try{var d=document.documentElement,t=localStorage.getItem('academy-theme');"
               "if((t==='light'||t==='dark')&&!d.hasAttribute('data-theme'))d.setAttribute('data-theme',t)}"
               "catch(e){}})();")
# Cycles system -> light -> dark and remembers the choice.
_THEME_TOGGLE = """(function(){
  var d=document.documentElement,b=document.getElementById('theme-toggle'),k='academy-theme';
  if(!b)return;
  function show(){var t=d.getAttribute('data-theme')||'system';b.textContent='Theme: '+t;}
  show();
  b.addEventListener('click',function(){
    var o=['system','light','dark'],t=d.getAttribute('data-theme')||'system',n=o[(o.indexOf(t)+1)%3];
    try{if(n==='system'){d.removeAttribute('data-theme');localStorage.removeItem(k);}
        else{d.setAttribute('data-theme',n);localStorage.setItem(k,n);}}catch(e){d.setAttribute('data-theme',n);}
    show();
  });
})();"""

_STATUS_LABEL = {"not_started": "Not started", "in_progress": "In progress", "completed": "Completed"}

# The lab's model picker: what the gateway key offers, and what each model accepts.
LAB_MODELS = {
    "claude-opus-5-5": "Opus 5.5: thinking is always on; output_config.effort takes low to max (default medium).",
    "claude-sonnet-5-5": "Sonnet 5.5: thinking is on by default; output_config.effort takes low to max (default high). Half the price of Opus 5.5.",
    "claude-haiku-4-5": "Haiku 4.5 is the previous generation. It rejects output_config.effort with a 400, and it thinks only with thinking={\"type\": \"enabled\", \"budget_tokens\": N}. Code written for Opus 5.5 needs changes to run on it.",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def theme_or_none(value: str | None) -> str | None:
    return value if value in THEMES else None


def markdown(text: str) -> str:
    """Lesson markdown (CommonMark plus tables) to HTML. Raw HTML in the source is escaped."""
    from markdown_it import MarkdownIt   # only the lab page needs it
    return MarkdownIt("commonmark", {"html": False}).enable("table").render(text)


def status_pill(status: str) -> str:
    key = status if status in _STATUS_LABEL else "not_started"
    return f'<span class="pill pill-{key}">{_STATUS_LABEL[key]}</span>'


def shell(title: str, body: str, *, theme: str | None = None, active: str | None = None,
          nav: bool = True) -> str:
    theme_attr = f' data-theme="{theme}"' if theme in THEMES else ""
    links = ""
    if nav:
        items = [("home", "/", "Home"), ("cards", "/cards", "Flash cards"), ("meridian", "/meridian", "Meridian data"),
                 ("design", "/design", "Design system")]
        current = ' aria-current="page"'
        links = '<nav class="nav" aria-label="Main">' + "".join(
            f'<a href="{href}"{current if key == active else ""}>{label}</a>'
            for key, href, label in items) + "</nav>"
    return f"""<!doctype html>
<html lang="en"{theme_attr}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<link rel="stylesheet" href="/static/academy.css">
<script>{_THEME_BOOT}</script>
</head>
<body>
<header class="topbar"><div class="container topbar-inner">
  <a class="brand" href="/"><span class="brand-mark" aria-hidden="true">F</span>FDE Academy</a>
  {links}
  <span class="spacer"></span>
  <button class="btn btn-ghost btn-sm" id="theme-toggle" type="button" aria-label="Change color theme">Theme: system</button>
</div></header>
<main>
{body}
</main>
<footer class="footer"><div class="container row">
  <span>FDE Academy v{esc(__version__)}</span><span class="spacer"></span>
  <span>Runs locally on 127.0.0.1.</span>
</div></footer>
<script>{_THEME_TOGGLE}</script>
</body>
</html>"""


# --------------------------------------------------------------------- home
def home_page(tree: Any, store: Any, *, theme: str | None = None) -> str:
    """Placeholder home: what the server, store and lesson loader know."""
    step_status = store.step_status()
    st = store.status()
    pos = st["position"]
    ordered = tree.ordered_step_ids()
    resume_id = pos["step_id"] if pos and pos["step_id"] in tree.steps else (ordered[0] if ordered else None)
    opened = sum(sum(c.values()) for c in st["modules"].values())

    if resume_id:
        step = tree.steps[resume_id]
        continue_card = f"""
      <div class="card card-pad stack">
        <p class="eyebrow">{"Continue where you left off" if pos else "Start here"}</p>
        <h2 style="margin:0">{esc(step.spec.title)}</h2>
        <div class="row"><code>{esc(resume_id)}</code>{status_pill(step_status.get(resume_id, "not_started"))}</div>
        <div class="row" style="margin-top:var(--sp-2)">
          <a class="btn btn-primary" href="/lab/{esc(resume_id)}">Open the lab</a>
          <a class="btn" href="/design">See the design system</a>
        </div>
        <p class="small muted" style="margin:0">The lab runs your code from the browser, shows the console and
        every model call, grades your predictions against the run, and has a tutor on every step.</p>
      </div>"""
    else:
        continue_card = """
      <div class="card card-pad"><p class="eyebrow">No lessons yet</p>
      <p>No lesson steps were found under <code>content/</code>.</p></div>"""

    pr = st["predictions"]
    accuracy = f"{pr['right'] / pr['graded']:.0%}" if pr["graded"] else "–"
    tiles = "".join(f"""
        <div class="stat"><div class="stat-label">{label}</div><div class="stat-value">{value}</div>
        <div class="stat-sub">{sub}</div></div>""" for label, value, sub in [
        ("Predictions right", accuracy, f"{pr['right']:,} of {pr['graded']:,} graded"),
        ("Surprises explained", f"{pr['explained']:,}", f"of {pr['surprises']:,} wrong predictions"),
        ("Mistakes cleared", f"{st['quiz']['fixed_after_retry']:,}", f"{st['quiz']['still_wrong']:,} quiz items still wrong"),
        ("Spend today", f"${st['spend']['today_usd']:.4f}", f"${st['spend']['total_usd']:.4f} total"),
    ])
    review = review_card(tree, store)

    modules = []
    for m in tree.outline(step_status):
        chapters = []
        for c in m["chapters"]:
            rows = "".join(f"""
              <tr><td><a href="/lab/{esc(s['id'])}">{esc(s['title'])}</a></td>
                  <td><code>{esc(s['id'])}</code></td><td>{status_pill(s['status'])}</td></tr>"""
                           for s in c["steps"])
            chapters.append(f"""
            <h3 style="margin-top:var(--sp-4)">{esc(c['title'])}</h3>
            <table class="table"><thead><tr><th>Step</th><th>Id</th><th>Status</th></tr></thead>
            <tbody>{rows}</tbody></table>""")
        elective = ' <span class="pill pill-plain">Elective</span>' if m.get("elective") else ""
        modules.append(f"""
        <article class="card">
          <div class="card-head"><span class="pill pill-plain pill-mono">{esc(m['id'])}</span>
            <h3 class="card-title">{esc(m['title'])}</h3>{elective}</div>
          <div class="card-body"><p class="secondary">{esc(m.get('summary') or '')}</p>{''.join(chapters)}</div>
        </article>""")

    if tree.errors:
        items = "".join(f"<li><code>{esc(e)}</code></li>" for e in tree.errors)
        errors = f"""<div class="callout callout-critical" style="margin-top:var(--sp-5)">
          <span class="icon icon-alert" aria-hidden="true"></span>
          <div><p><b>{len(tree.errors)} content error(s)</b>: these lessons didn't load.</p><ul>{items}</ul></div></div>"""
    else:
        errors = (f'<p class="small muted" style="margin-top:var(--sp-4)">Content: {len(tree.steps):,} step(s) in '
                  f'{len(tree.modules):,} module(s), no load errors.</p>')

    body = f"""
<section class="container page-head">
  <p class="eyebrow">A learning lab · GenAI and agent engineering</p>
  <h1>Learn agent engineering by watching it run.</h1>
  <p class="lede">Every lesson is a set of experiments: predict, change one thing, run it live, compare
  what the run measured with what you expected, then explain the gap.</p>
</section>
<section class="container stack-lg" style="padding-bottom:var(--sp-7)">
  <div class="grid-2">{continue_card}
    <div class="grid-tiles" style="align-content:start">{tiles}</div>
  </div>
  {review}
  <div>
    <h2>Course</h2>
    <div class="stack-lg">{''.join(modules) or '<p class="muted">No modules yet.</p>'}</div>
    {errors}
  </div>
  {START_OVER_ALL if tree.steps else ""}
</section>
<script>{_START_OVER_JS}</script>"""
    return shell("FDE Academy", body, theme=theme, active="home")


# "Start over": the lab page has one for its lesson, the home page one for every lesson. Both show
# what's cleared and what's kept before anything happens. Same markup and script on both pages.
START_OVER_KEEPS = ("Kept: your quiz history (spaced review still brings back your misses), your spend, "
                    "and your run history (every past run can still be reopened).")


def start_over_panel(scope: str, endpoint: str, button: str) -> str:
    return f"""
  <details class="start-over" data-endpoint="{esc(endpoint)}">
    <summary class="btn btn-sm btn-ghost btn-danger">{esc(button)}</summary>
    <div class="callout callout-warning stack" style="margin-top:var(--sp-2)">
      <div class="stack" style="gap:var(--sp-2)">
        <p class="small" style="margin:0"><b>Start {esc(scope)} over?</b> Your check and quiz answers, experiment
        predictions and explanations, latest run and tutor threads start empty, and every step loses its tick.
        Nothing is deleted.</p>
        <p class="small secondary" style="margin:0">{esc(START_OVER_KEEPS)}</p>
        <label class="small row" style="gap:var(--sp-2)"><input type="checkbox" class="start-over-code">
          Also put my code back to the starter</label>
        <div class="row"><button class="btn btn-sm btn-danger start-over-go" type="button">Start over</button>
          <span class="small muted start-over-msg"></span></div>
      </div>
    </div>
  </details>"""


START_OVER_ALL = f"""
  <div class="card card-pad stack">
    <p class="eyebrow">Start over</p>
    <p class="small secondary" style="margin:0">Do every lesson fresh, as if for the first time.</p>
    {start_over_panel("every lesson", "/api/start-over", "Start over all lessons")}
  </div>"""

# Clears the lab's remembered guide step, so a lesson opens on step 1 afterwards.
_START_OVER_JS = """(function(){
  document.querySelectorAll('details.start-over').forEach(function(box){
    var go=box.querySelector('.start-over-go'),msg=box.querySelector('.start-over-msg');
    go.addEventListener('click',function(){
      go.disabled=true;msg.textContent='Starting over…';
      fetch(box.dataset.endpoint,{method:'POST',headers:{'content-type':'application/json'},
            body:JSON.stringify({code:box.querySelector('.start-over-code').checked})})
        .then(function(r){return r.json().then(function(j){if(!r.ok)throw new Error(j.detail||('HTTP '+r.status));return j;});})
        .then(function(j){
          try{j.steps.forEach(function(id){localStorage.removeItem('academy-guide:'+id);});}catch(e){}
          if(box.dataset.endpoint!=='/api/start-over')history.replaceState(null,'',location.pathname+'#g1');
          location.reload();
        })
        .catch(function(e){go.disabled=false;msg.textContent='Could not start over: '+e.message;});
    });
  });
})();"""


REVIEW_SHOWN = 6   # per kind: quiz items, flash cards, wrong predictions


def review_card(tree: Any, store: Any) -> str:
    """Spaced review: quiz items still wrong, then wrong predictions, oldest first."""
    still = store.mistakes()["still_wrong"]
    cards = [m for m in still if m["item_id"].startswith("cards:")]    # flash cards get their own share
    quiz = [m for m in still if not m["item_id"].startswith("cards:")]
    surprises = store.surprises()
    items = []
    for m in quiz[:REVIEW_SHOWN] + cards[:REVIEW_SHOWN]:
        step = m["step_id"] if m["step_id"] in tree.steps else None
        parts = m["item_id"].split(":")      # <step>:<quiz id>, <step>:<guide step>:<check id>, cards:<deck>:<card>
        anchor = parts[1] if len(parts) == 3 else "quiz"
        card = parts[0] == "cards" and len(parts) == 3
        if card:
            link = f'<a class="btn btn-sm" href="/cards#{esc(parts[2])}">Review the flash card</a>'
        elif step:
            link = f'<a class="btn btn-sm" href="/lab/{esc(step)}#{esc(anchor)}">Retry in the lab</a>'
        else:
            link = '<span class="small muted">asked in chat; re-asked by /today</span>'
        kind = '<span class="pill pill-warning">Flash card</span>' if card else '<span class="pill pill-critical">Quiz</span>'
        question = m["question"] or m["item_id"]
        if card:
            question = question.replace("`", "")     # card fronts are markdown; this list is plain text
        items.append(f"""
          <li class="row" style="justify-content:space-between;gap:var(--sp-3)">
            <span>{kind} {esc(question)}
            <span class="small muted">· missed {m['misses']} of {m['tries']}</span></span>{link}</li>""")
    for sp in surprises[:REVIEW_SHOWN]:
        step = sp["step_id"] if sp["step_id"] in tree.steps else None
        exp = tree.steps[step].spec.experiment(sp["experiment_id"]) if step else None
        title = f"{sp['experiment_id'].upper()} {exp.title}" if exp else sp["experiment_id"].upper()
        link = f'<a class="btn btn-sm" href="/lab/{esc(step)}#{esc(sp['experiment_id'])}">Redo the card</a>' if step else ""
        explained = "" if sp["explained_at"] else ' <span class="pill pill-warning">not explained yet</span>'
        items.append(f"""
          <li class="row" style="justify-content:space-between;gap:var(--sp-3)">
            <span><span class="pill pill-accent">{esc(title)}</span> {esc(sp['prompt'] or sp['item_id'])}
            <span class="small muted">· the run measured {esc(sp['actual_display'] or '?')}</span>{explained}</span>
            {link}</li>""")
    hidden = sum(max(0, len(group) - REVIEW_SHOWN) for group in (quiz, cards, surprises))
    more = (f'<p class="small muted" style="margin:0">…and {hidden:,} more, oldest first. <code>/today</code> '
            f're-asks up to 3 each session.</p>' if hidden else "")
    body = (f'<ul class="stack" style="list-style:none;margin:0;padding:0">{"".join(items)}</ul>{more}' if items
            else '<p class="small muted" style="margin:0">Nothing to review: no missed quiz items, flash cards or '
                 'wrong predictions.</p>')
    return f"""
  <div class="card card-pad stack">
    <p class="eyebrow">Spaced review</p>
    <h2 style="margin:0">What to look at again</h2>
    <p class="small secondary" style="margin:0">Quiz items you got wrong, flash cards you didn't know, and
    predictions the run proved wrong (from each experiment's latest attempt). Right answers on a retry clear them.</p>
    {body}
  </div>"""


# ------------------------------------------------------------- unauthorized
def unauthorized_page(port: int, *, reason: str = "no_session") -> str:
    """Shown to a browser tab without this launch's session cookie (or with a stale launch link).

    Never includes the token. Uses only the open stylesheet, so it renders before sign-in.
    """
    if reason == "bad_token":
        title = "That launch link is from an earlier start"
        lead = ("Every start of the server makes a new private link. The one you opened belongs to a "
                "previous launch, so it no longer works.")
    else:
        title = "Open FDE Academy from its launch link"
        lead = ("This tab doesn't have this launch's session yet. FDE Academy only answers to the private "
                "link printed when the server starts, so no other website can drive it.")
    body = f"""
<section class="container-narrow page-head">
  <p class="eyebrow"><span class="pill pill-warning">Not signed in</span></p>
  <h1>{esc(title)}</h1>
  <p class="lede">{esc(lead)}</p>
</section>
<section class="container-narrow" style="padding-bottom:var(--sp-8)">
  <div class="card card-pad stack">
    <h3>Get back in</h3>
    <ol>
      <li>Find the terminal where you ran <code>python run.py</code>. It printed a line like
        <code>http://127.0.0.1:{int(port)}/auth?t=…</code>. Open that link.</li>
      <li>Or reopen it from any terminal in the repo:
        <pre style="margin-top:var(--sp-2)">.venv/Scripts/python -X utf8 tools/labctl.py open</pre></li>
      <li>Server not running? Start it with <code>python run.py</code>. Your progress is saved on disk,
        so nothing was lost.</li>
    </ol>
    <div class="callout"><span class="icon icon-info" aria-hidden="true"></span>
      <p class="small">Why the extra step: the server runs lesson code on your machine. The per-launch link,
      the Host check and the Origin check stop other web pages from reaching it.</p></div>
  </div>
</section>"""
    return shell("Sign in · FDE Academy", body, nav=False)


# ------------------------------------------------------------------- design
def lab_page(step: Any, code_path: Path, *, gateway: bool, theme: str | None = None) -> str:
    """The lab: the lesson, the editor, Run with its console and model calls, the experiment cards and the quiz."""
    note = "" if gateway else (
        '<div class="callout callout-warning" style="margin-top:var(--sp-3)"><span class="icon icon-alert" aria-hidden="true">'
        '</span><p class="small">No gateway credentials were found when the server started, so model calls will fail '
        'with 503. Add <code>ANTHROPIC_BASE_URL</code> and <code>ANTHROPIC_API_KEY</code> to '
        f'<code>{esc(paths.credentials_path())}</code> and restart <code>python run.py</code>.</p></div>')
    body = (HERE / "lab.html").read_text(encoding="utf-8")
    lesson = step.body_md
    if lesson.lstrip().startswith("# "):     # the page shows the title already
        lesson = lesson.lstrip().split("\n", 1)[1] if "\n" in lesson.lstrip() else ""
    for key, value in {"{{step_id_json}}": json.dumps(step.full_id), "{{step_id}}": esc(step.full_id),
                       "{{title}}": esc(step.spec.title), "{{code_path}}": esc(code_path),
                       "{{lesson_html}}": markdown(lesson) if lesson.strip() else "<p>No lesson text.</p>",
                       "{{gateway_note}}": note,
                       "{{start_over}}": start_over_panel("this lesson", f"/api/steps/{step.full_id}/start-over",
                                                          "Start this lesson over"),
                       "{{start_over_js}}": _START_OVER_JS,
                       "{{model_options}}": "".join(f"<option>{esc(m)}</option>" for m in LAB_MODELS),
                       "{{model_notes_json}}": json.dumps(LAB_MODELS),
                       "{{panels_json}}": json.dumps(step.spec.panels)}.items():
        body = body.replace(key, value)
    return shell(f"{step.spec.title} · FDE Academy", body, theme=theme)


def cards_page(*, theme: str | None = None) -> str:
    """Flash cards: what building FDE Academy taught. The cards load from /api/cards."""
    body = (HERE / "cards.html").read_text(encoding="utf-8")
    return shell("Flash cards · FDE Academy", body, theme=theme, active="cards")


# ----------------------------------------------------------------- meridian
def _table(head: list[str], rows: list[list[str]], *, nums: tuple[int, ...] = ()) -> str:
    """A design-system table; cells are already-escaped HTML. Wide tables scroll sideways."""
    def cell(tag: str, i: int, value: str) -> str:
        cls = ' class="num"' if i in nums else ""
        return f"<{tag}{cls}>{value}</{tag}>"
    ths = "".join(cell("th", i, esc(h)) for i, h in enumerate(head))
    trs = "".join("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>" for r in rows)
    return (f'<div style="overflow-x:auto"><table class="table"><thead><tr>{ths}</tr></thead>'
            f"<tbody>{trs}</tbody></table></div>")


def meridian_page(seed: dict[str, Any], *, theme: str | None = None) -> str:
    """Every record the mock Meridian API serves, read from the same seed files, so the OPP-, ACC- and
    R- IDs in a lesson can be looked up, and a model's answer checked against the data."""
    accounts = {a["account_id"]: a for a in seed["accounts"]}

    def money(amount: float, currency: str) -> str:
        return f"{esc(currency)} {amount:,.0f}"

    opps = []
    for o in seed["opportunities"]:
        acc = accounts.get(o["account_id"], {})
        staffing = "<br>".join(f"{esc(e['role'])} · {esc(e['location'])} · {e['days']:,} days" for e in o["effort"])
        opps.append([f'<code id="{esc(o["opportunity_id"])}">{esc(o["opportunity_id"])}</code>',
                     f'<code>{esc(o["account_id"])}</code><br><span class="small secondary">{esc(acc.get("legal_name", "?"))}</span>',
                     esc(o["service_line"]), esc(o["stage"]), esc(o["engagement_type"]), esc(o["start_date"]),
                     staffing, f'{o["requested_discount_pct"]}%', "yes" if o["travel_required"] else "no",
                     f'<span class="small">{esc(o["crm_notes"])}</span>'])
    accs = []
    for a in seed["accounts"]:
        deals = "<br>".join(f"{esc(d['deal_id'])}: {esc(d['outcome'])} {esc(d['closed_on'])}, "
                            f"{money(d['amount'], d['currency'])} at {d['discount_pct']}% off, {esc(d['service_line'])}"
                            for d in a["deals"]) or '<span class="muted">none</span>'
        accs.append([f'<code id="{esc(a["account_id"])}">{esc(a["account_id"])}</code>', esc(a["legal_name"]),
                     esc(a["industry"]), esc(a["contracting_region"]),
                     ", ".join(f"<code>{esc(c)}</code>" for c in a["competitor_ids"]) or '<span class="muted">none</span>',
                     f'<span class="small">{deals}</span>'])
    rates = [[f"<code>{esc(r['role'])}</code>", esc(r["location"]), money(r["day_rate"], r["currency"]),
              esc(r["version"]), esc(r["valid_from"]), esc(r["valid_to"])]
             for r in sorted(seed["rate_card"], key=lambda r: (r["version"], r["role"], r["location"]))]
    n_opp, n_acc, n_rate = len(opps), len(accs), len(rates)

    body = f"""
<section class="container page-head">
  <p class="eyebrow">The lessons' sample company</p>
  <h1>Meridian data</h1>
  <p class="lede">Northwind Meridian Consulting is a made-up consultancy that sells data, cloud and AI projects
  in the UK, the EU, the US and APAC. Its sales data sits behind one small internal REST API, and from s02 on the
  lab starts a mock of that API for each run. This page shows every record the mock serves, read from the same
  seed files, so you can check a model's answer against the data.</p>
</section>
<section class="container stack-lg" style="padding-bottom:var(--sp-7)">
  <article class="card"><div class="card-head"><h2 class="card-title">What the IDs mean</h2></div>
    <div class="card-body">{_table(["ID", "What it is"], [
        ["<code>OPP-…</code>", "An <b>opportunity</b>: a possible sale being worked on in the CRM, with its stage, "
         "the staffing it needs, the discount the client's procurement asked for, and CRM notes."],
        ["<code>ACC-…</code>", "An <b>account</b>: a client company, with its past deals."],
        ["<code>D-…</code>", "A <b>past deal</b> with an account: won or lost, with its amount and discount."],
        ["<code>R-…</code>", "A <b>role</b> code, such as R-ARCH. The rate card gives each role's day rate per "
         "location (UK, PL, IN), and the dates each rate is valid."]])}</div></article>
  <article class="card"><div class="card-head"><h2 class="card-title">The API</h2></div>
    <div class="card-body stack">{_table(["Request", "Returns"], [
        ["<code>GET /opportunities/{id}</code>", "One opportunity, or a 404 if the ID doesn't exist."],
        ["<code>GET /accounts?page=&amp;page_size=</code>", "One page of accounts (at most 10), each with its "
         "<code>deals[]</code>, and <code>next_page</code> (null on the last page)."],
        ["<code>GET /rate-card?role=&amp;location=&amp;as_of=</code>", "The rate-card rows that match. With "
         "<code>as_of</code>, only the rows valid on that date."],
        ["<code>PATCH /opportunities/{id}</code>", "A write endpoint. It accepts the call and stores nothing."]])}
      <p class="small muted" style="margin:0">Every request needs <code>Authorization: Bearer &lt;token&gt;</code>.
      The lab gives each run its own URL and token, in <code>MERIDIAN_API_URL</code> and
      <code>MERIDIAN_API_TOKEN</code>. The model never sees either.</p></div></article>
  <article class="card"><div class="card-head"><h2 class="card-title">Opportunities</h2><span class="spacer"></span>
    <span class="small muted">{n_opp} records · <code>GET /opportunities/{{id}}</code></span></div>
    <div class="card-body">{_table(["ID", "Account", "Service line", "Stage", "Engagement", "Start", "Staffing",
                                    "Discount asked", "Travel", "CRM notes"], opps, nums=(7,))}</div></article>
  <article class="card"><div class="card-head"><h2 class="card-title">Accounts</h2><span class="spacer"></span>
    <span class="small muted">{n_acc} records · <code>GET /accounts</code></span></div>
    <div class="card-body">{_table(["ID", "Legal name", "Industry", "Region", "Competitors", "Past deals"], accs)}</div></article>
  <article class="card"><div class="card-head"><h2 class="card-title">Rate card</h2><span class="spacer"></span>
    <span class="small muted">{n_rate} rows · <code>GET /rate-card</code></span></div>
    <div class="card-body">{_table(["Role", "Location", "Day rate", "Version", "Valid from", "Valid to"], rates,
                                   nums=(2,))}</div></article>
</section>"""
    return shell("Meridian data · FDE Academy", body, theme=theme, active="meridian")


def design_page(*, theme: str | None = None) -> str:
    """The style guide. Read on each request so edits show up on reload."""
    body = (HERE / "design.html").read_text(encoding="utf-8")
    return shell("Design system · FDE Academy", body, theme=theme, active="design")
