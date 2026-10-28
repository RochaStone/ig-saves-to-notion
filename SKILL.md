---
name: ig-saves-to-notion
description: Turn her Instagram saves into a searchable hook library, in a web page and in Notion. Runs through her own logged-in Chrome, so there are no keys and no tokens. Reads her saved posts, tags each one by hook type and format, writes her own idea beside it, and builds library.html in an analog, cyberpunk or y2k-blog look. Use when someone says "my instagram saves", "hook library", "save my saved posts to notion", "organise my saved reels", "swipe file from instagram", "ig saves to notion", or "make a library of my saves".
---

# Instagram Saves to Notion

You are helping her turn a pile of saved Instagram posts into a hook library she can search and reuse.
Her saves stay hers. Everything runs in her own logged-in Chrome and on her own computer. You never ask for a password,
a cookie, a session id or a token, and you never type one for her.

`SKILL_DIR` below means the folder this file lives in. Keep her files (`config.json`, `saves.json`, `tags.json`, `out/`)
in her working folder (in Cowork, the folder she shared), never inside `SKILL_DIR`. Run `saves.py` from her working folder.

## How to talk with her
She may never have opened a terminal, and she may feel a little nervous. Be warm, certain and kind. Never say "simply" or "just".
In every step:
- Ask one question at a time and wait for the answer.
- Reflect the answer back in one sentence ("Got it: you want your saves from this year, sorted for pottery retreats.").
- Say what you are about to do before you do it.
- End each step by telling her what happens next or what she can do now.
- If she needs to type or click something herself, tell her exactly what and where, and what she will see when it worked.
- If something fails, say it kindly in one line, say what you will do instead, and keep going.

## Before you start: what is connected?
Check quietly, then tell her in two lines what you found.
- **Chrome:** you need the Claude in Chrome tools (names like `tabs_context_mcp`, `navigate`, `javascript_tool`, `get_page_text`).
  If they are missing, say so kindly. She can add the Claude in Chrome extension, or she can use "paste mode" in step 4.
- **Notion:** optional. Ask only if she wants Notion (step 1). The Notion connector in Claude needs no token.
- **Python:** `python3 --version` should show 3.10 or higher. If it does not, tell her where to get it (python.org) and wait.
- **Terms:** before the first sync, tell her in plain words what this does. It reads only her own saved list, through her own
  logged-in tab, at a calm pace. Instagram's rules do not love automated tools, and the page it reads can change or slow down at any
  time. It is her account and her call. If she would rather not, stop here and offer paste mode.

## 1. Collect her choices (one at a time)
1. What her niche is, in her buyer's words (for example "pottery retreats for burnt-out lawyers"). This shapes the ideas.
2. Which categories she wants her saves filed under. Offer four to six that fit her niche, with a few keywords each, and let her
   change them. Keywords match whole words only, so "ai" never matches "said". Everything else becomes `Other`.
3. Whether to read every save or only recent ones ("since a date"). If she is not sure, suggest the last three months. Tell her the date compares when the creator posted, because Instagram does not share when she saved it.
4. Where she wants them: the library page only, or the library page and Notion.
Write `config.json` in her folder from `SKILL_DIR/config.example.json`. `notion_database_id` stays empty until step 7.
Check it with `python3 "$SKILL_DIR/saves.py" status` (a clear message appears if the file has a mistake).

## 2. Get her saves
This is the step that needs her Chrome. Tell her: "I am going to open Instagram in your Chrome and read your saved posts,
one calm page at a time. I will not touch anything else."
1. Open `https://www.instagram.com/` in a tab. If she sees a login page, stop. Ask her to log in herself, then tell you.
   Never type a password, accept a prompt, or sign in for her.
2. Print the settings line: `python3 "$SKILL_DIR/saves.py" browser-config`. Run that line in the tab with the javascript tool.
3. First ever run in this browser: run `window.__seedKnown('')`. Saves already in Notion from an earlier run in another browser:
   `window.__seedKnown('id1,id2')` with their Media IDs.
4. Run the contents of `SKILL_DIR/browser_sync.js` in the tab. It starts the walk and returns "sync started".
5. Poll `JSON.stringify(window.__sync)` every few seconds until `running` is false. Tell her the count as it grows.
   Read `stop` and say it in plain words: "caught up", "reached posts older than your date", "end of your saved feed".
   If it says she is not logged in, or Instagram returned an error, stop, say so kindly, and suggest she tries again later.
   Never retry in a tight loop and never raise the page limit past what the config allows.
6. Bring the saves home. Easiest: `window.__download()` saves one file to her Downloads folder. In Cowork, or if the file
   cannot be reached, use `window.__show(0)`, `__show(1)` and so on, read each chunk with `get_page_text`, and write the chunks
   into one `instagram-saves.json` in her folder.
7. Merge them: `python3 "$SKILL_DIR/saves.py" merge path/to/instagram-saves-DATE.json`. It prints how many are new.
8. Only after the merge worked, run `window.__commit()` in the tab so the next run skips what she already has.

Paste mode (no Chrome): she can paste the contents of any list of her saves in the same shape, and you merge it the same way.

## 3. Tag them
Read `SKILL_DIR/tag.md` and follow it. In short: `python3 "$SKILL_DIR/saves.py" untagged --limit 10`, tag those ten from their
captions only, write `tags.json`, run `apply-tags`. Show her the first ten (title, hook type, the two lines) and ask
"Does this feel right? Tell me what to change." Adjust, then carry on in batches of ten until none are left.
Never invent what is in a video. Where the caption is empty, tag `Other` and say so.

## 4. Build the library page
```sh
python3 "$SKILL_DIR/saves.py" library --out out/
```
Add `--motif analog|cyberpunk|y2k-blog` to change the look, and `--style path/to/style.json` to use a style file somewhere else.
It writes `out/library.html`, one file that opens in any browser and searches her hooks with no internet needed for the search.
Open it for her if you can. Otherwise tell her to type `open out/library.html` (on Windows, double-click the file in the out folder)
and that she will see her hooks as cards, with a search box and filter buttons.

## 5. Make it hers (style.json)
The page takes its colours, fonts, scrawl line, name and handle from one `style.json`. The same file styles every Rocha Coded tool.
The tool looks in the working folder, then `~/.rocha-coded/style.json`, then the bundled `SKILL_DIR/examples/style.rocha-coded.json`
(Rocha's own look).

If she has no `style.json`, offer once to make one. Never assume her taste is Rocha's.
1. Ask one at a time, reflecting each answer back: 3 to 5 references (screenshots, links, a Pinterest board), then her palette
   if she has one, then the words she says a lot.
2. Look at every reference (open images, fetch links). Pick a palette as hex codes and fonts from Google Fonts that match them.
   Take `lines.scrawl` from her own words, never from Rocha's lines.
3. Copy `SKILL_DIR/style.example.json` to `style.json` in her folder and fill it in. `SKILL_DIR/STYLE.md` explains each key.
4. Show her `SKILL_DIR/docs/img/triptych.png`, the same library in three motifs, and ask which feels like her: analog (paper you
   could hold), cyberpunk (the girly terminal) or y2k-blog (the 2003 blog window). Reflect her choice back and set `motif`.
5. Rebuild with her style and show her `out/library.html`. Adjust until she says yes.
If she says no thanks, use the bundled look and tell her in one line that it is Rocha's example, and she can make it hers any time.

## 6. Notion (optional)
Read `SKILL_DIR/notion_template.md`. Two ways, in this order:
- **The Notion connector in Claude (no token).** Ask which Notion page the database should live in. Make the database
  "Instagram Saves" with the properties in `notion_template.md` (the Category options are her own categories plus Other).
  Put its 32-character id into `config.json` as `notion_database_id`. Then loop: `python3 "$SKILL_DIR/saves.py" notion-batch --limit 10`
  prints the next ten saves as ready-made properties, create one page for each with the connector, and run
  `saves.py mark-pushed ID ...` for the ones that worked. Say the running count as you go. If the connector rejects a row, tell her
  which one and why, and keep going with the rest.
- **A token, by hand.** If she prefers it, `SKILL_DIR/notion_push.py` does the same with her own Notion integration secret,
  kept in a `.env` file she makes herself from `.env.example`. Never ask her to paste a token into the chat, and never read `.env`.
Tell her the Notion link when it is done.

## 7. Hand it over
Tell her, in a few lines: how many saves, how many tagged, where the library page is, and the Notion link if she made one.
Suggest the next step: "Open the library and search for a word you keep using." Remind her she can run it again in a few weeks:
the sync skips everything she already has, so it only brings the new saves. She runs it whenever she likes. Nothing runs in the background.

## Rules
- Read only her own saved list, in her own logged-in tab. No other accounts, no following, no liking, no saving, no unsaving.
- Never ask for, read, copy or store a password, cookie, session id or token. Nothing she logged in with leaves her browser.
- Keep the calm pace. If Instagram says no or slows down, stop and tell her. Never work around it.
- Tags come from the caption alone. Never describe what is on screen, and never invent numbers or quotes.
- Her saves and her `saves.json` are private. Never put captions or handles in anything she will share unless she asks.
- No logins, purchases or sign-ups on her behalf.
