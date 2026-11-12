"""Link a Covenant worker to an Astropods blueprint or deployment by name."""


def compact_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def names_match(left: str, right: str) -> bool:
    """True when the names are equal, or a name of at least 4 letters sits inside the other.

    "Lipi" matches a deployment called "lipi-translator". "AI" does not match everything.
    """

    a, b = compact_name(left), compact_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and short in long
