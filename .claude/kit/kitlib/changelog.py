"""Compile changelog fragments (docs/changelog.d/*.md) into a release section of docs/CHANGELOG.md.

Each task branch writes its own fragment so parallel lanes never edit the same file (decision 13).
Fragments use Keep a Changelog headings; anything else is rejected before any file is touched.
"""

from dataclasses import dataclass
from pathlib import Path

CHANGELOG_REL = Path("docs") / "CHANGELOG.md"
FRAGMENTS_REL = Path("docs") / "changelog.d"
HEADINGS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
UNRELEASED = "## [Unreleased]"


class ChangelogError(Exception):
    """A fragment or the changelog can't be used; nothing has been written."""


@dataclass
class Release:
    section: str
    new_text: str
    fragments: list


def fragment_files(root: Path) -> list[Path]:
    """Fragment files in name order; README.md and _-prefixed files are documentation, not fragments."""
    folder = root / FRAGMENTS_REL
    if not folder.is_dir():
        return []
    return sorted(
        path for path in folder.glob("*.md") if path.name.lower() != "readme.md" and not path.name.startswith("_")
    )


def parse_fragment(path: Path) -> dict:
    """{heading: [entry lines]}; an entry is a bullet plus any indented continuation lines."""
    sections: dict = {}
    current = None
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if line.startswith("### "):
            heading = line[4:].strip()
            if heading not in HEADINGS:
                raise ChangelogError(
                    f"{path.name}:{number}: unknown heading {heading!r} (use one of {', '.join(HEADINGS)})"
                )
            current = sections.setdefault(heading, [])
        elif not line.strip():
            continue
        elif current is None:
            raise ChangelogError(f"{path.name}:{number}: text before the first ### heading")
        elif line.startswith(("- ", "* ")) or not current:
            current.append(line)
        else:
            current[-1] += "\n" + line  # continuation of the previous bullet
    return sections


def build(root: Path, version: str, date: str) -> Release:
    """Work out the new changelog text; raises ChangelogError without touching any file."""
    fragments = fragment_files(root)
    if not fragments:
        raise ChangelogError(f"no fragments in {FRAGMENTS_REL.as_posix()}/: nothing to release")
    changelog = root / CHANGELOG_REL
    if not changelog.is_file():
        raise ChangelogError(f"{CHANGELOG_REL.as_posix()} not found")
    text = changelog.read_text(encoding="utf-8-sig")
    if UNRELEASED not in text:
        raise ChangelogError(f"{CHANGELOG_REL.as_posix()} has no '{UNRELEASED}' heading to release under")

    merged = {heading: [] for heading in HEADINGS}
    for fragment in fragments:
        for heading, entries in parse_fragment(fragment).items():
            merged[heading].extend(entries)

    parts = [f"## [{version}] - {date}"]
    for heading in HEADINGS:
        if merged[heading]:
            parts.append(f"### {heading}\n" + "\n".join(merged[heading]) + "\n")
    section = "\n".join(parts) + "\n"

    before, after = text.split(UNRELEASED, 1)
    rest = after.lstrip("\n")
    pending = rest.split("\n## ", 1)[0] if not rest.startswith("## ") else ""
    if pending.strip():
        raise ChangelogError(
            f"{CHANGELOG_REL.as_posix()} has entries under '{UNRELEASED}'; "
            "move them into a fragment in docs/changelog.d/ so nothing is released out of order"
        )
    new_text = f"{before}{UNRELEASED}\n\n{section}" + (f"{rest}" if rest else "")
    return Release(section=section, new_text=new_text, fragments=fragments)


def apply(root: Path, release: Release) -> None:
    (root / CHANGELOG_REL).write_bytes(release.new_text.encode("utf-8"))
    for fragment in release.fragments:
        fragment.unlink()
