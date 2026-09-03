HIRAGANA = (0x3040, 0x309F)
KATAKANA = (0x30A0, 0x30FF)
CJK_IDEOGRAPH = (0x4E00, 0x9FFF)
LATIN_SUPPLEMENT_MAX = 0x024F


def _in_range(ch, rng):
    return rng[0] <= ord(ch) <= rng[1]


def looks_like_unwanted_chinese(text):
    if not text:
        return False
    has_kana = any(_in_range(c, HIRAGANA) or _in_range(c, KATAKANA) for c in text)
    has_cjk = any(_in_range(c, CJK_IDEOGRAPH) for c in text)
    has_latin = any(c.isalpha() and ord(c) <= LATIN_SUPPLEMENT_MAX for c in text)
    return has_cjk and not has_kana and not has_latin
