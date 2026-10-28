"""Tests. Run from the repo root: python3 -m unittest discover -s tests -v"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import library_render as L  # noqa: E402
import notion_push  # noqa: E402
import saves_core as core  # noqa: E402
import style_loader as S  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
PAGE1 = json.loads((FIX / "feed_page1.json").read_text(encoding="utf-8"))
PAGE2 = json.loads((FIX / "feed_page2.json").read_text(encoding="utf-8"))
TAGS = json.loads((ROOT / "examples" / "tags.sample.json").read_text(encoding="utf-8"))
CATS = core.load_config(ROOT / "config.example.json")["categories"]
NODE = shutil.which("node")


def sample_saves():
    saves = []
    for page in (PAGE1, PAGE2):
        saves, _ = core.merge_saves(saves, core.parse_feed_page(page), CATS)
    core.apply_tags(saves, [dict(t) for t in TAGS])
    return saves


# ---------- parsing the fixture ----------

class TestParsing(unittest.TestCase):
    def test_fixture_page_one(self):
        saves = core.parse_feed_page(PAGE1)
        self.assertEqual(len(saves), 5)  # six items, one has no shortcode and is skipped
        first = saves[0]
        self.assertEqual(first["type"], "Reel")
        self.assertEqual(first["author"], "example_clay_coach")
        self.assertEqual(first["url"], "https://www.instagram.com/p/FxAmple001/")
        self.assertEqual((first["likes"], first["comments"], first["plays"]), (1840, 96, 52310))
        self.assertEqual(first["posted"], "2026-10-24T09:12:00.000Z")

    def test_types_and_missing_fields(self):
        by_code = {s["code"]: s for s in core.parse_feed_page(PAGE1)}
        self.assertEqual(by_code["FxAmple002"]["type"], "Carousel")
        self.assertEqual(by_code["FxAmple004"]["type"], "Post")
        self.assertIsNone(by_code["FxAmple004"]["plays"])
        self.assertEqual(by_code["FxAmple006"]["caption"], "")  # null caption, bare (unwrapped) item

    def test_malformed_input_never_crashes(self):
        for bad in ({}, {"items": None}, {"items": [None, 5, "x", {"media": None}, {"media": {"id": "1"}}]}, None, []):
            self.assertEqual(core.parse_feed_page(bad), [])

    def test_emoji_caption_survives(self):
        s = next(s for s in core.parse_feed_page(PAGE1) if s["code"] == "FxAmple004")
        self.assertIn("\U0001F52E", s["caption"])

    def test_clip_never_splits_an_emoji(self):
        text = "a" * 1999 + "\U0001F52E"
        clipped = core.clip(text)
        self.assertEqual(clipped, "a" * 1999)
        self.assertLessEqual(len(clipped.encode("utf-16-le")) // 2, core.NOTION_TEXT_LIMIT)


class TestWalk(unittest.TestCase):
    def test_walks_both_pages(self):
        saves, stop = core.walk([PAGE1, PAGE2], set())
        self.assertEqual(len(saves), 11)
        self.assertEqual(stop, "end of saved feed")

    def test_caught_up_after_two_known_pages(self):
        known = {s["id"] for s in core.parse_feed_page(PAGE1) + core.parse_feed_page(PAGE2)}
        saves, stop = core.walk([PAGE1, PAGE2, PAGE2], known)
        self.assertEqual((len(saves), stop), (0, "caught up"))

    def test_since_stops_when_a_whole_page_is_older(self):
        saves, stop = core.walk([PAGE1, PAGE2], set(), since="2026-10-23")
        self.assertEqual(stop, "reached posts older than since")
        self.assertEqual(len(saves), 5)

    def test_since_newer_than_everything_stops_at_once(self):
        saves, stop = core.walk([PAGE1, PAGE2], set(), since="2026-12-01")
        self.assertEqual((saves, stop), ([], "reached posts older than since"))

    def test_page_limit(self):
        saves, stop = core.walk([PAGE1, PAGE2], set(), max_pages=1)
        self.assertEqual((len(saves), stop), (5, "page limit reached"))

    def test_page_cap_is_a_hard_ceiling(self):
        many = [{"items": [{"media": {"id": str(i), "code": f"c{i}", "media_type": 1, "taken_at": 1}}],
                 "more_available": True} for i in range(150)]
        saves, stop = core.walk(many, set(), max_pages=500)
        self.assertEqual((len(saves), stop), (core.MAX_PAGES_CAP, "page limit reached"))


@unittest.skipUnless(NODE, "node is not installed, so the browser script was not compared with the Python parser")
class TestBrowserScriptMatchesPython(unittest.TestCase):
    """browser_sync.js and saves_core.py read the same feed. This runs the real JS file under node."""

    def run_node(self, code):
        script = f"const js = require({json.dumps(str(ROOT / 'browser_sync.js'))});\n{code}"
        done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_same_saves_from_both_fixture_pages(self):
        out = self.run_node(f"const pages = [{json.dumps(PAGE1)}, {json.dumps(PAGE2)}];"
                            "console.log(JSON.stringify(pages.flatMap(p => js.parseFeedPage(p))));")
        self.assertEqual(out, core.parse_feed_page(PAGE1) + core.parse_feed_page(PAGE2))

    def test_same_walk_results(self):
        cases = [(set(), "", 20), (set(), "2026-10-23", 20), (set(), "", 1),
                 ({s["id"] for s in core.parse_feed_page(PAGE1) + core.parse_feed_page(PAGE2)}, "", 20)]
        for known, since, cap in cases:
            py_saves, py_stop = core.walk([PAGE1, PAGE2], known, since, cap)
            js = self.run_node(f"console.log(JSON.stringify(js.walk([{json.dumps(PAGE1)}, {json.dumps(PAGE2)}], "
                               f"{json.dumps(sorted(known))}, {{since: {json.dumps(since)}, maxPages: {cap}}})));")
            self.assertEqual(js["saves"], py_saves, (since, cap))
            self.assertEqual(js["stop"], py_stop, (since, cap))


HARNESS = r"""
// Runs the real browser_sync.js inside a fake instagram.com tab: a fake fetch serving the fixture pages,
// a fake localStorage, and timers that do not wait. Prints what the script did as JSON.
const vm = require('vm'), fs = require('fs');
const job = JSON.parse(process.argv[1]);
const store = new Map(Object.entries(job.storage || {}));
const calls = [];
const body = {innerHTML: ''}, shown = {textContent: ''};
const sandbox = {
  console, JSON, Math, Date, Set, Map, Promise, Number, String, Array, Object, URL, Blob: function () {},
  encodeURIComponent, setTimeout: fn => setImmediate(fn),
  localStorage: {getItem: k => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v))},
  document: {title: '', body, getElementById: () => shown, createElement: () => ({click() {}, remove() {}}),},
  fetch: async (url, opts) => {
    calls.push({url, headers: opts.headers, credentials: opts.credentials, redirect: opts.redirect});
    const step = job.responses[Math.min(calls.length - 1, job.responses.length - 1)];
    return {status: step.status, type: step.type || 'basic', json: async () => step.body};
  },
};
sandbox.window = sandbox;
sandbox.__savesConfig = job.config || {};
vm.createContext(sandbox);
(async () => {
  const returned = vm.runInContext(fs.readFileSync(job.file, 'utf8'), sandbox);
  for (let i = 0; i < 200 && sandbox.__sync.running; i++) await new Promise(r => setImmediate(r));
  const out = {returned, sync: sandbox.__sync, saves: sandbox.__saves, calls};
  if (job.commit) out.committed = sandbox.__commit();
  if (job.show) out.shown = sandbox.__show(0);
  out.storage = Object.fromEntries(store);
  out.body = body.innerHTML;
  console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(NODE, "node is not installed, so the browser script flow was not run")
class TestBrowserScriptFlow(unittest.TestCase):
    """The whole browser run, against a fake tab: the requests it makes, how it stops, and what it remembers."""

    def run_flow(self, responses, config=None, storage=None, commit=False, show=False):
        job = {"file": str(ROOT / "browser_sync.js"), "responses": responses, "config": config or {},
               "storage": {"rocha_coded_saves_known": "[]"} if storage is None else storage, "commit": commit, "show": show}
        done = subprocess.run([NODE, "--input-type=commonjs", "-e", HARNESS, json.dumps(job)],
                              capture_output=True, text=True, timeout=60, cwd=tempfile.gettempdir())
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    OK = [{"status": 200, "body": PAGE1}, {"status": 200, "body": PAGE2}]

    def test_first_run_reads_both_pages_and_asks_for_the_next_one_by_cursor(self):
        out = self.run_flow(self.OK)
        self.assertEqual(out["returned"], "sync started")
        self.assertEqual(out["sync"]["stop"], "end of saved feed")
        self.assertEqual(len(out["saves"]), 11)
        urls = [c["url"] for c in out["calls"]]
        self.assertEqual(urls, ["/api/v1/feed/saved/posts/", "/api/v1/feed/saved/posts/?max_id=QVFDexample_page2"])
        for call in out["calls"]:
            self.assertEqual(call["headers"], {"X-IG-App-ID": "936619743392459"})  # the only header it sets
            self.assertEqual((call["credentials"], call["redirect"]), ("include", "manual"))

    def test_nothing_is_remembered_until_commit_and_the_next_run_catches_up(self):
        out = self.run_flow(self.OK)
        self.assertEqual(out["storage"]["rocha_coded_saves_known"], "[]")
        out = self.run_flow(self.OK, commit=True)
        self.assertEqual(out["committed"], "known saves: 11")
        again = self.run_flow(self.OK, storage=out["storage"])
        self.assertEqual((len(again["saves"]), again["sync"]["stop"]), (0, "caught up"))

    def test_asks_to_seed_on_the_very_first_run_and_makes_no_request(self):
        out = self.run_flow(self.OK, storage={})
        self.assertIn("__seedKnown", out["sync"]["stop"])
        self.assertEqual(out["calls"], [])
        self.assertFalse(out["sync"]["running"])

    def test_logged_out_is_said_kindly(self):
        out = self.run_flow([{"status": 0, "type": "opaqueredirect", "body": {}}])
        self.assertEqual(out["sync"]["stop"], "not logged in to Instagram in this browser")
        self.assertEqual(out["saves"], [])

    def test_a_slow_down_from_instagram_stops_at_once_without_retrying(self):
        out = self.run_flow([{"status": 429, "body": {}}])
        self.assertIn("HTTP 429", out["sync"]["stop"])
        self.assertEqual(len(out["calls"]), 1)

    def test_the_page_limit_and_since_come_from_config(self):
        out = self.run_flow(self.OK, config={"maxPages": 1})
        self.assertEqual(len(out["calls"]), 1)
        self.assertIn("page limit reached", out["sync"]["stop"])
        out = self.run_flow(self.OK, config={"since": "2026-10-23"})
        self.assertEqual((len(out["saves"]), out["sync"]["stop"]), (5, "reached posts older than since"))

    def test_show_writes_a_chunk_of_ten_as_text(self):
        out = self.run_flow(self.OK, show=True)
        self.assertEqual(out["shown"], "chunk 0: 10 saves")
        self.assertEqual(len(out["saves"]), 11)


class TestBrowserScriptSafety(unittest.TestCase):
    def setUp(self):
        self.src = (ROOT / "browser_sync.js").read_text(encoding="utf-8")

    def test_never_touches_credentials(self):
        for needle in ("document.cookie", "sessionid", "csrf", "ds_user_id", "Authorization", "XMLHttpRequest"):
            self.assertNotIn(needle, self.src, needle)

    def test_only_talks_to_the_saved_feed_on_its_own_origin(self):
        self.assertEqual(re.findall(r"fetch\(([^,]+),", self.src), ["url"])
        self.assertIn("'/api/v1/feed/saved/posts/'", self.src)
        self.assertNotIn("http://", self.src.replace("https://www.instagram.com/p/", ""))

    def test_calm_and_capped(self):
        self.assertIn("PAGE_CAP = 100", self.src)
        self.assertIn("PAUSE_MS = 1500", self.src)
        self.assertIn("redirect: 'manual'", self.src)
        self.assertNotIn("console.log", self.src)

    def test_no_hardcoded_notion_or_dates(self):
        self.assertNotRegex(self.src, r"[0-9a-f]{32}")
        self.assertNotIn("2026-03", self.src)
        self.assertNotIn("notion_database_id", self.src)


# ---------- config, categories, merging ----------

class TestConfig(unittest.TestCase):
    def test_example_config_is_valid(self):
        self.assertEqual(core.validate_config(json.loads((ROOT / "config.example.json").read_text())), [])

    def test_plain_word_errors(self):
        errs = core.validate_config({"since": "03/01/2026", "max_pages": 500, "notion_database_id": "abc",
                                     "categories": {"Other": ["x"], "A,B": []}, "colour": 1})
        text = " ".join(errs)
        for needle in ("since should be a date", "max_pages", "notion_database_id", "Other is added", "comma", "Unknown keys"):
            self.assertIn(needle, text)

    def test_missing_and_broken_files_say_what_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(core.ConfigError) as ctx:
                core.load_config(Path(tmp) / "config.json")
            self.assertIn("Copy config.example.json", str(ctx.exception))
            bad = Path(tmp) / "bad.json"
            bad.write_text("{ nope", encoding="utf-8")
            with self.assertRaises(core.ConfigError) as ctx:
                core.load_config(bad)
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_browser_config_carries_no_notion_id(self):
        cfg = {"since": "2026-01-01", "max_pages": 5, "notion_database_id": "a" * 32}
        self.assertEqual(core.browser_config(cfg), {"since": "2026-01-01", "maxPages": 5})

    def test_nothing_of_hers_is_hardcoded(self):
        source = (ROOT / "saves_core.py").read_text() + (ROOT / "notion_push.py").read_text() + (ROOT / "saves.py").read_text()
        self.assertNotIn("3603b396", source)
        self.assertNotRegex(source, r"[0-9a-f]{32}")
        self.assertNotIn("CUTOFF", source)
        for word in ("fashion", "ootd", "wardrobe", "attention", "Keychain", "launchd"):
            self.assertNotIn(word.lower(), source.lower(), word)


class TestCategoriesAndMerge(unittest.TestCase):
    def test_whole_words_only(self):
        cats = {"AI": ["ai"]}
        self.assertEqual(core.classify("she said hello", "", cats), "Other")
        self.assertEqual(core.classify("my AI workflow", "", cats), "AI")

    def test_most_matches_wins_and_no_match_is_other(self):
        self.assertEqual(core.classify("a ritual with tea and a slow morning", "", CATS), "Wellness and rituals")
        self.assertEqual(core.classify("nothing here", "", CATS), "Other")

    def test_merge_is_idempotent_and_keeps_tags(self):
        saves = sample_saves()
        again, added = core.merge_saves(saves, core.parse_feed_page(PAGE1), CATS)
        self.assertEqual(added, 0)
        self.assertEqual(len(again), 11)
        self.assertTrue(all(s.get("hook_type") for s in again))

    def test_merge_keeps_newest_first_and_rejects_foreign_urls(self):
        saves, _ = core.merge_saves([], core.parse_feed_page(PAGE2), CATS)
        saves, _ = core.merge_saves(saves, core.parse_feed_page(PAGE1), CATS)
        posted = [s["posted"] for s in saves]
        self.assertEqual(posted, sorted(posted, reverse=True))
        evil = {"id": "9", "url": "https://evil.example/x", "author": "a", "caption": "c", "type": "Post"}
        self.assertEqual(core.merge_saves([], [evil], CATS)[1], 0)


# ---------- the tagging prompt ----------

class TestTaggingPrompt(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "tag.md").read_text(encoding="utf-8")

    def test_names_every_hook_type_and_format_in_the_schema(self):
        for name in core.HOOK_TYPES + core.FORMATS:
            self.assertIn(f"`{name}`", self.text, name)

    def test_example_input_and_output_are_valid_json_in_the_right_shape(self):
        blocks = [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", self.text, re.S)]
        self.assertEqual(len(blocks), 2)
        given, tags = blocks
        self.assertEqual(set(given[0]), {"id", "type", "author", "caption"})
        self.assertEqual(set(tags[0]), {"id", "hook_type", "format", "why_saved", "idea"})
        self.assertEqual(core.validate_tags(tags, {given[0]["id"]}), [])

    def test_untagged_output_matches_the_documented_input(self):
        saves = sample_saves()
        saves[0].pop("hook_type")
        row = core.untagged(saves, 10)[0]
        self.assertEqual(set(row), {"id", "type", "author", "caption"})

    def test_asks_for_caption_only_and_one_line(self):
        self.assertIn("caption only", self.text.lower().replace("from the caption only", "caption only"))
        self.assertIn("200 characters at most", self.text)

    def test_sample_tags_are_valid(self):
        self.assertEqual(core.validate_tags(TAGS, {s["id"] for s in sample_saves()}), [])

    def test_bad_tags_are_explained(self):
        ids = {"1"}
        bad = [{"id": "2", "hook_type": "Spicy", "format": "Reel", "why_saved": "a\nb", "idea": "x " + chr(0x2014) + " y"}]
        text = " ".join(core.validate_tags(bad, ids))
        for needle in ("no save with that id", "hook_type must be one of", "format must be one of", "one line", "em dash"):
            self.assertIn(needle, text)
        self.assertIn("must be a list", core.validate_tags({}, ids)[0])

    def test_apply_tags_sets_status_and_never_downgrades_used(self):
        saves, _ = core.merge_saves([], core.parse_feed_page(PAGE1), CATS)
        saves[1]["status"] = "Used"
        tags = [{"id": s["id"], "hook_type": "Other", "format": "Other", "why_saved": "w", "idea": "i"} for s in saves[:2]]
        self.assertEqual(core.apply_tags(saves, tags), 2)
        self.assertEqual([s["status"] for s in saves[:2]], ["Tagged", "Used"])


# ---------- Notion shapes ----------

class TestNotion(unittest.TestCase):
    def setUp(self):
        self.save = sample_saves()[0]

    def test_api_properties_use_schema_names(self):
        props = core.to_api_properties(self.save)
        names = {p["name"] for p in core.SCHEMA["properties"]}
        self.assertTrue(set(props) <= names)
        self.assertEqual(props["URL"], {"url": self.save["url"]})
        self.assertEqual(props["Hook type"], {"select": {"name": self.save["hook_type"]}})
        self.assertEqual(props["Likes"], {"number": self.save["likes"]})
        self.assertEqual(props["Posted"], {"date": {"start": self.save["posted"]}})

    def test_connector_properties_follow_the_documented_flat_shape(self):
        props = core.to_mcp_properties(self.save)
        self.assertEqual(props["userDefined:URL"], self.save["url"])
        self.assertEqual(props["date:Posted:start"], self.save["posted"])
        self.assertEqual(props["date:Posted:is_datetime"], 1)
        self.assertEqual(props["Plays"], self.save["plays"])
        self.assertEqual(props["Category"], self.save["category"])

    def test_empty_values_are_left_out(self):
        props = core.to_api_properties({"id": "1", "url": "https://www.instagram.com/p/x/", "author": "a"})
        self.assertNotIn("Likes", props)
        self.assertNotIn("Hook type", props)
        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "Save by @a")

    def test_database_payload_has_every_property_and_your_categories(self):
        body = notion_push.database_payload("a" * 32, CATS)
        self.assertEqual(set(body["properties"]), {p["name"] for p in core.SCHEMA["properties"]})
        options = [o["name"] for o in body["properties"]["Category"]["select"]["options"]]
        self.assertEqual(options, [*CATS.keys(), "Other"])
        self.assertIn("title", body["properties"]["Name"])

    def test_push_skips_what_is_already_there_and_marks_progress(self):
        saves = sample_saves()[:3]
        calls = []

        def fake(method, path, token, body=None):
            calls.append((method, path))
            if path.endswith("/query"):
                return {"results": [{"properties": {"Media ID": {"rich_text": [{"plain_text": saves[0]["id"]}]}}}],
                        "has_more": False}
            return {"id": "page"}

        with mock.patch.object(notion_push, "request", fake), mock.patch.object(notion_push.time, "sleep"):
            added, skipped = notion_push.push(saves, "d" * 32, "token")
        self.assertEqual((added, skipped), (2, 1))
        self.assertTrue(all(s["pushed"] for s in saves))
        self.assertEqual([c for c in calls if c[1] == "/pages"], [("POST", "/pages")] * 2)

    def test_no_token_is_a_clear_message_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(notion_push.PushError) as ctx:
                notion_push.load_token(Path(tmp) / ".env")
        self.assertIn(".env.example", str(ctx.exception))
        self.assertIn("connector", str(ctx.exception))

    def test_token_is_read_from_env_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {}, clear=True):
            env = Path(tmp) / ".env"
            env.write_text("# note\nNOTION_TOKEN=\"abc\"\n", encoding="utf-8")
            self.assertEqual(notion_push.load_token(env), "abc")

    def test_env_example_has_no_value(self):
        self.assertEqual((ROOT / ".env.example").read_text().count("NOTION_TOKEN="), 1)
        self.assertNotRegex((ROOT / ".env.example").read_text(), r"NOTION_TOKEN=\S")


# ---------- style.json ----------

class TestStyle(unittest.TestCase):
    def test_both_bundled_style_files_share_the_same_keys(self):
        a = json.loads((ROOT / "examples" / "style.rocha-coded.json").read_text())
        b = json.loads((ROOT / "style.example.json").read_text())
        self.assertEqual(set(a) - {"references"}, set(b) - {"references"})
        self.assertEqual(set(a["palette"]), set(b["palette"]))
        self.assertEqual(set(a["fonts"]), set(b["fonts"]))

    def test_fallback_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd, home = Path(tmp) / "work", Path(tmp) / "home"
            (home / ".rocha-coded").mkdir(parents=True)
            cwd.mkdir()
            self.assertEqual(S.find_style(cwd=cwd, home=home), S.STYLE_EXAMPLE)
            (home / ".rocha-coded" / "style.json").write_text("{}")
            self.assertEqual(S.find_style(cwd=cwd, home=home), home / ".rocha-coded" / "style.json")
            (cwd / "style.json").write_text("{}")
            self.assertEqual(S.find_style(cwd=cwd, home=home), cwd / "style.json")
            explicit = Path(tmp) / "mine.json"
            explicit.write_text("{}")
            self.assertEqual(S.find_style(explicit, cwd, home), explicit)

    def test_inheritance_rule_borrows_only_palette_and_fonts(self):
        user = {"owner": "", "handle": "", "name": "", "lines": {}, "palette": {"accent": "#00AA88"},
                "fonts": {"masthead": "Bodoni Moda"}, "notes": "", "references": []}
        merged = S.inherit_style(user)
        self.assertEqual(merged["palette"]["accent"], "#00AA88")
        self.assertEqual(merged["palette"]["hero"], "#50163C")       # borrowed
        self.assertEqual(merged["fonts"]["masthead"], "Bodoni Moda")
        self.assertEqual(merged["fonts"]["mono"], "DM Mono")         # borrowed
        for key in ("owner", "handle", "name", "notes"):
            self.assertEqual(merged[key], "")
        self.assertEqual(merged["lines"], {})
        self.assertEqual(merged["references"], [])

    def test_a_users_page_never_prints_rochas_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            mine = Path(tmp) / "style.json"
            mine.write_text(json.dumps({"palette": {"accent": "#00AA88"}, "motif": "analog"}), encoding="utf-8")
            style = S.load_style(mine)
        for motif in S.MOTIFS:
            page = L.render_library(sample_saves(), {"niche": "ceramics"}, style, motif)
            page = page.replace("made with Rocha Coded", "").replace(L.REPO_ISSUES, "")  # the tool's own credit and link
            for word in ("build your founder world", "@rocheverse", "THE ROCHEVERSE TIMES", "Rocha"):
                self.assertNotIn(word, page, (motif, word))

    def test_bundled_example_prints_her_scrawl_and_name(self):
        page = L.render_library(sample_saves(), {}, S.load_style(), "analog")
        self.assertIn("build your founder world", page)
        self.assertIn("@rocheverse", page)

    def test_bad_colours_and_fonts_are_not_injected(self):
        style = {"palette": {"accent": "red; } body { display: none", "gold": "#12345"},
                 "fonts": {"masthead": 'x"}</style><script>alert(1)</script>', "label": "Bricolage Grotesque"}}
        head = S.style_head(style)
        self.assertNotIn("display: none", head)
        self.assertNotIn("<script>", head)
        self.assertIn("--gold: #12345;", head)
        self.assertIn("Bricolage+Grotesque", head)

    def test_motif_order_and_aliases(self):
        self.assertEqual(S.resolve_motif("cyberpunk", {"motif": "y2k-blog"}), "cyberpunk")
        self.assertEqual(S.resolve_motif(None, {"motif": "y2k-blog"}), "y2k-blog")
        self.assertEqual(S.resolve_motif(None, {}), "analog")
        self.assertEqual(S.resolve_motif("retro-tv", {}), "cyberpunk")
        self.assertEqual(S.resolve_motif("guest-check", {}), "analog")
        self.assertEqual(S.resolve_motif("nonsense", {}), "analog")


# ---------- the library, three motifs ----------

class TestLibraryMotifs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saves = sample_saves()
        cls.style = S.load_style()
        cls.cfg = {"niche": "pottery retreats for burnt-out lawyers"}
        cls.pages = {m: L.render_library(cls.saves, cls.cfg, cls.style, m) for m in S.MOTIFS}

    def test_analog_index_cards(self):
        page = self.pages["analog"]
        self.assertIn("m-analog", page)
        self.assertIn("HOOK LIBRARY", page)
        self.assertIn('class="tape"', page)
        self.assertIn("why keep it", page)
        self.assertNotIn("hook-library.exe", page)

    def test_cyberpunk_terminal(self):
        page = self.pages["cyberpunk"]
        self.assertIn("m-cyberpunk", page)
        self.assertIn("rocheverse:~$", page)
        self.assertIn('class="cursor"', page)
        self.assertIn("Silkscreen", page)
        self.assertIn('<input id="q"', page)
        self.assertNotIn('class="tape"', page)

    def test_y2k_blog_window(self):
        page = self.pages["y2k-blog"]
        self.assertIn("m-y2k-blog", page)
        self.assertIn("hook-library.exe", page)
        self.assertIn("000,777", page)
        self.assertIn("mood", page)
        self.assertIn("sign my guestbook", page)
        self.assertIn(L.REPO_ISSUES, page)

    def test_same_data_in_every_motif(self):
        for motif, page in self.pages.items():
            self.assertEqual(page.count('<li class="entry'), 11, motif)
            self.assertEqual(page.count("data-hook=\"Curiosity gap\""), 1, motif)
            self.assertEqual(page.count("https://www.instagram.com/p/"), 11, motif)

    def test_exactly_one_main_landmark(self):
        for motif, page in self.pages.items():
            self.assertEqual(page.count("<main"), 1, motif)

    def test_search_and_filters_are_wired(self):
        for motif, page in self.pages.items():
            self.assertIn('id="q"', page, motif)
            self.assertIn('id="none"', page, motif)
            self.assertIn('class="chip"', page, motif)
            self.assertIn('data-group="hook"', page, motif)

    def test_card_mode_fits_one_box_and_shows_six(self):
        for motif in S.MOTIFS:
            card = L.render_library(self.saves, self.cfg, self.style, motif, card=True)
            self.assertEqual(card.count('<li class="entry'), L.CARD_COUNT, motif)
            self.assertEqual(len(re.findall(r'class="[^"]*\bfit\b', card)), 1, motif)
            self.assertIn("body class=\"card", card)
            self.assertNotIn('id="q"', card)  # a picture has no live search box

    def test_user_text_is_escaped(self):
        evil = dict(self.saves[0], caption='<script>alert(1)</script> "quoted" & more', author='x"><img src=x>',
                    why_saved="<b>bold</b>", url="javascript:alert(1)")
        for motif in S.MOTIFS:
            page = L.render_library([evil], self.cfg, self.style, motif)
            self.assertNotIn("<script>alert(1)", page, motif)
            self.assertNotIn("<img src=x>", page, motif)
            self.assertNotIn("<b>bold</b>", page, motif)
            self.assertNotIn("javascript:", page, motif)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page, motif)

    def test_empty_library_is_friendly(self):
        for motif in S.MOTIFS:
            page = L.render_library([], self.cfg, self.style, motif)
            self.assertIn("No saves yet", page, motif)

    def test_untagged_saves_are_shown_as_such(self):
        saves = [dict(s) for s in self.saves]
        for key in ("hook_type", "format", "why_saved", "idea"):
            saves[0].pop(key)
        self.assertIn("not tagged yet", L.render_library(saves, self.cfg, self.style, "analog"))
        self.assertIn("not tagged yet", L.render_library(saves, self.cfg, self.style, "cyberpunk"))

    def test_unusual_captions_do_not_break_the_page(self):
        odd = dict(self.saves[0], caption="\n\n   ", author="")
        page = L.render_library([odd], self.cfg, self.style, "analog")
        self.assertIn("Save by @unknown", page)

    def test_swapping_palette_retones_every_motif(self):
        teal = dict(self.style, palette={**self.style["palette"], "hero": "#0B3C49", "accent": "#7FDBCA"})
        for motif in S.MOTIFS:
            page = L.render_library(self.saves, self.cfg, teal, motif)
            self.assertIn("--ground: #0B3C49;", page, motif)
            self.assertIn("--candy: #7FDBCA;", page, motif)

    def test_no_glow_or_coloured_shadows_in_any_stylesheet(self):
        for css in (ROOT / "assets").glob("*.css"):
            text = css.read_text(encoding="utf-8")
            self.assertNotIn("text-shadow", text, css.name)
            self.assertNotIn("drop-shadow", text, css.name)
            for shadow in re.findall(r"box-shadow:([^;]+);", text):
                self.assertNotRegex(shadow.replace("rgba(0,0,0", "").replace("rgba(0, 0, 0", ""), r"#(?!000\b)[0-9a-fA-F]{3,6}|var\(--(candy|gold|marker)",
                                    f"{css.name}: {shadow}")

    def test_mobile_rules_exist_for_every_motif(self):
        for name in ("library.css", "motif-cyberpunk.css", "motif-y2k.css"):
            self.assertIn("@media (max-width", (ROOT / "assets" / name).read_text(encoding="utf-8"), name)

    @unittest.skipUnless(L.find_chrome(), "no Chrome here, so the picture was not rendered")
    def test_card_png_is_1080_by_1350(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "card.html"
            page.write_text(L.render_library(self.saves, self.cfg, self.style, "cyberpunk", card=True), encoding="utf-8")
            ok, msg = L.render_png(page, Path(tmp) / "card.png")
            self.assertTrue(ok, msg)
            self.assertEqual(L.png_size(Path(tmp) / "card.png"), (1080, 1350))

    @unittest.skipUnless(L.find_chrome(), "no Chrome here, so the search box was not exercised")
    def test_search_and_filters_work_in_a_real_browser(self):
        probe = """<script>(function () {
          var q = document.getElementById("q"), r = {};
          function vis() { return [].slice.call(document.querySelectorAll(".entry")).filter(function (c) { return !c.hidden; }).length; }
          function type(v) { q.value = v; q.dispatchEvent(new Event("input")); return vis(); }
          r.start = vis(); r.reel = type("reel"); r.none = type("zzzz"); r.noneShown = !document.getElementById("none").hidden;
          r.cleared = type("");
          var chip = document.querySelector('.chip[data-group="hook"][data-value="List or steps"]');
          chip.click(); r.chip = vis(); r.pressed = chip.getAttribute("aria-pressed"); chip.click(); r.off = vis();
          document.querySelector('.chip[data-group="cat"][data-value="Wellness and rituals"]').click();
          r.combo = type("tea");
          document.body.setAttribute("data-result", JSON.stringify(r));
        })();</script>"""
        for motif in S.MOTIFS:
            with tempfile.TemporaryDirectory() as tmp:
                page = Path(tmp) / "probe.html"
                page.write_text(L.render_library(self.saves, self.cfg, self.style, motif).replace("</body>", probe + "</body>"),
                                encoding="utf-8")
                done = subprocess.run([L.find_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
                                       f"--user-data-dir={Path(tmp) / 'profile'}", "--virtual-time-budget=1000",
                                       "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=90)
            found = re.search(r"data-result=(?:'([^']*)'|\"([^\"]*)\")", done.stdout)
            self.assertIsNotNone(found, f"{motif}: the page script did not finish")
            result = json.loads((found.group(1) or found.group(2)).replace("&quot;", '"'))
            reels = sum(1 for s in self.saves if s["type"] == "Reel")
            lists = sum(1 for s in self.saves if s["hook_type"] == "List or steps")
            self.assertEqual(result, {"start": 11, "reel": reels, "none": 0, "noneShown": True, "cleared": 11,
                                      "chip": lists, "pressed": "true", "off": 11, "combo": result["combo"]}, motif)
            self.assertLessEqual(result["combo"], 2, motif)

    def test_no_chrome_degrades_with_a_clear_message(self):
        with mock.patch.object(L, "find_chrome", return_value=None):
            ok, msg = L.render_png(Path("x.html"), Path("x.png"))
        self.assertFalse(ok)
        self.assertIn("library page is ready", msg)


# ---------- the command line, start to finish ----------

class TestCommandLine(unittest.TestCase):
    def run_cli(self, cwd, *args, expect=0):
        done = subprocess.run([sys.executable, str(ROOT / "saves.py"), *args], cwd=cwd, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, expect, done.stdout + done.stderr)
        return done

    def test_whole_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copy(ROOT / "config.example.json", work / "config.json")
            downloaded = work / "instagram-saves-2026-10-28.json"  # the shape window.__download() writes
            downloaded.write_text(json.dumps({"saves": core.parse_feed_page(PAGE1) + core.parse_feed_page(PAGE2)}))

            line = self.run_cli(work, "browser-config").stdout.strip()
            self.assertTrue(line.startswith("window.__savesConfig = "), line)
            self.assertEqual(json.loads(line.split(" = ", 1)[1].rstrip(";")), {"since": "", "maxPages": 20})

            self.assertIn("11 new saves added", self.run_cli(work, "merge", str(downloaded)).stdout)
            self.assertIn("0 new saves added", self.run_cli(work, "merge", str(downloaded)).stdout)
            self.assertIn("11 saves, 0 tagged, 0 in Notion", self.run_cli(work, "status").stdout)

            batch = json.loads(self.run_cli(work, "untagged", "--limit", "10").stdout)
            self.assertEqual(len(batch), 10)

            bad = work / "bad-tags.json"
            bad.write_text(json.dumps([{"id": batch[0]["id"], "hook_type": "Spicy"}]))
            failed = self.run_cli(work, "apply-tags", str(bad), expect=1)
            self.assertIn("hook_type must be one of", failed.stderr)

            self.assertIn("Tagged 11 saves. 0 still to tag.",
                          self.run_cli(work, "apply-tags", str(ROOT / "examples" / "tags.sample.json")).stdout)

            for motif in S.MOTIFS:
                self.run_cli(work, "library", "--motif", motif, "--out", str(work / motif))
                page = (work / motif / "library.html").read_text(encoding="utf-8")
                self.assertIn(f"m-{motif}", page)
                self.assertIn("pottery retreats for burnt-out lawyers", page)

            rows = json.loads(self.run_cli(work, "notion-batch", "--limit", "2").stdout)
            self.assertEqual(len(rows), 2)
            self.assertIn("userDefined:URL", rows[0]["properties"])
            self.run_cli(work, "mark-pushed", rows[0]["id"])
            self.assertIn("1 in Notion", self.run_cli(work, "status").stdout)
            again = json.loads(self.run_cli(work, "notion-batch", "--limit", "20").stdout)
            self.assertEqual(len(again), 10)

    def test_a_first_run_with_no_config_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("0 saves", self.run_cli(tmp, "status").stdout)
            self.run_cli(tmp, "library", "--out", str(Path(tmp) / "out"))
            self.assertIn("No saves yet", (Path(tmp) / "out" / "library.html").read_text(encoding="utf-8"))

    def test_broken_files_are_explained_not_dumped(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "broken.json").write_text("{ nope")
            err = self.run_cli(work, "merge", "broken.json", expect=1).stderr
            self.assertIn("not valid JSON", err)
            self.assertNotIn("Traceback", err)
            err = self.run_cli(work, "merge", "missing.json", expect=1).stderr
            self.assertIn("Could not open", err)
            (work / "config.json").write_text('{"since": "yesterday"}')
            err = self.run_cli(work, "browser-config", expect=1).stderr
            self.assertIn("since should be a date", err)

    def test_notion_push_without_token_exits_kindly(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": "/usr/bin:/bin"}
            done = subprocess.run([sys.executable, str(ROOT / "notion_push.py"), "push"], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 1)
            self.assertIn("NOTION_TOKEN", done.stderr)
            self.assertNotIn("Traceback", done.stderr)


# ---------- house rules for every word and file we ship ----------

class TestHouseRules(unittest.TestCase):
    TEXT = [p for pat in ("*.md", "*.py", "*.js", "*.json", "*.sh", "*.css", "assets/*.css", "scripts/*", "docs/*.md",
                          "tests/*.py", "tests/*.md", "examples/*.json", "examples/*.html", "notion/*.json",
                          ".env.example", ".gitignore") for p in ROOT.glob(pat) if p.is_file()]

    def test_no_em_dashes_anywhere(self):
        for p in self.TEXT:
            self.assertNotIn(chr(0x2014), p.read_text(encoding="utf-8"), p.name)

    def test_banned_words_in_copy(self):
        copy = [ROOT / n for n in ("README.md", "SKILL.md", "tag.md", "notion_template.md", "STYLE.md")]
        for p in copy:
            text = p.read_text(encoding="utf-8")
            text = "\n".join(l for l in text.splitlines() if "Never say" not in l)  # the rule itself names the words
            for word in (r"\bsimply\b", r"\bjust\b", r"\bundocumented\b", r"\bhelpers?\b", r"\bactually\b"):
                self.assertIsNone(re.search(word, text, re.I), (p.name, word))

    def test_footer_is_verbatim_and_last(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        brand = (ROOT.parent / "BRAND.md").read_text(encoding="utf-8") if (ROOT.parent / "BRAND.md").exists() else ""
        footer = readme[readme.index("## Made by Rocha"):]
        if brand:
            block = brand[brand.index("## Made by Rocha"):]
            block = block[:block.index("```")]
            self.assertEqual(footer.strip(), block.strip())
        self.assertIn("Rocha \\\nBrand Alchemist & AI Architect \\\n", footer)
        self.assertTrue(footer.rstrip().endswith("[All tools on GitHub](https://github.com/RochaStone)"))
        self.assertIn("[Sign my guestbook](https://github.com/RochaStone/ig-saves-to-notion/issues)", readme)

    def test_readme_has_the_required_sections(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in ("## Start here", "## If it goes wrong (everyone's first time)", "## Make it yours",
                        "### A note on Instagram's rules", "## Licence"):
            self.assertIn(heading, readme)
        for img in re.findall(r'src="(docs/img/[^"]+)"', readme):
            self.assertTrue((ROOT / img).exists(), img)

    def test_every_image_is_listed(self):
        listed = (ROOT / "docs" / "IMAGES.md").read_text(encoding="utf-8")
        for f in (ROOT / "docs" / "img").iterdir():
            self.assertIn("step-01.svg" if f.name.startswith("step-") else f.name, listed, f.name)

    def test_no_private_paths_or_secrets(self):
        for p in self.TEXT:
            text = p.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/", p.name)

    def test_gitignore_keeps_her_data_out(self):
        ignore = (ROOT / ".gitignore").read_text()
        for name in ("saves.json", "tags.json", "config.json", ".env", "out/", ".pre-commit-config.yaml"):
            self.assertIn(name, ignore)
        self.assertFalse((ROOT / ".pre-commit-config.yaml").exists())

    def test_the_strip_list_is_gone(self):
        for name in (".env", ".venv", "state.json", "sync.log", "transcripts", "sync.py", "setup.sh", "requirements.txt"):
            self.assertFalse((ROOT / name).exists(), name)
        self.assertEqual(list(ROOT.glob("push_ideas*")), [])


if __name__ == "__main__":
    unittest.main()
