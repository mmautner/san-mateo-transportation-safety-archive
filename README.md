# San Mateo Transportation Safety page watch

Checks the City of San Mateo's [Transportation Safety page](https://www.cityofsanmateo.org/4727/Transportation-Safety) once a day and emails you a word-level diff whenever its content changes. It runs on GitHub Actions, costs nothing in a public repo, and has no AI or third-party service in the loop.

## How it works

Every morning at 8:17am Pacific, the workflow:

1. Fetches the page and converts the main body into clean Markdown (`page.md`): headings, paragraphs, list items, and links kept as `[text](url)`. Navigation, footer, slideshow, scripts and styling are dropped, so cosmetic edits to the site template don't trigger alerts.
2. Saves the page's internal CivicPlus version number to `version.txt`.
3. Commits both files if anything changed.
4. If `page.md` changed, opens a GitHub issue containing the diff. GitHub emails you about new issues in repos you own, so the issue is the notification.

The diff marks changes inline, for example:

```
...award anticipated in [-early December.-]{+mid-January.+}
```

The commit history becomes a dated record of everything the page has said, which is useful for holding the City to stated timelines.

## Setup

1. Create a new **public** GitHub repository. (Private works too, using about 30 of the 2,000 free monthly Actions minutes.)
2. Add the files from this ZIP, keeping the folder layout:
   ```
   watch.py
   .github/workflows/watch.yml
   README.md
   ```
3. Make sure Issues are enabled (Settings > General > Features; on by default).
4. Go to the Actions tab, select "Watch Transportation Safety page," and click **Run workflow**. This first run saves the baseline snapshot and does not open an issue.
5. Confirm you're getting email for issues: Settings > Notifications on your GitHub account should have email enabled for "Watching," and your own new repos are watched by default.

## What triggers an email

| Event | Commit | Issue / email |
|---|---|---|
| Page text, links, or headings change | Yes | Yes, with diff |
| Only formatting changes (version number bumps, text identical) | Yes | No |
| Nothing changes | No | No |
| Page fails to load or parses to almost nothing (redesign, block, outage) | No | GitHub's failed-run email |

The parser refuses to overwrite the snapshot if the result is under 2,000 characters or 20 lines, so a broken fetch shows up as a failure rather than a giant "everything was deleted" diff.

## Maintenance notes

- **60-day rule.** GitHub disables scheduled workflows in public repos after 60 days without repository activity. The workflow writes a `.heartbeat` file on the 1st of each month to keep the repo active even if the page goes quiet.
- **If the City redesigns the site.** The parser reads content from `#moduleContent .fr-view`, which is how CivicPlus (the City's web platform) structures editor content. A redesign that changes that markup will cause failed runs; `to_markdown()` in `watch.py` is the only function that would need updating.
- **Watching another page.** Change `URL` in `watch.py` and the URL in the issue body in `watch.yml`. Other CivicPlus pages on cityofsanmateo.org use the same structure. To watch several pages, copy the job or loop over a list of URLs, writing one Markdown file per page.
- **Timing.** GitHub may delay scheduled runs by several minutes during busy periods. The odd minute (:17) avoids the top-of-hour rush.

## Running locally

```
pip install beautifulsoup4
python watch.py
```

This writes `page.md` and `version.txt` to the current directory.
