#!/usr/bin/env python3
"""Generate every image the README uses, from the tool itself. Needs Chrome or Chromium for the PNGs.

  python3 scripts/make-readme-images.py

Builds the fictional sample library (tests/fixtures plus examples/tags.sample.json), then writes:
  docs/img/hero-y2k.png        the y2k-blog window with the sample library inside (1080x1350)
  docs/img/triptych.png        the same library in analog | cyberpunk | y2k-blog (1620x720)
  docs/img/step-01..05.svg     pixel step badges for "Start here"
  docs/img/divider.svg         a gold pixel hairline
  docs/img/heart.svg           a pixel heart
  examples/saves.sample.json   the sample saves, merged and tagged
  examples/library.sample.html the sample library page (analog)
  docs/IMAGES.md               the list of all of the above
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import library_render  # noqa: E402
import saves_core  # noqa: E402
from style_loader import MOTIFS, load_style  # noqa: E402

IMG = ROOT / "docs" / "img"
FIXTURES = ROOT / "tests" / "fixtures"
# 3x5 pixel digits, rows top to bottom
DIGITS = {"0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
          "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
          "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"]}


def _pixels(text: str, x0: int, y0: int) -> str:
    d = []
    for n, ch in enumerate(text):
        for r, row in enumerate(DIGITS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    d.append(f"M{x0 + n * 4 + c} {y0 + r}h1v1h-1z")
    return "".join(d)


def badge(num: str, ground: str, gold: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 11 9" width="33" height="27" '
            f'shape-rendering="crispEdges"><path fill="{ground}" d="M1 0h9v1h1v7h-1v1H1v-1H0V1h1z"/>'
            f'<path fill="{gold}" d="{_pixels(num, 2, 2)}"/></svg>\n')


def divider(gold: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="720" height="6" shape-rendering="crispEdges">'
            '<defs><pattern id="p" width="12" height="6" patternUnits="userSpaceOnUse">'
            f'<rect width="6" height="2" y="2" fill="{gold}"/><rect x="8" y="2" width="2" height="2" fill="{gold}"/>'
            '</pattern></defs><rect width="720" height="6" fill="url(#p)"/></svg>\n')


def heart(colour: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 7 6" width="21" height="18" shape-rendering="crispEdges">'
            f'<path fill="{colour}" d="M1 0h2v1h1V0h2v1h1v2H6v1H5v1H4v1H3V5H2V4H1V3H0V1h1z"/></svg>\n')


def triptych_html(pngs: dict[str, Path], ground: str, gold: str, cream: str) -> str:
    cells = "".join(
        f'<figure><img src="{p.as_uri()}" alt=""><figcaption>{m}</figcaption></figure>' for m, p in pngs.items())
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Silkscreen&display=swap">
<style>
* {{ margin: 0; box-sizing: border-box; }}
body {{ width: 1620px; height: 720px; background: {ground}; display: flex; gap: 30px; padding: 24px 36px; }}
figure {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 12px; }}
img {{ width: 100%; height: auto; border: 2px solid {gold}; }}
figcaption {{ font-family: "Silkscreen", monospace; color: {cream}; font-size: 22px; letter-spacing: .06em; }}
</style></head><body>{cells}</body></html>"""


def sample_saves(cfg: dict) -> list[dict]:
    """The fictional feed pages, merged and tagged exactly as a real run would do it."""
    saves: list[dict] = []
    for name in ("feed_page1.json", "feed_page2.json"):
        page = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        saves, _ = saves_core.merge_saves(saves, [i.get("media", i) for i in page["items"]], cfg["categories"])
    tags = json.loads((ROOT / "examples" / "tags.sample.json").read_text(encoding="utf-8"))
    saves_core.apply_tags(saves, tags)
    return saves


def main() -> int:
    style = load_style()
    pal = style.get("palette", {})
    ground, gold = pal.get("hero", "#50163C"), pal.get("gold", "#E9B949")
    cream, candy = pal.get("paper", "#FFF7F4"), pal.get("accent", "#FE9DCA")
    IMG.mkdir(parents=True, exist_ok=True)

    for i in range(1, 6):
        (IMG / f"step-{i:02d}.svg").write_text(badge(f"{i:02d}", ground, gold), encoding="utf-8")
    (IMG / "divider.svg").write_text(divider(gold), encoding="utf-8")
    (IMG / "heart.svg").write_text(heart(candy), encoding="utf-8")
    print("SVGs: step-01..05, divider, heart")

    cfg = saves_core.load_config(ROOT / "config.example.json")
    saves = sample_saves(cfg)
    saves_core.write_saves(ROOT / "examples" / "saves.sample.json", saves)
    (ROOT / "examples" / "library.sample.html").write_text(
        library_render.render_library(saves, cfg, style, "analog"), encoding="utf-8")

    ok_all = True
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pngs = {}
        for motif in MOTIFS:
            card = tmp / f"{motif}.html"
            card.write_text(library_render.render_library(saves, cfg, style, motif, card=True), encoding="utf-8")
            png = tmp / f"{motif}.png"
            ok, msg = library_render.render_png(card, png)
            ok_all &= ok
            if not ok:
                print(msg)
                break
            pngs[motif] = png
        if ok_all:
            (IMG / "hero-y2k.png").write_bytes(pngs["y2k-blog"].read_bytes())
            strip = tmp / "triptych.html"
            strip.write_text(triptych_html(pngs, ground, gold, cream), encoding="utf-8")
            ok_all, msg = library_render.render_png(strip, IMG / "triptych.png", 1620, 720)
            print(msg.replace("Picture", "Triptych"))

    (ROOT / "docs" / "IMAGES.md").write_text("""# Images

Every image here is generated by `scripts/make-readme-images.py` from the fictional sample in `tests/fixtures/`
and `examples/tags.sample.json`. No photos, no real people, no real accounts. Every handle starts with `example_`.

| File | What it is |
|---|---|
| `docs/img/hero-y2k.png` | the sample hook library in the y2k-blog motif, used as the README hero |
| `docs/img/triptych.png` | the same library in analog, cyberpunk and y2k-blog, side by side |
| `docs/img/step-01.svg` to `step-05.svg` | pixel step badges for "Start here" |
| `docs/img/divider.svg` | a gold pixel hairline between README sections |
| `docs/img/heart.svg` | the pixel heart beside "If it goes wrong" |
""", encoding="utf-8")
    print("docs/IMAGES.md written" + ("" if ok_all else " (PNGs skipped: no Chrome)"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
