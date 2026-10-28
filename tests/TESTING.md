# Testing

Everything below was run on 28 Oct 2026, on macOS with Python 3.12.8, Node 25 and Google Chrome installed.

## 1. The tests
```sh
python3 -m unittest discover -s tests -v
```
Result: **84 tests, all OK** (about 40 seconds, most of it three headless Chrome runs). They cover:
- **Reading the saved feed.** Two fictional Instagram pages in `tests/fixtures/` (twelve posts, one with no shortcode, one with no caption, one bare item, one emoji caption, all three media types). Eleven saves come out. Types, authors, links, counts and dates are checked. Malformed input never crashes.
- **The walk.** Both pages; "caught up" after two known pages; the `since` date stopping when a whole page is older; the page limit; the hard cap of 100 pages even if asked for 500.
- **The browser script matches the Python parser.** The real `browser_sync.js` is loaded under Node and given the same pages. Same saves, same stop reasons.
- **The whole browser run against a fake Instagram tab.** The real script runs in a Node sandbox with a fake `fetch` and a fake `localStorage`. It asks for the first page, then the next by cursor, sends only the public app id header, includes the tab's own login without ever reading it, and follows redirects manually. It remembers nothing until `__commit()`, then catches up on the next run. It asks to seed on the very first run and makes no request. A logged-out tab, and an HTTP 429, each stop at once with a plain message and no retry. `maxPages` and `since` come from the config. `__show` writes ten saves as text.
- **Browser script safety.** No cookie, session, CSRF, authorisation or XHR code; one `fetch`, to the saved feed on its own origin; calm pace and page cap present; no hardcoded Notion id or date; no `console.log`.
- **Config.** The example is valid; every mistake is explained in plain words; missing and broken files say what to do; the browser settings never carry a Notion id; none of the old engine's private values, keywords or strings are left in the code.
- **Categories and merging.** Whole-word matching ("ai" does not match "said"); most matches wins; no match is Other; merging twice adds nothing; tags survive a merge; newest first; foreign links are rejected.
- **The tagging prompt.** `tag.md` names every hook type and format in the schema; its two JSON examples parse, have the documented keys and validate; `untagged` prints exactly the documented input; bad tags are explained (unknown id, hook type, format, line breaks, em dash); applying tags never downgrades a Used save.
- **Notion.** Properties for both the API and the connector use the schema names and the documented flat shape; empty values are left out; the database payload has every property and your own categories; a push skips Media IDs already in Notion and marks progress (fake HTTP, no network); no token is a clear message; the token is read from `.env`; `.env.example` ships empty.
- **style.json.** Both bundled style files share the same keys. Fallback order: `--style`, `./style.json`, `~/.rocha-coded/style.json`, the bundled example. **The inheritance rule:** a user file borrows only missing palette and font entries, never lines, owner, handle, name, references or notes. A user's page, in all three motifs, never prints "build your founder world", "@rocheverse", "THE ROCHEVERSE TIMES" or "Rocha". The bundled example does print them. Bad colours and fonts (including a `</style><script>` attempt) are not injected. Motif order: `--motif`, then `style.json`, then analog; old names map to the nearest family.
- **Three motifs from one function.** analog (index cards, washi tape, "why keep it"), cyberpunk (`rocheverse:~$` prompt, block cursor, Silkscreen loaded, the search box inside the prompt), y2k-blog (`hook-library.exe` window, mood line, hit counter `000,777`, guestbook link to the repo's Issues). The same eleven saves in each. One `main` landmark each. Search and filters are wired in each. The share card shows six saves and carries exactly one box to fit. User text is escaped, including `<script>`, quotes, a `javascript:` link and an empty caption. An empty library and untagged saves render kindly. A new palette re-tones every motif. No `text-shadow`, `drop-shadow` or coloured box shadow in any stylesheet. Every stylesheet has a mobile rule.
- **A real browser.** Headless Chrome opens each of the three pages and runs the search box and the filter buttons: typing "reel", a word that matches nothing (the empty message appears), clearing, a hook-type button on and off, and a category button plus a word. The card picture comes out at exactly 1080x1350.
- **The command line, start to finish.** In a temporary folder: browser settings line, merge twice (11 new, then 0), status, ten untagged, a bad tags file refused with a plain message, good tags applied, the library in all three motifs with the niche in each, ten Notion rows prepared, one marked, ten left. A first run with no config works. Broken and missing files are explained with no traceback. `notion_push.py` with no token exits with a kind message.
- **House rules.** No em dashes in any shipped file. No "simply", "just", "undocumented", "helpers" or "actually" in the copy. The README footer is byte-for-byte the one in `BRAND.md`, and it is the last thing in the file. Required README sections and every image it links exist. Every image is listed in `docs/IMAGES.md`. No home-directory paths. `.gitignore` keeps `saves.json`, `tags.json`, `config.json`, `.env` and `out/` out of git. The old engine's `.env`, `.venv`, logs, state, transcripts, `push_ideas*`, `sync.py` and `setup.sh` are all gone.

## 2. Images, by eye
`python3 scripts/make-readme-images.py` built the sample from the fixtures and rendered all three share cards at 1080x1350 and the triptych at 1620x720. Each was opened and checked: nothing cut off, no glow, the plum header readable. One real bug found by eye and fixed: the card class on each entry also matched the page `body`, which turned the whole analog page pink. The entries are now `.entry`. The three pages were also rendered side by side at 390px wide inside iframes (headless Chrome will not size a window under 500px): no sideways scroll, cards stack, filter buttons wrap.

## 3. Security gate
```sh
./scripts/security-check.sh
```
Result: 9 passed, 0 failed, **SAFE TO PUBLISH**, run before the commit.

## Not tested
- **A live Instagram account.** Nothing here was run against a real logged-in Instagram tab. The request and the shape of the reply come from the engine this tool was built from, which read the same saved feed with the same fields. Instagram can change an internal page like this one without notice, so the first live run is the real test. The fixtures are fictional and written to that shape.
- **The Notion connector write path.** The rows `notion-batch` prints follow the connector's documented flat shape, but no page was created in a real Notion workspace from this build.
- **`notion_push.py` against the live Notion API.** The request bodies are built and tested, the calls are tested with a fake, and no token was used. The database-create call uses Notion API version 2022-06-28.
- **Claude Cowork.** The zip was built, but it was not uploaded to Cowork, and whether Cowork has the Claude in Chrome tools connected was not checked.
- **Reading the saves back with `get_page_text`.** `__show` is tested for what it writes to the page, not for Claude reading it back.
- **Windows and Linux.**
