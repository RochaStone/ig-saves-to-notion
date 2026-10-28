# The Notion database

One database, called **Instagram Saves**. Every save is one row. You can have it two ways.

## Way 1: Claude makes it for you (no token)
Turn on the Notion connector in Claude. Ask: "Make the Instagram Saves database from notion_template.md inside my Notion page called ...".
Claude makes the database with the properties below, tells you its link, and writes your saves into it.

## Way 2: you make it once, by hand
In Notion, make a new full-page database and add these properties. The names and types need to match exactly, because the tool writes to these names.

| Property | Type | What goes in it |
|---|---|---|
| Name | Title | the first line of the caption, or "Save by @author" |
| URL | URL | the link to the post on instagram.com |
| Media ID | Text | Instagram's id for the post, so nothing is added twice |
| Type | Select | Post, Reel, Carousel |
| Author | Text | the creator's handle, without the @ |
| Caption | Text | the caption, up to Notion's 2000 character limit |
| Posted | Date | when the creator published it (Instagram does not share when you saved it) |
| Category | Select | your own categories from `config.json`, plus Other |
| Status | Select | New, Tagged, Used, Archived |
| Likes, Comments, Plays | Number | the public counts at the time you synced |
| Hook type | Select | Curiosity gap, Proof first, Pain point, Contrarian, Question, Story open, Before and after, List or steps, Relatable moment, Other |
| Format | Select | Talking head, Voiceover on b-roll, Text on screen, Tutorial, Carousel of tips, Photo dump, Quote card, Meme, Interview clip, Other |
| Why saved | Text | one line, from tagging |
| Idea | Text | one line, from tagging |

The same list lives in `notion/schema.json`, which is what the code reads.

## Views worth making
- **Hook library**: a gallery view, grouped by Hook type, sorted by Posted (newest first).
- **To use**: a table filtered to Status is Tagged, sorted by Likes.
- **By category**: a board grouped by Category.

## Finding your database id
Open the database as a full page. The link looks like `notion.so/yourname/Instagram-Saves-` followed by 32 letters and numbers.
Those 32 characters are the id. Put them in `config.json` as `notion_database_id`. Claude can do this for you.

## Tell Notion who is allowed in
If you use a token (`notion_push.py`), open the database, click the three dots, choose Connections, and add your integration.
Without that step Notion answers "not found", which is its way of saying "I cannot see it".
The Notion connector in Claude does not need this step.
