# -*- coding: utf-8 -*-
"""
Разбивка ФИО: фамилия в дательном падеже + инициалы, имя-отчество, окончание
обращения ("Уважаемый/Уважаемая").

Порт VBA-макроса SplitFIO2 на Python.

Два режима:
  * strict=True  — поведение 1-в-1 с исходным макросом;
  * strict=False — улучшенные правила (по умолчанию): см. README.
"""

from dataclasses import dataclass, asdict
from typing import List, Optional
import re

# --- окончания отчеств -------------------------------------------------------

MALE_SUFFIXES = ("вич", "тич", "мич", "ьич", "лич", "нич", "рич", "ич",
                 "улы", "уулу", "оглы", "оглу", "угли")
FEMALE_SUFFIXES = ("вна", "чна", "шна", "кызы", "гызы", "кизи", "къызы")

# фамилии, которые не склоняются вовсе (на гласную кроме а/я, на -ых/-их)
INDECLINABLE_ENDINGS = ("о", "е", "ё", "и", "у", "ю", "ы", "э", "их", "ых")

# «адъективные» женские фамилии -> дательный на -ой
FEM_ADJ_ENDINGS = ("ова", "ева", "ёва", "ина", "ына", "ая", "яя")

SPACE_RE = re.compile(r"[\s\u00a0\u202f]+")


@dataclass
class FioResult:
    original: str          # A — исходное ФИО
    dative_initials: str   # B — «Иванову И.И.»
    name_patronymic: str   # C — «Иван Иванович»
    suffix: str            # D — «ый» / «ая»
    greeting: str          # «Уважаемый Иван Иванович»
    surname: str
    first_name: str
    patronymic: str
    gender: str            # male / female / unknown
    status: str            # ok / warning / error
    comment: str

    def as_dict(self):
        return asdict(self)


# --- вспомогательное ---------------------------------------------------------

def _clean(text: str) -> str:
    text = SPACE_RE.sub(" ", str(text or "")).strip()
    return text


def _cap(word: str) -> str:
    """ИВАНОВ / иванов -> Иванов; работает и для «Ван Дер Бек», и для дефисных."""
    if not word:
        return word
    parts = re.split(r"([-'’ ])", word.lower())
    return "".join(p if p in "-'’ " else (p[:1].upper() + p[1:]) for p in parts)


def detect_gender(patronymic: str) -> str:
    p = (patronymic or "").lower()
    if p.endswith(FEMALE_SUFFIXES):
        return "female"
    if p.endswith(MALE_SUFFIXES):
        return "male"
    return "unknown"


# --- склонение фамилии -------------------------------------------------------

def decline_surname_strict(fam: str, gender: str) -> str:
    """Дословная логика макроса."""
    if fam[-1:].lower() in ("о", "х", "и"):
        return fam
    low = fam.lower()
    if gender == "female":
        if low.endswith("ая"):
            return fam[:-2] + "ой"
        if low.endswith("а"):
            return fam[:-1] + "ой"
        return fam
    if gender == "male":
        if low.endswith("ь"):
            return fam[:-1] + "ю"
        if low.endswith("ок"):
            return fam[:-2] + "ку"
        if low.endswith("ец"):
            return fam[:-2] + "цу"
        if low.endswith(("ий", "ый")):
            return fam[:-2] + "ому"
        if low.endswith("й"):
            return fam[:-1] + "ю"
        if not low.endswith("а"):
            return fam + "у"
    return fam


def decline_surname(fam: str, gender: str):
    """Улучшенные правила. Возвращает (форма_в_дательном, комментарий)."""
    if not fam:
        return fam, ""

    # двойная фамилия через дефис — склоняем обе части
    if "-" in fam:
        parts = fam.split("-")
        out, notes = [], []
        for part in parts:
            d, n = decline_surname(part, gender)
            out.append(d)
            if n:
                notes.append(n)
        return "-".join(out), "; ".join(dict.fromkeys(notes))

    low = fam.lower()

    if low.endswith(INDECLINABLE_ENDINGS):
        return fam, ""

    if gender == "female":
        if low.endswith(FEM_ADJ_ENDINGS):
            if low.endswith(("ая", "яя")):
                return fam[:-2] + "ой", ""
            return fam[:-1] + "ой", ""
        if low.endswith("ия"):
            return fam[:-1] + "и", ""
        if low.endswith(("а", "я")):
            # несклоняемый тип («Сорока» -> «Сороке»)
            return fam[:-1] + ("е" if low.endswith("а") else "е"), \
                "женская фамилия не на -ова/-ина: проверьте падеж"
        # на согласную, -й, -ь женские фамилии не склоняются
        return fam, ""

    if gender == "male":
        if low.endswith(("ой", "ий", "ый")) and len(fam) >= 5:
            # прилагательный тип: Толстой -> Толстому, Белый -> Белому
            return fam[:-2] + "ому", ""
        if low.endswith("ь"):
            return fam[:-1] + "ю", ""
        if low.endswith("й"):
            return fam[:-1] + "ю", ""
        if low.endswith("ия"):
            return fam[:-1] + "и", ""
        if low.endswith(("а", "я")):
            return fam[:-1] + "е", "мужская фамилия на -а/-я: проверьте падеж"
        if low.endswith("ок") and len(fam) > 5:
            return fam[:-2] + "ку", "беглая гласная: возможно «" + fam + "у»"
        if low.endswith("ец") and len(fam) > 5:
            return fam[:-2] + "цу", "беглая гласная: возможно «" + fam + "у»"
        return fam + "у", ""

    return fam, "не определён пол по отчеству — фамилия не склонялась"


# --- основная функция --------------------------------------------------------

def process_fio(raw: str, strict: bool = False, fix_case: bool = True,
                spell: bool = False) -> FioResult:
    original = _clean(raw)

    empty = FioResult(original, "", "", "", "", "", "", "", "unknown", "error", "")
    if not original:
        empty.comment = "пустая строка"
        return empty

    parts = original.split(" ")
    comment = ""

    if len(parts) == 1:
        empty.comment = "только одно слово — не похоже на ФИО"
        return empty

    if len(parts) == 2:
        if strict:
            empty.comment = "пропущено макросом: нет отчества"
            return empty
        fam, name, otch = parts[0], parts[1], ""
        comment = "нет отчества"
    elif len(parts) == 3:
        fam, name, otch = parts
    else:
        # «Иванов Иван Иванович оглы», двойные фамилии через пробел и т.п.
        if strict:
            empty.comment = "пропущено макросом: больше трёх слов"
            return empty
        if parts[-1].lower() in ("оглы", "оглу", "кызы", "гызы", "улы", "уулу"):
            fam, name, otch = parts[0], parts[1], " ".join(parts[2:])
        else:
            # «Каблахов Ауэс Хан Мухамедович» -> фамилия / составное имя / отчество
            fam, name, otch = parts[0], " ".join(parts[1:-1]), parts[-1]
        comment = "больше трёх слов — проверьте разбивку"

    if fix_case:
        fam, name, otch = _cap(fam), _cap(name), _cap(otch)

    if spell:
        from spell_utils import correct_name, correct_patronymic
        new_name, ch1 = correct_name(name)
        new_otch, ch2 = correct_patronymic(otch)
        fixes = []
        if ch1:
            fixes.append(f"{name} → {new_name}")
            name = new_name
        if ch2:
            fixes.append(f"{otch} → {new_otch}")
            otch = new_otch
        if fixes:
            comment = "; ".join(x for x in (comment, "; ".join(fixes)) if x)

    gender = detect_gender(otch)

    if strict:
        if gender == "unknown":
            empty.comment = "пропущено макросом: нестандартное отчество"
            return empty
        fam_dat = decline_surname_strict(fam, gender)
        note = ""
    else:
        fam_dat, note = decline_surname(fam, gender)

    if gender == "male":
        suffix = "ый"
    elif gender == "female":
        suffix = "ая"
    else:
        suffix = ""
        if "пол" not in note:
            note = (note + "; " if note else "") + "пол не определён по отчеству"

    initials = (name[:1] + "." if name else "") + (otch[:1] + "." if otch else "")
    dative_initials = (fam_dat + " " + initials).strip()
    name_patronymic = (name + " " + otch).strip()
    greeting = ("Уважаем" + suffix + " " + name_patronymic).strip() if suffix else ""

    comment = "; ".join(x for x in (comment, note) if x)
    status = "ok" if not comment else "warning"

    return FioResult(
        original=original,
        dative_initials=dative_initials,
        name_patronymic=name_patronymic,
        suffix=suffix,
        greeting=greeting,
        surname=fam,
        first_name=name,
        patronymic=otch,
        gender=gender,
        status=status,
        comment=comment,
    )


def process_many(rows: List[str], strict: bool = False, fix_case: bool = True,
                 spell: bool = False) -> List[FioResult]:
    return [process_fio(r, strict=strict, fix_case=fix_case, spell=spell) for r in rows]


GENDER_RU = {"male": "муж.", "female": "жен.", "unknown": "не определён"}
