# style.json

One file holds your look. Every Rocha Coded tool reads the same file, so you make it once.

## Where it goes
The tool looks in this order and uses the first one it finds:
1. `style.json` in the folder you are working in (your Cowork folder, or wherever you run Claude Code)
2. `~/.rocha-coded/style.json`, to use one look across every project
3. `examples/style.rocha-coded.json`, the bundled example (Rocha's look)

Start from `style.example.json`: copy it to `style.json` and fill it in. Or ask Claude to make one with you.

## The keys
| Key | What to put there | Used by this tool |
|---|---|---|
| `name` | your brand or studio name | no |
| `owner` | your name, as you sign things | yes, in the heading, the sidebar and the footer line |
| `handle` | your Instagram or main social handle, with the @ | yes, in the footer line |
| `site` | your website address | no |
| `palette.hero` | your ground colour, the deep one everything sits on, as a hex code like `#50163C` | the page behind the cards (never a fill) |
| `palette.wine` | a second deep colour for labels | the small labels and the sidebar bars |
| `palette.accent` | your one bright accent | the tape, the hook pill and the pressed filter button |
| `palette.paper` | a light paper colour | the search box |
| `palette.paper_pink` | the card paper itself | yes |
| `palette.ink` | your text colour | the card text and outlines |
| `palette.marker` | the colour of the handwriting | the "my version" line and the date stamp |
| `palette.plum` | a deep shade | kept for other tools |
| `palette.gold` | a highlight colour for thin rules | the rule under the heading and the counts |
| `palette.cool` | one cool accent, used rarely | no |
| `fonts.masthead` | a big display font from Google Fonts | the HOOK LIBRARY heading |
| `fonts.label` | a font for labels and small print | the labels, pills, buttons and card titles |
| `fonts.body` | a reading font | no (the library prints in mono) |
| `fonts.scrawl` | a handwriting or marker font | your scrawl and the "my version" line |
| `fonts.script` | a signature script font | no |
| `fonts.mono` | a typewriter font | the card text and the numbers |
| `fonts.pixel` (optional) | a pixel font from Google Fonts | the cyberpunk and y2k-blog labels (Silkscreen if empty) |
| `motif` | `analog`, `cyberpunk` or `y2k-blog` (older names like `guest-check` or `retro-tv` still work and map to the nearest one) | yes: index cards, a terminal, or a blog window |
| `lines.scrawl` | a short line in your own words | the handwritten line at the foot of the page |
| `lines.masthead`, `headline`, `todo`, `stamp`, `celebrate`, `affirm`, `invite`, `magazine` | more of your own lines | kept for other tools |
| `references` | 3 to 5 images or links that feel like you | Claude looks at these when it makes your style with you |
| `notes` | your look in one or two sentences | Claude reads this too |

## Good to know
- Colours must be hex codes (`#RRGGBB`). Anything else is skipped and the bundled colour is used for that slot.
- Fonts are Google Fonts names, letters, numbers and spaces only. If a font is not on Google Fonts, or you are offline, the page uses a similar font already on your computer.
- Any colour or font you leave empty borrows the bundled example's, so the page always looks finished.
- Your words and your name never borrow. Leave `lines.scrawl`, `owner` or `handle` empty and the page prints nothing there.
