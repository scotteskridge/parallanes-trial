"""Blank out comments so pattern rules don't fire on commented-out code.

Deliberately simple (decision 23): line comments by file type plus block comments, and no string
parsing. A comment marker inside a string ends checking for that line, so a rule can miss a
violation there, but stripping only ever removes text (a removed comment leaves a space, so tokens
on either side can't join), so it can't cause a false alarm. Line numbers are
preserved: the result has one entry per input line, split the way editors number lines.
"""

_HASH = (("#",), ())
_C_LIKE = (("//",), (("/*", "*/"),))
_DASH = (("--",), ())
_MARKUP = ((), (("<!--", "-->"),))

_STYLES = {
    **dict.fromkeys(
        [
            ".py",
            ".sh",
            ".bash",
            ".zsh",
            ".rb",
            ".pl",
            ".r",
            ".ps1",
            ".psm1",
            ".toml",
            ".yaml",
            ".yml",
            ".cfg",
            ".ini",
            ".conf",
            ".mk",
            ".cmake",
            ".tf",
            ".nim",
            ".ex",
            ".exs",
        ],
        _HASH,
    ),
    **dict.fromkeys(
        [
            ".c",
            ".h",
            ".cc",
            ".cpp",
            ".hpp",
            ".cs",
            ".java",
            ".kt",
            ".kts",
            ".scala",
            ".go",
            ".rs",
            ".swift",
            ".js",
            ".jsx",
            ".mjs",
            ".cjs",
            ".ts",
            ".tsx",
            ".dart",
            ".php",
            ".css",
            ".scss",
            ".less",
            ".gradle",
            ".groovy",
            ".proto",
            ".shader",
            ".hlsl",
            ".glsl",
        ],
        _C_LIKE,
    ),
    **dict.fromkeys([".sql", ".lua", ".hs", ".elm"], _DASH),
    **dict.fromkeys([".md", ".html", ".htm", ".xml", ".svg", ".vue", ".xaml"], _MARKUP),
}


def split_lines(text: str) -> list[str]:
    """Lines as an editor numbers them. str.splitlines() also breaks on form feeds and other
    separators, which would shift every later line number."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def strip_comments(text: str, suffix: str) -> list[str]:
    """Lines of text with comments removed, for a file with this extension (e.g. ".py")."""
    style = _STYLES.get(suffix.lower())
    lines = split_lines(text)
    if style is None:
        return lines
    line_markers, blocks = style

    out = []
    block_end = None  # set while inside a block comment
    for line in lines:
        kept = []
        i = 0
        while i < len(line):
            if block_end is not None:
                end = line.find(block_end, i)
                if end == -1:
                    break
                i = end + len(block_end)
                block_end = None
                continue
            # The earliest marker on the rest of the line decides what happens next.
            nearest = None
            for marker in line_markers:
                at = line.find(marker, i)
                if at != -1 and (nearest is None or at < nearest[0]):
                    nearest = (at, marker, None)
            for start, end in blocks:
                at = line.find(start, i)
                if at != -1 and (nearest is None or at < nearest[0]):
                    nearest = (at, start, end)
            if nearest is None:
                kept.append(line[i:])
                break
            at, marker, end = nearest
            kept.append(line[i:at])
            if end is None:
                break  # line comment: the rest of the line is gone
            block_end = end
            i = at + len(marker)
        # A space where a comment was, so `foo/* c */bar` can't become a new token `foobar`.
        out.append(" ".join(kept))
    return out
