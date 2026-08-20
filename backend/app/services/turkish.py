"""Turkish I/İ helpers. English str.upper() turns i into I, which is the wrong letter."""

from __future__ import annotations


def lower_tr(value: str) -> str:
    return value.replace("İ", "i").replace("I", "ı").lower()


def upper_tr(value: str) -> str:
    return value.replace("i", "İ").replace("ı", "I").upper()


def title_word(word: str) -> str:
    if len(word) > 1 and word.isupper():
        word = word[0] + word[1:].lower()
    first, rest = word[:1], word[1:]
    if first in "iİ":
        return "İ" + lower_tr(rest)
    if first == "ı":
        return "I" + lower_tr(rest)
    if first == "I":
        return ("İ" if _ascii_i_should_be_dotted(rest) else "I") + lower_tr(rest)
    return upper_tr(first) + lower_tr(rest)


def _ascii_i_should_be_dotted(rest: str) -> bool:
    """True when leading ASCII I is an English-capitalized i, not Turkish I (ı).

    Keep Işık, Irmak, Ilık, ısı, ıspanak. Fix İçişleri, İstanbul, işlem, iki.
    Only used when the letter is already I and the rest is lowercase-ish.
    """
    if not rest:
        return False
    first = rest[0]
    second = rest[1:2]
    if first != first.lower() or not first.isalpha():
        return False
    folded = lower_tr(first)
    nxt = lower_tr(second) if second else ""
    if folded in "çğbcdefhkmptvyz":
        return True
    if folded == "l":
        return nxt != "ı"
    if folded == "n":
        return nxt != "ı"
    if folded == "s":
        return nxt not in "ıp"
    if folded == "r":
        return not lower_tr(rest).startswith("rm")
    if folded == "ş":
        return nxt != "ı"
    return False


def fix_sentence_i(text: str) -> str:
    """Fix sentence-initial i/I using Turkish rules. Never turn a real I (ı) into İ."""
    if not text:
        return text
    out: list[str] = []
    start = True
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if start and char == "i":
            out.append("İ")
            start = False
            index += 1
            continue
        if start and char == "ı":
            out.append("I")
            start = False
            index += 1
            continue
        if start and char == "I" and _ascii_i_should_be_dotted(text[index + 1 :]):
            out.append("İ")
            start = False
            index += 1
            continue
        out.append(char)
        if char in ".!?…\n\r":
            start = True
        elif start and char in " \t\"')]:":
            pass
        elif not char.isspace():
            start = False
        index += 1
    return "".join(out)
