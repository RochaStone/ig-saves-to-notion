#!/usr/bin/env python3
"""Optional: push your saves to Notion with your own Notion integration secret (a token).

You do NOT need this if the Notion connector in Claude is turned on. Claude can write the same saves for you
without any token. This script is for people who prefer to run it by hand, or on a schedule.

  python3 notion_push.py create --parent PAGE_ID   make the Instagram Saves database inside a page you shared
  python3 notion_push.py push [--limit 50]         add saves that are not in Notion yet

The token lives in a file called .env next to this script (copy .env.example). It is read here and sent only to
api.notion.com. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import saves_core as core

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
PACE_SECONDS = 0.4          # a calm pace; Notion allows about three requests a second
RETRY_WAITS = (5, 20, 60)


class PushError(Exception):
    """Something the user can fix, said in plain words."""


def load_token(env_path: Path = Path(".env")) -> str:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token and Path(env_path).is_file():
        for line in Path(env_path).read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "NOTION_TOKEN":
                token = value.strip().strip('"').strip("'")
    if not token:
        raise PushError("No NOTION_TOKEN found. Copy .env.example to .env and paste your Notion integration secret "
                        "after the equals sign. Or skip this script and let Claude write to Notion with the connector.")
    return token


def request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """One call to the Notion API. Waits and retries when Notion asks for a slower pace."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"})
    for wait in (*RETRY_WAITS, None):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and wait is not None:
                time.sleep(float(exc.headers.get("Retry-After") or wait))
                continue
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            hint = " Check the token, and that the page or database is shared with your integration." \
                if exc.code in (401, 403, 404) else ""
            raise PushError(f"Notion said no (HTTP {exc.code}): {detail}.{hint}")
        except (urllib.error.URLError, TimeoutError) as exc:
            if wait is None:
                raise PushError(f"Could not reach Notion ({exc}). Check your internet and try again.")
            time.sleep(wait)
    raise PushError("Notion kept asking to slow down. Wait a few minutes and run it again.")


def database_payload(parent_page_id: str, categories: dict) -> dict:
    """The body for 'create database', from notion/schema.json plus your own category names."""
    props: dict[str, dict] = {}
    for p in core.SCHEMA["properties"]:
        kind, name = p["type"], p["name"]
        if kind == "select":
            options = list(p.get("options", []))
            if name == "Category":
                options = [*categories.keys(), "Other"]
            props[name] = {"select": {"options": [{"name": o} for o in options]}}
        elif kind == "number":
            props[name] = {"number": {"format": "number"}}
        else:
            props[name] = {kind: {}}
    return {"parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": "Instagram Saves"}}], "properties": props}


def existing_media_ids(database_id: str, token: str) -> set[str]:
    """Media IDs already in the database, so a save is never added twice."""
    known: set[str] = set()
    cursor = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = request("POST", f"/databases/{database_id}/query", token, body)
        for page in data.get("results", []):
            rich = page.get("properties", {}).get("Media ID", {}).get("rich_text", [])
            if rich:
                known.add(rich[0].get("plain_text", ""))
        if not data.get("has_more"):
            return known
        cursor = data.get("next_cursor")


def push(saves: list[dict], database_id: str, token: str, limit: int = 50) -> tuple[int, int]:
    """Add saves that are not in Notion yet. Returns (added, already_there). Marks each one as it goes."""
    there = existing_media_ids(database_id, token)
    added = skipped = 0
    for s in core.pending_push(saves, limit):
        if s["id"] in there:
            s["pushed"] = True
            skipped += 1
            continue
        request("POST", "/pages", token, {"parent": {"database_id": database_id},
                                          "properties": core.to_api_properties(s)})
        s["pushed"] = True
        added += 1
        time.sleep(PACE_SECONDS)
    return added, skipped


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="notion_push.py", description="Optional: push saves to Notion with a token.")
    p.add_argument("--saves", type=Path, default=Path("saves.json"))
    p.add_argument("--config", type=Path, default=Path("config.json"))
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--parent", required=True, help="the 32-letter id at the end of a Notion page link")
    u = sub.add_parser("push")
    u.add_argument("--limit", type=int, default=50)
    args = p.parse_args(argv)
    try:
        token = load_token()
        cfg = core.load_config(args.config) if args.config.exists() else {"categories": {}}
        if args.cmd == "create":
            parent = args.parent.replace("-", "").strip()
            if not core.DB_ID.match(parent):
                raise PushError("--parent should be the 32 letters and numbers at the end of your Notion page link.")
            made = request("POST", "/databases", token, database_payload(parent, cfg.get("categories", {})))
            print(f"Database created. Put this in config.json as notion_database_id:\n{made['id'].replace('-', '')}")
            return 0
        db = str(cfg.get("notion_database_id") or "").replace("-", "")
        if not db:
            raise PushError("config.json has no notion_database_id yet. Run the create step first, or paste your database id.")
        saves = core.load_saves(args.saves)
        try:
            added, skipped = push(saves, db, token, args.limit)
        finally:
            core.write_saves(args.saves, saves)   # keep the progress even if a call fails part-way
        print(f"Added {added} to Notion. {skipped} were already there.")
        return 0
    except (PushError, core.ConfigError) as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
