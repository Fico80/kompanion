import re


NUMBER_WORDS = {
    "null": 0, "zero": 0,
    "ein": 1, "eine": 1, "einer": 1, "einen": 1, "eins": 1, "one": 1,
    "zwei": 2, "two": 2,
    "drei": 3, "three": 3,
    "vier": 4, "four": 4,
    "fünf": 5, "funf": 5, "five": 5,
    "sechs": 6, "six": 6,
    "sieben": 7, "seven": 7,
    "acht": 8, "eight": 8,
    "neun": 9, "nine": 9,
    "zehn": 10, "ten": 10,
    "elf": 11, "eleven": 11,
    "zwölf": 12, "zwoelf": 12, "twelve": 12,
    "dreizehn": 13, "thirteen": 13,
    "vierzehn": 14, "fourteen": 14,
    "fünfzehn": 15, "funfzehn": 15, "fifteen": 15,
    "sechzehn": 16, "sixteen": 16,
    "siebzehn": 17, "seventeen": 17,
    "achtzehn": 18, "eighteen": 18,
    "neunzehn": 19, "nineteen": 19,
    "zwanzig": 20, "twenty": 20,
    "dreißig": 30, "dreissig": 30, "thirty": 30,
    "vierzig": 40, "forty": 40,
    "fünfzig": 50, "funfzig": 50, "fifty": 50,
    "sechzig": 60, "sixty": 60,
    "siebzig": 70, "seventy": 70,
    "achtzig": 80, "eighty": 80,
    "neunzig": 90, "ninety": 90,
    "hundert": 100, "one hundred": 100,
}

_DE_ONES = {
    "ein": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
    "funf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
}
_DE_TENS = {
    "zwanzig": 20, "dreißig": 30, "dreissig": 30, "vierzig": 40,
    "fünfzig": 50, "funfzig": 50, "sechzig": 60, "siebzig": 70,
    "achtzig": 80, "neunzig": 90,
}
for one_word, one_value in _DE_ONES.items():
    prefix = "ein" if one_value == 1 else one_word
    for ten_word, ten_value in _DE_TENS.items():
        NUMBER_WORDS.setdefault(f"{prefix}und{ten_word}", ten_value + one_value)

_EN_ONES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
for ten_word, ten_value in _EN_TENS.items():
    for one_word, one_value in _EN_ONES.items():
        NUMBER_WORDS.setdefault(f"{ten_word} {one_word}", ten_value + one_value)
        NUMBER_WORDS.setdefault(f"{ten_word}-{one_word}", ten_value + one_value)

NUMBER_PATTERN = r"\d+|" + "|".join(
    re.escape(k) for k in sorted(NUMBER_WORDS, key=len, reverse=True)
)


def parse_number(value: str) -> int:
    value = value.lower().strip()
    if value.isdigit():
        return int(value)
    return NUMBER_WORDS[value]
