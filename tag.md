# Tagging prompt

Claude reads this file when it tags your saves. You can edit it. Change the words and the tags change with them.

## What you are doing
You are helping a founder turn her saved Instagram posts into a hook library she can search.
For each save, you read the caption and decide four things. Work from the caption only. You cannot see the video or the
pictures, so never describe what is on screen. If the caption is empty or too short to tell, use `Other` and say so in one line.

Her niche, from `config.json`: **the `niche` line**. Use it for the `idea`. If it is empty, write the idea for a small service business.

## The input
Run `python3 saves.py untagged --limit 10`. It prints up to ten saves like this:
```json
[
  {"id": "3501000000000000001_9001", "type": "Reel", "author": "example_clay_coach",
   "caption": "Nobody tells you the first week of a retreat business is mostly spreadsheets."}
]
```

## The four tags
1. `hook_type`: how the opening line grabs attention. Pick exactly one:
   `Curiosity gap`, `Proof first`, `Pain point`, `Contrarian`, `Question`, `Story open`, `Before and after`, `List or steps`, `Relatable moment`, `Other`.
2. `format`: the shape of the post, as far as the caption and type tell you. Pick exactly one:
   `Talking head`, `Voiceover on b-roll`, `Text on screen`, `Tutorial`, `Carousel of tips`, `Photo dump`, `Quote card`, `Meme`, `Interview clip`, `Other`.
   A `Carousel` type almost always means `Carousel of tips` or `Quote card`. A `Reel` is never a `Photo dump`.
3. `why_saved`: one line on what makes this one worth keeping. Say what the hook does, in plain words ("it promises a secret and makes you wait for it").
4. `idea`: one line for a post of her own this could spark, in her niche. A direction, not a finished caption.

## Rules for the two lines
- One line each, 200 characters at most, no line breaks.
- Plain words. No em dashes, no hype, no hashtags, no filler.
- Do not copy the caption back. Do not invent numbers, results or quotes that are not in the caption.
- Write `why_saved` as what the post does, not as a claim about what she was thinking. She can change it.

## The output
Write a file called `tags.json`: one list, one object per save, using the exact `id` from the input.
```json
[
  {"id": "3501000000000000001_9001",
   "hook_type": "Curiosity gap",
   "format": "Talking head",
   "why_saved": "It promises the unglamorous truth and makes you wait for the list.",
   "idea": "The three boring tasks that quietly decide whether a retreat sells out."}
]
```
Then run `python3 saves.py apply-tags tags.json`. If it prints a list of problems, fix them in `tags.json` and run it again.
Tell her how many are tagged and how many are left. Do ten at a time, and show her the first ten before you carry on.
