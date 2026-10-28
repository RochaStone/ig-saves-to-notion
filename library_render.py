"""library.html for ig-saves-to-notion: your saves as a searchable hook library, in three motif families.

One function, render_library(), draws the same data three ways:
  analog     index cards you could hold, with washi tape
  cyberpunk  a plum CRT terminal where the search box is the prompt
  y2k-blog   a 2003 blog window with sidebar, hit counter and guestbook
Motif is structure; style.json palette and fonts are colour and type, so every family re-tones.
The page is one self-contained file. It makes no network calls except loading Google Fonts (and falls back
to fonts already on the computer when offline). Your saves never leave the page.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import saves_core
from style_loader import MOTIFS, find_style, load_style, resolve_motif, style_head  # noqa: F401  (re-exported)

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
CSS_FILES = {"analog": ["library.css"], "cyberpunk": ["library.css", "motif-cyberpunk.css"],
             "y2k-blog": ["library.css", "motif-y2k.css"]}
CARD_W, CARD_H = 1080, 1350
CARD_COUNT = 6          # how many saves the share-card picture shows
REPO_ISSUES = "https://github.com/RochaStone/ig-saves-to-notion/issues"
TITLE = "HOOK LIBRARY"

# Card pictures only: once fonts load, shrink the cards until the whole frame fits 1080x1350.
FIT_SCRIPT = """<script>
(function () {
  function fit() {
    var f = document.querySelector(".fit"), l = document.querySelector(".cards"), z = 1;
    while (f && l && f.scrollHeight > f.clientHeight + 1 && z > 0.5) { z -= 0.02; l.style.zoom = z; }
  }
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(fit);
})();
</script>"""

# The search and filter chips. Plain script, no libraries. The saves stay on the page.
FILTER_SCRIPT = """<script>
(function () {
  var q = document.getElementById("q"), cards = [].slice.call(document.querySelectorAll(".entry"));
  var chips = [].slice.call(document.querySelectorAll(".chip")), none = document.getElementById("none");
  var shown = document.getElementById("shown"), on = {hook: null, cat: null};
  function run() {
    var t = q.value.trim().toLowerCase(), n = 0;
    cards.forEach(function (c) {
      var ok = (!t || c.dataset.q.indexOf(t) > -1) && (!on.hook || c.dataset.hook === on.hook) &&
        (!on.cat || c.dataset.cat === on.cat);
      c.hidden = !ok;
      if (ok) { n++; }
    });
    none.hidden = n > 0;
    if (shown) { shown.textContent = n; }
  }
  chips.forEach(function (b) {
    b.addEventListener("click", function () {
      var g = b.dataset.group, v = b.dataset.value;
      on[g] = on[g] === v ? null : v;
      chips.forEach(function (x) { if (x.dataset.group === g) { x.setAttribute("aria-pressed", String(on[g] === x.dataset.value)); } });
      run();
    });
  });
  q.addEventListener("input", run);
})();
</script>"""

PIXEL_HEART = ('<svg class="pix" viewBox="0 0 7 6" width="21" height="18" aria-hidden="true" shape-rendering="crispEdges">'
               '<path fill="currentColor" d="M1 0h2v1h1V0h2v1h1v2H6v1H5v1H4v1H3V5H2V4H1V3H0V1h1z"/></svg>')
PIXEL_STAR = ('<svg class="pix" viewBox="0 0 5 5" width="15" height="15" aria-hidden="true" shape-rendering="crispEdges">'
              '<path fill="currentColor" d="M2 0h1v2h2v1H3v2H2V3H0V2h2z"/></svg>')


def _e(s: object) -> str:
    return html.escape(str(s), quote=True)


def _short(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"


def _when(iso: str) -> str:
    try:
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


def _link(save: dict) -> str:
    url = str(save.get("url", ""))
    return url if url.startswith("https://www.instagram.com/") else "#"


# ---------- the data every motif draws ----------

def _data(saves: list[dict], cfg: dict, style: dict, card: bool) -> dict:
    lines = style.get("lines") if isinstance(style.get("lines"), dict) else {}
    owner = str(style.get("owner") or "").strip()
    stat = saves_core.stats(saves)
    return {
        "saves": saves[:CARD_COUNT] if card else saves,
        "total": stat["total"], "tagged": stat["tagged"],
        "owner": owner, "niche": str((cfg or {}).get("niche") or "").strip(),
        "date": dt.date.today().isoformat(),
        "scrawl": str(lines.get("scrawl") or "").strip(),
        "credit": " \u00b7 ".join(str(x).strip() for x in (owner, style.get("handle"), "made with Rocha Coded")
                                  if x and str(x).strip()),
        "hooks": sorted({s["hook_type"] for s in saves if s.get("hook_type")}),
        "cats": sorted({s.get("category") or "Other" for s in saves}),
    }


def _search_text(s: dict) -> str:
    bits = [s.get("caption", ""), s.get("type", ""), s.get("author", ""), s.get("hook_type", ""), s.get("format", ""),
            s.get("category", ""), s.get("why_saved", ""), s.get("idea", "")]
    return re.sub(r"\s+", " ", " ".join(str(b) for b in bits)).lower()


def _attrs(s: dict) -> str:
    return (f'data-q="{_e(_search_text(s))}" data-hook="{_e(s.get("hook_type", ""))}" '
            f'data-cat="{_e(s.get("category") or "Other")}"')


def _card(s: dict, i: int, motif: str, title_len: int) -> str:
    """One save as a card. The wording of the labels changes with the motif; the data does not."""
    caption = re.sub(r"\s+", " ", s.get("caption") or "").strip()
    title = _e(_short(caption, title_len) if caption else f"Save by @{s.get('author') or 'unknown'}")
    who = _e(s.get("author") or "unknown")
    kind, when = _e(s.get("type", "Post")), _e(_when(s.get("posted", "")))
    hook, fmt, cat = s.get("hook_type"), s.get("format"), s.get("category") or "Other"
    why, idea = s.get("why_saved"), s.get("idea")
    href = _e(_link(s))
    if motif == "cyberpunk":
        tagged = (f'<span class="k">hook</span> {_e(hook)} <span class="k">format</span> {_e(fmt)} '
                  f'<span class="k">in</span> {_e(cat)}') if hook else f'<span class="k">not tagged yet</span> in {_e(cat)}'
        extra = ((f'<p class="sys">\u203a why: {_e(why)}</p>' if why else "") +
                 (f'<p class="sys idea">\u203a idea: {_e(idea)}</p>' if idea else ""))
        return (f'<li class="entry{" tagged" if hook else ""}" {_attrs(s)}>'
                f'<p class="row"><span class="n">[{i:02d}]</span> <span class="px">{kind.lower()}</span> '
                f'<span class="at">@{who}</span> <span class="date">{when}</span></p>'
                f'<h2><a href="{href}" target="_blank" rel="noopener noreferrer">{title}</a></h2>'
                f'<p class="sys">\u203a {tagged}</p>{extra}</li>')
    pills = ((f'<span class="pill hook">{_e(hook)}</span><span class="pill">{_e(fmt)}</span>' if hook
              else '<span class="pill ghost">not tagged yet</span>') + f'<span class="pill ghost">{_e(cat)}</span>')
    notes = ((f'<p class="why"><b>why keep it</b> {_e(why)}</p>' if why else "") +
             (f'<p class="idea"><b>my version</b> {_e(idea)}</p>' if idea else ""))
    return (f'<li class="entry{" tagged" if hook else ""}" {_attrs(s)}><span class="tape" aria-hidden="true"></span>'
            f'<p class="meta"><span class="type">{kind}</span><span class="who">@{who}</span>'
            f'<span class="date">{when}</span></p>'
            f'<h2><a href="{href}" target="_blank" rel="noopener noreferrer">{title}</a></h2>'
            f'<div class="tags">{pills}</div>{notes}</li>')


def _chips(d: dict) -> str:
    def group(name: str, values: list[str]) -> str:
        return "".join(f'<button type="button" class="chip" data-group="{name}" data-value="{_e(v)}" '
                       f'aria-pressed="false">{_e(v)}</button>' for v in values)
    hooks, cats = group("hook", d["hooks"]), group("cat", d["cats"] if len(d["cats"]) > 1 else [])
    return (f'<div class="chips" role="group" aria-label="filter by hook type">{hooks}</div>' if hooks else "") + \
           (f'<div class="chips" role="group" aria-label="filter by category">{cats}</div>' if cats else "")


def _empty(d: dict) -> str:
    return ('<li class="empty"><p>No saves yet. When your first sync has run, they all land here, '
            'ready to search.</p></li>') if not d["saves"] else ""


def _header(d: dict, card: bool) -> str:
    who = f'for <b>{_e(d["owner"])}</b>' if d["owner"] else ""
    where = f' \u00b7 {_e(d["niche"])}' if d["niche"] else ""
    shown = (f'<span id="shown">{len(d["saves"])}</span> of {d["total"]}' if not card
             else f'{len(d["saves"])} of {d["total"]}')
    return f"""<header class="mast">
    <div class="kicker">YOUR INSTAGRAM SAVES, IN ONE PLACE</div>
    <h1>{TITLE}</h1>
    <div class="for">{who}{where}</div>
    <div class="count" aria-live="polite">{shown} saves shown \u00b7 {d["tagged"]} tagged</div>
  </header>"""


def _tools(d: dict, card: bool) -> str:
    if card:
        return '<div class="tools"><span class="fake">search your hooks</span></div>'
    return (f'<div class="tools"><label for="q">search your hooks</label>'
            f'<input id="q" type="search" placeholder="try: price, ritual, reel" autocomplete="off">{_chips(d)}</div>')


def _scrawl(d: dict) -> str:
    return (f'<p class="scrawl">{_e(d["scrawl"])}<svg viewBox="0 0 300 20" aria-hidden="true">'
            f'<path d="M4 14 C 80 4, 160 18, 296 6" /></svg></p>') if d["scrawl"] else ""


def _analog(d: dict, card: bool, frame: bool) -> str:
    cards = "".join(_card(s, i, "analog", 74 if card else 120) for i, s in enumerate(d["saves"], 1)) or _empty(d)
    tag = "main" if frame else "section"
    return f"""<{tag} class="lib{" frame fit" if frame else ""}" aria-label="Hook library">
  {_header(d, card)}
  {_tools(d, card)}
  <ol class="cards">{cards}</ol>
  <p id="none" class="none" hidden>Nothing matches yet. Clear the search to see them all.</p>
  <footer class="foot">{_scrawl(d)}<div class="credit">{_e(d["credit"])}</div></footer>
</{tag}>"""


def _cyberpunk(d: dict, card: bool) -> str:
    cards = "".join(_card(s, i, "cyberpunk", 70 if card else 120) for i, s in enumerate(d["saves"], 1)) or _empty(d)
    search = ('<span class="fake">search your hooks</span>' if card else
              '<label class="sr" for="q">search your hooks</label>'
              '<input id="q" type="search" placeholder="search your hooks" autocomplete="off">')
    echo = f' echo "{_e(d["scrawl"])}"' if d["scrawl"] else ""
    who = f' --for "{_e(d["owner"])}"' if d["owner"] else ""
    return f"""<main class="crt frame" aria-label="Hook library">
  <div class="bezel"><span class="led candy"></span><span class="led gold"></span>
    <span class="px">hook-library \u00b7 rocheverse</span><span class="screws"><i></i><i></i></span></div>
  <div class="screen fit">
    <p class="prompt"><span class="ps">rocheverse:~$</span> hooks{who}</p>
    <p class="sys">\u203a {d["total"]} saves \u00b7 {d["tagged"]} tagged \u00b7 {_e(d["date"])}{" \u00b7 " + _e(d["niche"]) if d["niche"] else ""}</p>
    <p class="prompt find"><span class="ps">rocheverse:~$</span> grep {search}</p>
    {_chips(d) if not card else ""}
    <ol class="cards">{cards}</ol>
    <p id="none" class="sys" hidden>\u203a no matches. clear the search to see everything.</p>
    <p class="prompt last"><span class="ps">rocheverse:~$</span>{echo}<span class="cursor" aria-hidden="true"></span></p>
    <p class="credit px">{_e(d["credit"])}</p>
  </div>
</main>"""


def _y2k(d: dict, card: bool) -> str:
    about = "<br>".join(_e(x) for x in (d["owner"] or "your name here", d["niche"]) if x)
    inner = _analog(d, card, frame=False)
    return f"""<main class="win frame fit" aria-label="Hook library">
  <div class="titlebar"><span class="btns"><i></i><i></i><i></i></span><span class="title px">hook-library.exe</span></div>
  <div class="marquee"><span>{PIXEL_STAR} {d["total"]} saves, {d["tagged"]} tagged {PIXEL_STAR} last updated {_e(d["date"])} {PIXEL_STAR} search your hooks {PIXEL_STAR}</span></div>
  <div class="winbody">
    <div class="post">{inner}</div>
    <aside class="side">
      <section><h3 class="px">about me</h3><p>{about}</p></section>
      <section><h3 class="px">mood</h3><p>inspired \u2727</p></section>
      <section><h3 class="px">currently reading</h3><p>my saves, sorted by hook</p></section>
      <section class="counter"><h3 class="px">hit counter</h3><p>you are visitor no.<br><b>000,777</b></p></section>
      <section class="guest"><h3 class="px">guestbook</h3><p><a href="{REPO_ISSUES}">sign my guestbook</a> {PIXEL_HEART}</p></section>
      <p class="sparkle">{PIXEL_HEART}{PIXEL_STAR}{PIXEL_HEART}</p>
      <p class="updated">last updated {_e(d["date"])}</p>
    </aside>
  </div>
</main>"""


def render_library(saves: list[dict], cfg: dict | None = None, style: dict | None = None,
                   motif: str | None = None, card: bool = False) -> str:
    """The whole page as one HTML string. card=True is the fixed 1080x1350 picture used for the README."""
    style = load_style(find_style()) if style is None else style
    motif = resolve_motif(motif, style)
    d = _data(saves, cfg or {}, style, card)
    body = _cyberpunk(d, card) if motif == "cyberpunk" else _y2k(d, card) if motif == "y2k-blog" else _analog(d, card, True)
    css = "\n".join((ASSETS / f).read_text(encoding="utf-8") for f in CSS_FILES[motif] if (ASSETS / f).exists())
    script = FIT_SCRIPT if card else FILTER_SCRIPT
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hook library{_e(" for " + d["owner"]) if d["owner"] else ""}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>{css}</style>
{style_head(style, motif)}</head>
<body class="{"card" if card else "page"} m-{motif}">
{body}{script}</body></html>"""


# ---------- PNG (only the README pictures use this) ----------

def find_chrome() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for cmd in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge"):
        p = shutil.which(cmd)
        if p:
            return p
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(p).exists():
            return p
    return None


def png_size(path: Path) -> tuple[int, int]:
    with Path(path).open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", head[16:24])


def render_png(page_html: Path, png: Path, width: int = CARD_W, height: int = CARD_H) -> tuple[bool, str]:
    chrome = find_chrome()
    if not chrome:
        return False, ("No Chrome or Chromium found, so no picture this time. The library page is ready. "
                       "Install Chrome, or set CHROME_PATH, then run again.")
    with tempfile.TemporaryDirectory() as profile:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", f"--user-data-dir={profile}",
               f"--window-size={width},{height}", "--force-device-scale-factor=1",
               "--virtual-time-budget=6000", f"--screenshot={png}", Path(page_html).resolve().as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        try:
            subprocess.run(cmd, capture_output=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"Chrome could not render the picture ({exc}). The library page is ready."
    if not Path(png).exists():
        return False, "Chrome ran but wrote no picture. The library page is ready."
    w, h = png_size(png)
    return True, f"Picture: {png} ({w}x{h})"
