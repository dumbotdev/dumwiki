# dumwiki (v0.2)

A crypto event index that updates itself. Every hour it reads crypto news feeds,
groups headlines about the same event, scores each event by how many outlets
covered it, and adds it to a timeline page.

## What's in here

- `collect.py`  the collector. Reads `feeds.json`, writes `events.json`.
- `feeds.json`  the list of news feeds. Add or remove lines to change sources.
- `events.json` the event archive. Grows over time. Starts empty.
- `index.html`  the wiki page. Reads `events.json`.
- `dumbot.mp4`  the small "a dumbot app" stamp in the corner.
- `.github/workflows/collect.yml`  runs the collector every hour on GitHub, free.
- `tests/`      made-up feeds used to check the grouping logic.

## Put it online (no server needed)

1. Create a free account at github.com.
2. Create a new **public** repository, e.g. `dumbot-wiki`.
3. Upload everything in this folder (drag and drop works: "Add file" > "Upload files").
   The `.github` folder must be included.
4. In the repository: Settings > Pages > Source: "Deploy from a branch", branch `main`, folder `/ (root)`. Save.
5. In the repository: Actions tab > "collect" > "Run workflow". This does the first collection.
6. After a minute, your wiki is at `https://YOUR-USERNAME.github.io/dumbot-wiki/`.

From then on it updates itself every hour.

## How ranking works

- Headlines within 48 hours of each other that share enough words become one event.
- Score = 10 points per distinct outlet + 1 per extra mention.
- Each event keeps a short summary from the feed, topic tags (edit the `TAGS` list in `collect.py`), every report with its time, and first/last seen.
- On the page, a month with more than 12 events is split into day sections;
  quieter months stay as one section. Within a section, highest score first.

## Not built yet

- Reddit and X. Both need paid/official API access; scraping them breaks their terms.
- Impressions in the score (comes with those sources).
- Written summaries per event. v0 stores headlines and links only.
- History before the day you turn it on.
