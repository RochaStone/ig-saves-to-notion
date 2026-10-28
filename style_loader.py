"""style.json for ig-saves-to-notion: the shared Rocha Coded fallback order and inheritance rule.

Fallback order: --style, ./style.json, ~/.rocha-coded/style.json, the bundled examples/style.rocha-coded.json.
Inheritance rule: a user's style borrows ONLY missing palette and fonts from the bundled example.
Lines, owner, handle, name, references and notes never fall back to Rocha's.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLE_EXAMPLE = HERE / "examples" / "style.rocha-coded.json"
MOTIFS = ("analog", "cyberpunk", "y2k-blog")
# Older motif names from the shared schema map to the nearest family.
MOTIF_ALIASES = {"guest-check": "analog", "front-page": "analog", "magazine-scrawl": "analog",
                 "pink-paper": "analog", "rotary": "analog", "leopard": "analog", "neutral": "analog",
                 "retro-tv": "cyberpunk", "sticker-collage": "y2k-blog", "y2k": "y2k-blog", "blog": "y2k-blog"}
COLOUR = re.compile(r"^#[0-9A-Fa-f]{3,8}$")
FONT_NAME = re.compile(r"^[A-Za-z0-9 ]{1,40}$")
# style.json palette key -> CSS variable. hero is the GROUND (page behind the card), never a fill.
PALETTE_VARS = {"hero": "--ground", "wine": "--wine", "accent": "--candy", "paper_pink": "--paper",
                "paper": "--cream", "ink": "--ink", "marker": "--marker", "plum": "--plum", "gold": "--gold"}
# style.json font key -> (CSS variable, system fallback stack, Google Fonts axes or "")
FONT_VARS = {
    "masthead": ("--serif", 'Georgia, "Times New Roman", serif', "ital,wght@0,400;0,900;1,400;1,900"),
    "label": ("--label", 'system-ui, "Helvetica Neue", Arial, sans-serif', "wght@400;600;800"),
    "mono": ("--mono", "ui-monospace, Menlo, Consolas, monospace", "wght@400;500"),
    "scrawl": ("--scrawl", '"Marker Felt", "Comic Sans MS", cursive', ""),
    "pixel": ("--pixel", '"Pixelify Sans", ui-monospace, monospace', "wght@400;700"),
}
HOUSE_PIXEL_FONT = "Silkscreen"  # chrome labels in cyberpunk and y2k-blog unless fonts.pixel says otherwise


def find_style(explicit: Path | None = None, cwd: Path | None = None, home: Path | None = None) -> Path:
    candidates = [explicit] if explicit else []
    candidates += [Path(cwd or Path.cwd()) / "style.json",
                   Path(home or Path.home()) / ".rocha-coded" / "style.json", STYLE_EXAMPLE]
    return next((Path(c) for c in candidates if c and Path(c).is_file()), STYLE_EXAMPLE)


def inherit_style(user: dict) -> dict:
    try:
        example = json.loads(STYLE_EXAMPLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        example = {}
    merged = dict(user)
    for key in ("palette", "fonts"):
        mine = user.get(key) if isinstance(user.get(key), dict) else {}
        base = example.get(key) if isinstance(example.get(key), dict) else {}
        merged[key] = {**base, **{k: v for k, v in mine.items() if str(v or "").strip()}}
    return merged


def load_style(path: Path | None = None) -> dict:
    path = path or STYLE_EXAMPLE
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Could not read style file {path} ({exc}). Using the bundled example look.", file=sys.stderr)
        try:
            data = json.loads(STYLE_EXAMPLE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        path = STYLE_EXAMPLE
    data = data if isinstance(data, dict) else {}
    return data if Path(path) == STYLE_EXAMPLE else inherit_style(data)


def resolve_motif(requested: str | None, style: dict) -> str:
    """--motif wins, then style.json motif, then analog. Old names map to the nearest family."""
    raw = str(requested or style.get("motif") or "analog").strip().lower()
    raw = MOTIF_ALIASES.get(raw, raw)
    return raw if raw in MOTIFS else "analog"


def style_head(style: dict, motif: str = "analog") -> str:
    """Font links plus a :root block that overrides colours and fonts. Every value is validated first."""
    palette = style.get("palette") if isinstance(style.get("palette"), dict) else {}
    fonts = dict(style.get("fonts")) if isinstance(style.get("fonts"), dict) else {}
    if motif != "analog" and not str(fonts.get("pixel") or "").strip():
        fonts["pixel"] = HOUSE_PIXEL_FONT
    css_vars, links = [], []
    for key, var in PALETTE_VARS.items():
        val = str(palette.get(key) or "").strip()
        if COLOUR.match(val):
            css_vars.append(f"{var}: {val};")
    for key, (var, fallback, axes) in FONT_VARS.items():
        fam = str(fonts.get(key) or "").strip()
        if not FONT_NAME.match(fam):
            continue
        css_vars.append(f'{var}: "{fam}", {fallback};')
        q = fam.replace(" ", "+")
        if axes:  # weighted request first; if the family lacks a weight, the plain link below still loads it
            links.append(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={q}:{axes}&display=swap">')
        links.append(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={q}&display=swap">')
    return "\n".join(links) + f"\n<style>:root {{ {' '.join(css_vars)} }}</style>"
