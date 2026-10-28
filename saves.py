#!/usr/bin/env python3
"""ig-saves-to-notion: the small command line Claude uses behind the scenes.

  python3 saves.py browser-config           the one line to paste into your Instagram tab before browser_sync.js
  python3 saves.py merge FILE [FILE ...]    add downloaded saves to saves.json (nothing is added twice)
  python3 saves.py untagged [--limit 10]    the next saves to tag, as JSON, for tag.md
  python3 saves.py apply-tags tags.json     check the tags and write them into saves.json
  python3 saves.py library [--motif ...]    write out/library.html, your searchable hook library
  python3 saves.py notion-batch [--limit 10]  the next saves as Notion connector properties, as JSON
  python3 saves.py mark-pushed ID [ID ...]  remember which saves are in Notion
  python3 saves.py status                   how many saves, tagged and in Notion

Run it from the folder where your saves.json and config.json live. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import library_render
import saves_core as core
from style_loader import find_style, load_style, resolve_motif

SAVES = Path("saves.json")
CONFIG = Path("config.json")


def _config(path: Path) -> dict:
    """config.json if it exists, else a safe empty one, so every command works on a first run."""
    if Path(path).exists():
        return core.load_config(path)
    return {"since": "", "max_pages": 20, "niche": "", "categories": {}, "notion_database_id": ""}


def cmd_browser_config(args: argparse.Namespace) -> int:
    cfg = _config(args.config)
    print("window.__savesConfig = " + json.dumps(core.browser_config(cfg)) + ";")
    return 0


def _read_saves_file(path: Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise core.ConfigError(f"Could not open {path} ({exc.strerror}).")
    except ValueError as exc:
        raise core.ConfigError(f"{path} is not valid JSON ({exc}). If you pasted it by hand, check the ends of the file.")
    rows = data.get("saves", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise core.ConfigError(f"{path} should hold a list of saves.")
    return [r for r in rows if isinstance(r, dict)]


def cmd_merge(args: argparse.Namespace) -> int:
    cfg = _config(args.config)
    existing = core.load_saves(args.saves)
    total_new = 0
    for f in args.files:
        existing, added = core.merge_saves(existing, _read_saves_file(f), cfg.get("categories", {}))
        total_new += added
        print(f"{f}: {added} new")
    core.write_saves(args.saves, existing)
    print(f"{total_new} new saves added. {len(existing)} in {args.saves}.")
    return 0


def cmd_untagged(args: argparse.Namespace) -> int:
    saves = core.load_saves(args.saves)
    print(json.dumps(core.untagged(saves, args.limit), ensure_ascii=False, indent=1))
    return 0


def cmd_apply_tags(args: argparse.Namespace) -> int:
    saves = core.load_saves(args.saves)
    try:
        tags = json.loads(Path(args.tags).read_text(encoding="utf-8"))
    except OSError as exc:
        raise core.ConfigError(f"Could not open {args.tags} ({exc.strerror}).")
    except ValueError as exc:
        raise core.ConfigError(f"{args.tags} is not valid JSON ({exc}).")
    errors = core.validate_tags(tags, {s["id"] for s in saves})
    if errors:
        print("The tags need a fix before they can be saved:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    n = core.apply_tags(saves, tags)
    core.write_saves(args.saves, saves)
    left = len([s for s in saves if not s.get("hook_type")])
    print(f"Tagged {n} saves. {left} still to tag.")
    return 0


def cmd_library(args: argparse.Namespace) -> int:
    saves = core.load_saves(args.saves)
    cfg = _config(args.config)
    style = load_style(find_style(args.style))
    motif = resolve_motif(args.motif, style)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    page = out / "library.html"
    page.write_text(library_render.render_library(saves, cfg, style, motif), encoding="utf-8")
    print(f"Library ({motif}): {page}  {len(saves)} saves, {core.stats(saves)['tagged']} tagged")
    return 0


def cmd_notion_batch(args: argparse.Namespace) -> int:
    saves = core.load_saves(args.saves)
    batch = core.pending_push(saves, args.limit)
    print(json.dumps([{"id": s["id"], "properties": core.to_mcp_properties(s)} for s in batch],
                     ensure_ascii=False, indent=1))
    return 0


def cmd_mark_pushed(args: argparse.Namespace) -> int:
    saves = core.load_saves(args.saves)
    n = core.mark_pushed(saves, args.ids)
    core.write_saves(args.saves, saves)
    print(f"Marked {n} saves as in Notion.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    s = core.stats(core.load_saves(args.saves))
    print(f"{s['total']} saves, {s['tagged']} tagged, {s['pushed']} in Notion.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="saves.py", description="Your Instagram saves, as a hook library.")
    p.add_argument("--saves", type=Path, default=SAVES, help="your saves file (default saves.json)")
    p.add_argument("--config", type=Path, default=CONFIG, help="your settings (default config.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("browser-config").set_defaults(fn=cmd_browser_config)
    m = sub.add_parser("merge")
    m.add_argument("files", nargs="+", type=Path)
    m.set_defaults(fn=cmd_merge)
    u = sub.add_parser("untagged")
    u.add_argument("--limit", type=int, default=10)
    u.set_defaults(fn=cmd_untagged)
    a = sub.add_parser("apply-tags")
    a.add_argument("tags", type=Path)
    a.set_defaults(fn=cmd_apply_tags)
    lib = sub.add_parser("library")
    lib.add_argument("--motif", choices=library_render.MOTIFS, default=None)
    lib.add_argument("--style", type=Path, default=None)
    lib.add_argument("--out", type=Path, default=Path("out"))
    lib.set_defaults(fn=cmd_library)
    nb = sub.add_parser("notion-batch")
    nb.add_argument("--limit", type=int, default=10)
    nb.set_defaults(fn=cmd_notion_batch)
    mp = sub.add_parser("mark-pushed")
    mp.add_argument("ids", nargs="+")
    mp.set_defaults(fn=cmd_mark_pushed)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except core.ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
