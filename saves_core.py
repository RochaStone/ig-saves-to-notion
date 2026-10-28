"""The heart of ig-saves-to-notion: config, feed parsing, categories, tags and Notion property shapes.

Plain Python 3.10+ standard library. browser_sync.js does the same parsing inside her own logged-in
instagram.com tab; parse_media() here mirrors its toSave() so the tests can check both against one fixture.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "notion" / "schema.json").read_text(encoding="utf-8"))
_OPTIONS = {p["name"]: p.get("options", []) for p in SCHEMA["properties"]}
HOOK_TYPES: list[str] = _OPTIONS["Hook type"]
FORMATS: list[str] = _OPTIONS["Format"]
STATUSES: list[str] = _OPTIONS["Status"]
MEDIA_TYPES = {1: "Post", 2: "Reel", 8: "Carousel"}
NOTION_TEXT_LIMIT = 2000
TAG_TEXT_LIMIT = 200
MAX_PAGES_CAP = 100  # a hard ceiling: this reads one person's saves, never a crawl
DB_ID = re.compile(r"^[0-9a-fA-F]{32}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONFIG_KEYS = {"notion_database_id", "since", "max_pages", "niche", "categories"}


class ConfigError(ValueError):
    pass


# ---------- config.json ----------

def validate_config(cfg: object) -> list[str]:
    """Every problem in plain words. An empty list means the config is good to use."""
    if not isinstance(cfg, dict):
        return ["config.json must be one JSON object, wrapped in { }."]
    errors = []
    unknown = sorted(set(cfg) - CONFIG_KEYS - {k for k in cfg if str(k).startswith("_")})
    if unknown:
        errors.append(f"Unknown keys: {', '.join(unknown)}. The keys are: {', '.join(sorted(CONFIG_KEYS))}.")
    db = str(cfg.get("notion_database_id") or "").replace("-", "").strip()
    if db and not DB_ID.match(db):
        errors.append("notion_database_id should be 32 letters and numbers from your database link, or empty.")
    since = str(cfg.get("since") or "").strip()
    if since:
        if not DATE.match(since):
            errors.append("since should be a date like 2026-03-01, or empty for no cutoff.")
        else:
            try:
                dt.date.fromisoformat(since)
            except ValueError:
                errors.append(f"since is not a real date: {since}.")
    pages = cfg.get("max_pages", 20)
    if not isinstance(pages, int) or isinstance(pages, bool) or not 1 <= pages <= MAX_PAGES_CAP:
        errors.append(f"max_pages should be a whole number from 1 to {MAX_PAGES_CAP}.")
    if not isinstance(cfg.get("niche", ""), str):
        errors.append("niche should be words in quotes.")
    cats = cfg.get("categories", {})
    if not isinstance(cats, dict):
        errors.append('categories should look like {"Category name": ["keyword", "another"]}.')
    else:
        for name, words in cats.items():
            if not str(name).strip() or "," in str(name):
                errors.append(f"Category name {name!r} must not be empty or contain a comma (Notion rule).")
            if name == "Other":
                errors.append("Other is added for you. Leave it out of categories.")
            if not isinstance(words, list) or not words or not all(isinstance(w, str) and w.strip() for w in words):
                errors.append(f"Category {name!r} needs a list of keywords, like [\"hook\", \"reel\"].")
    return errors


def load_config(path: Path) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Could not open {path} ({exc.strerror}). Copy config.example.json to config.json first.")
    except ValueError as exc:
        raise ConfigError(f"{path} is not valid JSON ({exc}). Check for a missing comma or quote.")
    errors = validate_config(cfg)
    if errors:
        raise ConfigError("config.json needs a fix:\n- " + "\n- ".join(errors))
    cfg.setdefault("max_pages", 20)
    cfg.setdefault("categories", {})
    cfg.setdefault("since", "")
    cfg.setdefault("niche", "")
    return cfg


def browser_config(cfg: dict) -> dict:
    """The part of config.json the browser script needs. No Notion id ever goes into the browser."""
    return {"since": cfg.get("since", ""), "maxPages": cfg.get("max_pages", 20)}


# ---------- parsing the saved feed (mirrors toSave / walk in browser_sync.js) ----------

def iso(ts: object) -> str:
    if not isinstance(ts, (int, float)) or ts <= 0:
        return ""
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _num(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def parse_media(media: dict) -> dict | None:
    code = media.get("code") or media.get("shortcode")
    if not code or not media.get("id"):
        return None
    cap = media.get("caption")
    user = media.get("user") or {}
    plays = media.get("play_count") or media.get("ig_play_count") or media.get("view_count")
    return {
        "id": str(media["id"]),
        "code": str(code),
        "url": f"https://www.instagram.com/p/{code}/",
        "type": MEDIA_TYPES.get(media.get("media_type"), "Post"),
        "author": str(user.get("username") or ""),
        "caption": str(cap.get("text") or "") if isinstance(cap, dict) else "",
        "posted": iso(media.get("taken_at")),
        "likes": _num(media.get("like_count")),
        "comments": _num(media.get("comment_count")),
        "plays": _num(plays),
    }


def parse_feed_page(data: dict) -> list[dict]:
    items = (data.get("items") or []) if isinstance(data, dict) else []
    out = []
    for item in items:
        media = item.get("media", item) if isinstance(item, dict) else None
        save = parse_media(media) if isinstance(media, dict) else None
        if save:
            out.append(save)
    return out


def since_ts(since: str) -> int:
    if not since:
        return 0
    d = dt.date.fromisoformat(since)
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def walk(pages: list[dict], known: set[str], since: str = "", max_pages: int = 20) -> tuple[list[dict], str]:
    """Walk feed pages newest first, as the browser does. Returns (new saves, why it stopped)."""
    cutoff, fresh_all, known_run = since_ts(since), [], 0
    max_pages = min(max_pages, MAX_PAGES_CAP)
    known = set(known)
    for n, data in enumerate(pages):
        if n >= max_pages:
            return fresh_all, "page limit reached"
        medias = [i.get("media", i) for i in data.get("items") or []]
        if not medias:
            return fresh_all, "end of saved feed"
        if cutoff and all(m.get("taken_at") and m["taken_at"] < cutoff for m in medias):
            return fresh_all, "reached posts older than since"
        fresh = 0
        for save in parse_feed_page(data):
            if save["id"] in known:
                continue
            known.add(save["id"])
            fresh_all.append(save)
            fresh += 1
        known_run = 0 if fresh else known_run + 1
        if known_run == 2:
            return fresh_all, "caught up"
        if not data.get("more_available"):
            return fresh_all, "end of saved feed"
    return fresh_all, "no more pages"


# ---------- categories ----------

def classify(caption: str, author: str, categories: dict[str, list[str]]) -> str:
    """Whole-word keyword match: 'ai' does not match 'said'. Most matches wins; no match is Other."""
    text = f"{caption} {author}".lower()
    best, top = "Other", 0
    for name, words in categories.items():
        score = sum(1 for w in words
                    if re.search(rf"(?<![a-z0-9]){re.escape(w.lower().strip())}(?![a-z0-9])", text))
        if score > top:
            best, top = name, score
    return best


def merge_saves(existing: list[dict], incoming: list[dict], categories: dict[str, list[str]]) -> tuple[list[dict], int]:
    """Add new saves (by id) and keep the whole list newest first. Existing rows keep their tags and status."""
    have = {s["id"] for s in existing}
    added = []
    for raw in incoming:
        save = parse_media(raw) if "media_type" in raw or "taken_at" in raw else dict(raw)
        if not save or not save.get("id") or save["id"] in have:
            continue
        if not str(save.get("url", "")).startswith("https://www.instagram.com/"):
            continue
        have.add(save["id"])
        save.setdefault("status", "New")
        save["category"] = classify(save.get("caption", ""), save.get("author", ""), categories)
        added.append(save)
    merged = added + list(existing)
    merged.sort(key=lambda s: s.get("posted") or "", reverse=True)  # newest first; stable, so ties keep their order
    return merged, len(added)


# ---------- tags (from tag.md) ----------

def validate_tags(tags: object, known_ids: set[str]) -> list[str]:
    if not isinstance(tags, list):
        return ["tags.json must be a list: [ {...}, {...} ]."]
    errors = []
    for i, t in enumerate(tags, 1):
        if not isinstance(t, dict):
            errors.append(f"Tag {i} is not an object.")
            continue
        where = f"Tag {i} (id {t.get('id', '?')})"
        if str(t.get("id", "")) not in known_ids:
            errors.append(f"{where}: no save with that id.")
        if t.get("hook_type") not in HOOK_TYPES:
            errors.append(f"{where}: hook_type must be one of {', '.join(HOOK_TYPES)}.")
        if t.get("format") not in FORMATS:
            errors.append(f"{where}: format must be one of {', '.join(FORMATS)}.")
        for key in ("why_saved", "idea"):
            v = t.get(key)
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{where}: {key} is missing.")
            elif len(v) > TAG_TEXT_LIMIT or "\n" in v:
                errors.append(f"{where}: {key} must be one line, {TAG_TEXT_LIMIT} characters at most.")
            elif "\u2014" in v:
                errors.append(f"{where}: {key} has an em dash. Use a full stop or a comma.")
    return errors


def apply_tags(saves: list[dict], tags: list[dict]) -> int:
    by_id = {str(t["id"]): t for t in tags}
    n = 0
    for s in saves:
        t = by_id.get(s["id"])
        if not t:
            continue
        for key in ("hook_type", "format"):
            s[key] = t[key]
        for key in ("why_saved", "idea"):
            s[key] = t[key].strip()
        if s.get("status", "New") == "New":
            s["status"] = "Tagged"
        n += 1
    return n


def stats(saves: list[dict]) -> dict:
    return {"total": len(saves), "tagged": sum(1 for s in saves if s.get("hook_type")),
            "pushed": sum(1 for s in saves if s.get("pushed"))}


def pending_push(saves: list[dict], limit: int = 10) -> list[dict]:
    return [s for s in saves if not s.get("pushed")][:limit]


def mark_pushed(saves: list[dict], ids: list[str]) -> int:
    wanted, n = {str(i) for i in ids}, 0
    for s in saves:
        if s["id"] in wanted and not s.get("pushed"):
            s["pushed"] = True
            n += 1
    return n


def untagged(saves: list[dict], limit: int = 10) -> list[dict]:
    rows = [s for s in saves if not s.get("hook_type")][:limit]
    return [{"id": s["id"], "type": s.get("type"), "author": s.get("author"),
             "caption": clip(s.get("caption", ""), 600)} for s in rows]


# ---------- Notion shapes ----------

def clip(text: str, limit: int = NOTION_TEXT_LIMIT) -> str:
    """Notion counts UTF-16 units, so an emoji counts as two. Never leaves half an emoji."""
    encoded = (text or "").encode("utf-16-le")
    if len(encoded) <= limit * 2:
        return text or ""
    return encoded[: limit * 2].decode("utf-16-le", errors="ignore")


def title_of(save: dict) -> str:
    first = re.sub(r"\s+", " ", clip(save.get("caption", ""), 100)).strip()
    return first or f"Save by @{save.get('author', '')}"


def _text_fields(save: dict) -> dict[str, str]:
    return {"Media ID": save["id"], "Author": save.get("author", ""), "Caption": clip(save.get("caption", "")),
            "Why saved": save.get("why_saved", ""), "Idea": save.get("idea", "")}


def _select_fields(save: dict) -> dict[str, str]:
    return {"Type": save.get("type", "Post"), "Category": save.get("category", "Other"),
            "Status": save.get("status", "New"), "Hook type": save.get("hook_type", ""),
            "Format": save.get("format", "")}


def to_api_properties(save: dict) -> dict:
    """Properties for the Notion REST API (notion_push.py)."""
    props = {"Name": {"title": [{"text": {"content": title_of(save)}}]}, "URL": {"url": save["url"]}}
    for k, v in _text_fields(save).items():
        if v:
            props[k] = {"rich_text": [{"text": {"content": v}}]}
    for k, v in _select_fields(save).items():
        if v:
            props[k] = {"select": {"name": v}}
    if save.get("posted"):
        props["Posted"] = {"date": {"start": save["posted"]}}
    for k in ("likes", "comments", "plays"):
        if save.get(k) is not None:
            props[k.capitalize()] = {"number": save[k]}
    return props


def to_mcp_properties(save: dict) -> dict:
    """Flat properties for the Notion connector's create-pages tool (the shape it documents)."""
    props = {"Name": title_of(save), "userDefined:URL": save["url"]}
    props.update({k: v for k, v in {**_text_fields(save), **_select_fields(save)}.items() if v})
    if save.get("posted"):
        props["date:Posted:start"] = save["posted"]
        props["date:Posted:is_datetime"] = 1
    for k in ("likes", "comments", "plays"):
        if save.get(k) is not None:
            props[k.capitalize()] = save[k]
    return props


def load_saves(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("saves", []) if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict) and r.get("id")]


def write_saves(path: Path, saves: list[dict]) -> None:
    Path(path).write_text(json.dumps({"saves": saves}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
