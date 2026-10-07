"""Fill {{placeholders}} in templates.

Deliberately tiny instead of a template engine: templates are prose, and the only job is safe
substitution. Anything a template asks for must be in the registry, and every registered name it
uses must have a value, so a typo fails at install time instead of shipping as literal braces.
Write \\{{name}} to keep literal braces in the output.
"""

import re

_PLACEHOLDER = re.compile(r"(\\?)\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class TemplateError(ValueError):
    """A template asked for a placeholder that is unknown or has no value."""


def placeholders_in(text: str) -> set[str]:
    """Names of the placeholders a template uses, ignoring escaped ones."""
    return {name for escape, name in _PLACEHOLDER.findall(text) if not escape}


def render(text: str, values: dict[str, str], registry: set[str]) -> str:
    """Return text with every {{name}} replaced by values[name].

    Raises TemplateError naming every unknown placeholder (not in registry) and every
    registered one without a value, so all problems in a template show up in one run.
    """
    used = placeholders_in(text)
    unknown = sorted(used - registry)
    missing = sorted((used & registry) - values.keys())
    problems = [f"unknown placeholder {{{{{name}}}}}" for name in unknown]
    problems += [f"no value for {{{{{name}}}}}" for name in missing]
    if problems:
        raise TemplateError("; ".join(problems))

    def substitute(match: re.Match) -> str:
        escape, name = match.groups()
        if escape:
            return match.group(0)[1:]  # drop the backslash, keep the braces
        return str(values[name])

    # A function replacement inserts values literally: no backslash or group processing.
    return _PLACEHOLDER.sub(substitute, text)
