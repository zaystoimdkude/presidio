"""
Custom Presidio recognizers for:
  - Mongolian National Registration Number (Монгол регистерийн дугаар)
  - IBAN (International Bank Account Number)

Монгол регистерийн дугаарын формат:
  2 том кирилл үсэг + 8 тоо
  Жишээ: УП04230973, АА91234567, ӨН12345678

IBAN формат (ISO 13616):
  2 латин үсэг (улсын код) + 2 тоо (шалгах тоо) + 4-30 үсэг/тоо
  Жишээ: MN12GOLO1234567890, GB29NWBK60161331926819
"""

import re
from typing import List

from presidio_analyzer import Pattern, PatternRecognizer


# ── Монгол регистерийн дугаар ────────────────────────────────────────────────

MONGOLIAN_ID_PATTERNS = [
    Pattern(
        name="Mongolian Registration Number (2 Cyrillic + 8 digits)",
        # Unicode ranges:
        #   U+0410-U+042F = А-Я (uppercase Cyrillic)
        #   U+04E8 = Ө  U+04AE = Ү  (Mongolian special uppercase)
        #   U+0430-U+044F = а-я (lowercase)
        #   U+04E9 = ө  U+04AF = ү  (Mongolian special lowercase)
        # Examples: УП04230973, АА91234567, ӨН00112233
        regex=r"\b[\u0410-\u042F\u04E8\u04AE\u0430-\u044F\u04E9\u04AF]{2}\d{8}\b",
        score=0.85,
    )
]

MONGOLIAN_ID_CONTEXT = [
    # Монгол
    "регистер", "регистрийн", "регистерийн", "РД", "иргэний",
    "үнэмлэх", "паспорт", "дугаар", "дугаарт",
    # English
    "registration", "national id", "id number", "citizen", "passport",
]


def create_mongolian_id_recognizer(supported_language: str = "en") -> PatternRecognizer:
    """
    Монгол иргэний регистерийн дугаарыг таних PatternRecognizer.

    Regex: [А-ЯӨҮа-яөү]{2}\\d{8}
    Жишээ: УП04230973
    """
    return PatternRecognizer(
        supported_entity="MN_NATIONAL_ID",
        name="MongolianNationalIDRecognizer",
        patterns=MONGOLIAN_ID_PATTERNS,
        context=MONGOLIAN_ID_CONTEXT,
        supported_language=supported_language,
    )


# ── IBAN ────────────────────────────────────────────────────────────────────────

# ISO 13616 IBAN: CC##BBBB...  (2 letter country code, 2 check digits, BBAN)
# Mongolian bank IBAN example: MN12GOLO1234567890
IBAN_PATTERNS = [
    Pattern(
        name="IBAN (full standard)",
        # CC##: 2 letters + 2 digits, then 4-30 alphanumeric (BBAN)
        # Spaces are sometimes inserted every 4 chars; we handle both spaced and unspaced
        regex=(
            r"\b"
            r"[A-Z]{2}"           # Country code (e.g. MN, GB, DE, US)
            r"\d{2}"              # Check digits
            r"[A-Z0-9]{4,30}"     # BBAN (Basic Bank Account Number)
            r"\b"
        ),
        score=0.5,
    ),
    Pattern(
        name="IBAN (spaced format)",
        # Grouped in 4s: GB29 NWBK 6016 1331 9268 19
        regex=(
            r"\b"
            r"[A-Z]{2}\d{2}"                 # CC##
            r"(?:\s[A-Z0-9]{4}){1,7}"        # groups of 4
            r"(?:\s[A-Z0-9]{1,4})?"          # last partial group
            r"\b"
        ),
        score=0.6,
    ),
]

IBAN_CONTEXT = [
    # English
    "iban", "IBAN", "bank account", "account number", "bic", "swift",
    "transfer", "wire", "international",
    # Монгол
    "данс", "дансны", "дансанд", "банкны", "шилжүүлэг",
    "олон улс", "гадаад данс",
]


def create_iban_recognizer(supported_language: str = "en") -> PatternRecognizer:
    """
    IBAN дугаарыг таних PatternRecognizer.

    ISO 13616 стандарт: 2 том үсэг (улс) + 2 тоо + 4-30 үсэг/тоо
    Жишээ: MN12GOLO1234567890, GB29NWBK60161331926819
    """
    return PatternRecognizer(
        supported_entity="IBAN_CODE",
        name="IBANRecognizerCustom",
        patterns=IBAN_PATTERNS,
        context=IBAN_CONTEXT,
        supported_language=supported_language,
    )


# ── Хялбар бүртгүүлэх функц ────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = ["en", "de", "es", "fr", "it", "pt", "nl"]


def get_all_custom_recognizers() -> List[PatternRecognizer]:
    """
    Бүх custom recognizer-ийн жагсаалт буцаана.
    Олон хэлд ажиллахын тулд хэл тус бүрт нэг instance үүсгэнэ.
    """
    recognizers = []
    for lang in SUPPORTED_LANGUAGES:
        recognizers.append(create_mongolian_id_recognizer(lang))
        recognizers.append(create_iban_recognizer(lang))
    return recognizers
