"""Snapshot the City of San Mateo Transportation Safety page as normalized Markdown.

Writes page.md (the content that gets diffed) and version.txt (CivicPlus's internal
page version number). Exits non-zero if the fetch or parse looks wrong, so a site
redesign or a block shows up as a failed run instead of a silent empty diff.
"""

import re
import sys
import urllib.request

from bs4 import BeautifulSoup, NavigableString

URL = "https://www.cityofsanmateo.org/4727/Transportation-Safety"
USER_AGENT = "sanmateo-page-watch/1.0 (once-daily change monitor)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def clean(s: str) -> str:
    s = s.replace("\xa0", " ").replace("\ufeff", "").replace("\u200b", "")
    return re.sub(r"\s+", " ", s).strip()


def inline(el) -> str:
    """Flatten an element to text, keeping hyperlinks as [text](href)."""
    if isinstance(el, NavigableString):
        return str(el)
    if el.name in ("script", "style", "img"):
        return ""
    if el.name == "br":
        return " "
    inner = "".join(inline(c) for c in el.children)
    href = (el.get("href") or "").strip()
    if el.name == "a" and href and not href.startswith("#") and clean(inner):
        return f"[{clean(inner)}]({href})"
    return inner


def to_markdown(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("#moduleContent")
    if content is None:
        sys.exit("Could not find #moduleContent; page layout may have changed.")

    lines = []
    headline = soup.select_one("#versionHeadLine")
    if headline:
        lines.append(f"# {clean(headline.get_text())}")

    for block in content.select(".fr-view"):
        for el in block.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            if el.find_parent(["p", "li"]):  # already captured by its parent block
                continue
            text = clean(inline(el))
            if not text:
                continue
            if el.name.startswith("h"):
                lines += ["", "#" * int(el.name[1]) + " " + text]
            elif el.name == "li":
                nested = "circle" in (el.parent.get("style") or "")
                lines.append(("  " if nested else "") + "- " + text)
            else:
                lines.append(text)

    version_el = soup.select_one("#hdnVersionID")
    version = version_el.get("value", "") if version_el else ""
    return "\n".join(lines).strip() + "\n", version


def main() -> None:
    page, version = to_markdown(fetch(URL))
    if len(page) < 2000 or page.count("\n") < 20:
        sys.exit(f"Parsed only {len(page)} chars; refusing to overwrite snapshot.")
    with open("page.md", "w", encoding="utf-8") as f:
        f.write(page)
    with open("version.txt", "w", encoding="utf-8") as f:
        f.write(version + "\n")
    print(f"Wrote {len(page)} chars, page version {version}")


if __name__ == "__main__":
    main()
