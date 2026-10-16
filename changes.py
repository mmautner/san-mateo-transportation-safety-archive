"""Summarize the differences between two page.md snapshots as readable Markdown.

Usage: python changes.py OLD.md NEW.md          # issue body
       python changes.py OLD.md NEW.md --title  # short list of changed sections

The body lists each added, removed, or edited line grouped under the page heading
(and the bold-looking subheading line, like "Project Update") it falls in. Within an edited
line, removed text is <del>struck through</del> and added text is <b>bold</b>.
Long runs of unchanged words are shortened to "…", with the full before/after text
in a collapsed section at the end.
"""

import difflib
import os
import re
import sys

CONTEXT_WORDS = 8  # unchanged words kept on each side of an edit within a line
SIMILAR = 0.5  # lines at least this similar are shown as one edited line
MAX_BODY = 60000  # GitHub caps issue bodies at 65,536 characters
MAX_TITLE = 120


def strip_marker(line: str) -> str:
    """Drop the leading list/heading marker, which the bullets below replace."""
    return re.sub(r"^\s*(?:#+|-)\s+", "", line)


def strip_links(text: str) -> str:
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


def is_heading(line: str) -> bool:
    return line.startswith("#")


def is_subheading(line: str) -> bool:
    """Short standalone lines the City styles as headings, like "What We Are Adding"."""
    text = strip_links(line).strip()
    return (not line.startswith(("#", "-", " ")) and has_text(text)
            and len(text) <= 100 and not re.search(r"[.:;,!?]$", text))


def has_text(line: str) -> bool:
    return bool(re.search(r"\w", line))  # skip divider lines like "-----"


def context(lines: list[str], index: int) -> tuple[str, str | None]:
    """The (heading line, subheading) a line falls under."""
    sub = None
    for line in reversed(lines[: index + 1]):
        if is_heading(line):
            return line, sub
        if sub is None and is_subheading(line):
            sub = strip_links(line)
    return "Top of page", sub


def name_of(line: str, heading: str, sub: str | None) -> str:
    """A short name for the item a line describes, e.g. "Alameda and Aragon Analysis [Quick-Build]"."""
    text = strip_links(strip_marker(line))
    prefix = re.match(r"([^:]{3,80}):\s", text)
    return prefix.group(1) if prefix else (sub or heading)


def trim(words: list[str], keep_end: bool) -> tuple[str, bool]:
    """Shorten an unchanged run, always keeping its opening words so the line is recognizable."""
    if len(words) <= 2 * CONTEXT_WORDS:
        return " ".join(words), False
    tail = words[-CONTEXT_WORDS:] if keep_end else []
    return " ".join(words[:CONTEXT_WORDS] + ["…"] + tail), True


def shared_ends(x: str, y: str) -> tuple[int, int]:
    """Lengths of the common prefix and suffix of x and y, backed off to word boundaries."""
    def mid_word(s: str, p: int) -> bool:
        return 0 < p < len(s) and s[p - 1].isalnum() and s[p].isalnum()

    p = len(os.path.commonprefix([x, y]))
    while p and (mid_word(x, p) or mid_word(y, p)):
        p -= 1
    s = min(len(os.path.commonprefix([x[p:][::-1], y[p:][::-1]])), len(x) - p, len(y) - p)
    while s and (mid_word(x, len(x) - s) or mid_word(y, len(y) - s)):
        s -= 1
    return p, s


def words(text: str) -> list[str]:
    """Split on whitespace, keeping each Markdown link whole so trimming can't break it."""
    return re.findall(r"\[[^\]]*\]\([^)]*\)\S*|\S+", text)


def inline_diff(old: str, new: str) -> tuple[str, bool]:
    """Mark word-level edits; returns the marked text and whether anything was shortened."""
    a, b = words(old), words(new)
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    parts, trimmed = [], False
    for n, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            text, cut = trim(a[i1:i2], keep_end=n < len(ops) - 1)
            parts.append(text)
            trimmed |= cut
            continue
        x, y = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        p, s = shared_ends(x, y) if x and y else (0, 0)
        part = x[:p]
        if x[p : len(x) - s].strip():
            part += f"<del>{x[p:len(x) - s]}</del>"
        if y[p : len(y) - s].strip():
            part += f"<b>{y[p:len(y) - s]}</b>"
        parts.append(part + x[len(x) - s :])
    return " ".join(p for p in parts if p), trimmed


def pair_lines(old: list[str], new: list[str]):
    """Yield (old_pos, new_pos) pairs, matching similar lines in order; None if unmatched."""
    j = 0
    for i, line in enumerate(old):
        match = next(
            (k for k in range(j, len(new))
             if difflib.SequenceMatcher(None, line, new[k]).ratio() >= SIMILAR),
            None,
        )
        if match is None:
            yield i, None
            continue
        for k in range(j, match):
            yield None, k
        yield i, match
        j = match + 1
    for k in range(j, len(new)):
        yield None, k



class Summary:
    def __init__(self, old_text: str, new_text: str):
        esc = lambda t: t.replace("<", "&lt;").splitlines()
        self.old, self.new = esc(old_text), esc(new_text)
        self.groups: dict[tuple[str, str | None], list[str]] = {}
        self.titles: list[str] = []
        self.full: list[tuple[str, str, str]] = []  # (name, before, after) for shortened edits
        self.counts = {"edited": 0, "added": 0, "removed": 0}

        ops = difflib.SequenceMatcher(None, self.old, self.new, autojunk=False).get_opcodes()
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal":
                continue
            old_idx = [i for i in range(i1, i2) if has_text(self.old[i])]
            new_idx = [j for j in range(j1, j2) if has_text(self.new[j])]
            old_block = [self.old[i] for i in old_idx]
            new_block = [self.new[j] for j in new_idx]
            for a, b in pair_lines(old_block, new_block):
                self.add(None if a is None else old_idx[a], None if b is None else new_idx[b])

    def add(self, i: int | None, j: int | None) -> None:
        a = self.old[i] if i is not None else None
        b = self.new[j] if j is not None else None
        line, index, lines = (b, j, self.new) if b is not None else (a, i, self.old)
        if is_subheading(line):  # file a changed subheading under what precedes it, not itself
            index -= 1
        heading_line, sub = context(lines, index)
        heading = strip_marker(heading_line)
        label = " heading" if is_heading(line) or is_subheading(line) else ""
        if a and b:
            text, trimmed = inline_diff(strip_marker(a), strip_marker(b))
            item = f"<b>Changed{label}:</b> {text}"
            self.counts["edited"] += 1
            if trimmed:
                self.full.append((name_of(b, heading, sub), strip_marker(a), strip_marker(b)))
        elif b:
            item = f"<b>Added{label}:</b> {strip_marker(b)}"
            self.counts["added"] += 1
        else:
            item = f"<b>Removed{label}:</b> <del>{strip_marker(a)}</del>"
            self.counts["removed"] += 1
        self.groups.setdefault((heading, sub), []).append(item)

        level = len(re.match(r"#*", heading_line).group())
        self.titles.append(sub if level >= 4 and sub else heading)  # "#### Next Steps" is too generic

    def title(self) -> str:
        names = list(dict.fromkeys(self.titles))
        title = "; ".join(names)
        for n in range(len(names), 0, -1):
            more = f" (+{len(names) - n} more)" if n < len(names) else ""
            title = "; ".join(names[:n]) + more
            if len(title) <= MAX_TITLE:
                break
        return title

    def body(self, details: bool = True) -> str:
        if not self.groups:
            return "Only formatting changed (no text was added or removed).\n"
        n = len({heading for heading, _ in self.groups})
        stats = [f"{v} line{'s' * (v != 1)} {k}" for k, v in self.counts.items() if v]
        out = [f"**{n} section{'s' * (n != 1)} changed** · " + " · ".join(stats), ""]

        last = None
        for (heading, sub), items in self.groups.items():
            if heading != last:
                out += [f"### {heading}", ""]
                last = heading
            if sub and sub != heading:
                out += [f"*{sub}*", ""]
            out += [f"- {item}" for item in items] + [""]

        if details and self.full:
            out += ["<details><summary>Full before/after text of shortened edits</summary>", ""]
            for name, before, after in self.full:
                out += [f"- <i>{name}</i>", f"  - Before: {before}", f"  - After: {after}"]
            out += ["", "</details>", ""]

        text = "\n".join(out)
        if len(text) > MAX_BODY and details:
            return self.body(details=False)
        return text[:MAX_BODY]


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f_old, open(sys.argv[2], encoding="utf-8") as f_new:
        summary = Summary(f_old.read(), f_new.read())
    print(summary.title() if "--title" in sys.argv[3:] else summary.body())
