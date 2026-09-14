# -*- coding: utf-8 -*-
"""
Склонение должностей в дательный падеж: «Генеральный директор» -> «Генеральному директору».

Логика: склоняется только «вершина» должности — идущие подряд прилагательные
плюс первое существительное. Всё, что дальше (родительный падеж, предлоги,
названия компаний), остаётся без изменений:

    Начальник отдела продаж      -> Начальнику отдела продаж
    Директор по развитию         -> Директору по развитию
    Заместитель главного врача   -> Заместителю главного врача
"""

from dataclasses import dataclass, asdict
import re

SPACE_RE = re.compile(r"[\s\u00a0\u202f]+")
CYR_RE = re.compile(r"^[а-яёА-ЯЁ\-']+$")

# должности, которые целиком не склоняются (дальше идёт родительный падеж)
FROZEN_STARTS = ("и.о.", "и.о", "вр.и.о.", "врио", "исполняющий")

# служебные слова — на них склонение останавливается
STOPWORDS = {"по", "при", "в", "во", "на", "с", "со", "для", "и", "или",
             "от", "об", "о", "к", "у", "за", "над", "под"}

ADJ_ENDINGS = ("ый", "ий", "ой", "ая", "яя", "ое", "ее")

# окончания косвенных падежей: такое слово — зависимое, его не трогаем
# («заведующий отделением», «начальник отдела»)
OBLIQUE_ENDINGS = ("ом", "ем", "ём", "ами", "ями", "ах", "ях", "ою",
                   "ого", "его", "ому", "ему", "ыми", "ими", "ую", "юю",
                   "ых", "их", "ов", "ев", "ей")
# именительный падеж, похожий на косвенный
NOM_EXCEPTIONS = {"агроном", "астроном", "гастроном", "эконом", "лаборант",
                  "консультант", "ассистент"}
HUSHING = "жшчщц"

# аббревиатуры, которые остаются заглавными при исправлении регистра
KNOWN_ABBR = {"ооо", "оао", "зао", "пао", "ао", "ип", "нко", "ано", "гбу", "мбу",
              "фгуп", "гуп", "муп", "тсж", "снт", "рф", "ит", "ип", "сро", "чоу",
              "мку", "гку", "фку", "нуз", "цод", "сб", "hr", "it"}


@dataclass
class PositionResult:
    original: str
    dative: str
    comment: str

    def as_dict(self):
        return asdict(self)


# ------------------------------------------------------------------ утилиты

def _clean(text: str) -> str:
    return SPACE_RE.sub(" ", str(text or "")).strip()


ORG_FORMS = {"ооо", "оао", "зао", "пао", "ао", "ип", "нко", "ано", "гбу", "мбу",
             "фгуп", "гуп", "муп", "чоу", "мку", "гку", "фку", "тсж", "снт"}


def fix_position_case(text: str) -> str:
    """Первая буква — заглавная, остальное — строчное.

    Не трогаем: аббревиатуры (ООО, ПТО, HR), слова в кавычках и название
    организации сразу после правовой формы («ООО Ромашка»).
    """
    tokens = text.split(" ")
    out = []
    keep_next = False
    for idx, t in enumerate(tokens):
        core = t.strip(".,;:()«»\"'")
        low = core.lower()
        in_quotes = any(q in t for q in "«»\"'")

        if keep_next or in_quotes or not core:
            out.append(t)
            keep_next = low in ORG_FORMS
            continue

        if low in KNOWN_ABBR or (core.isupper() and len(core) <= 5) or not CYR_RE.match(core):
            out.append(t)                       # ООО, ПТО, HR, IT
            keep_next = low in ORG_FORMS
            continue

        low_t = t.lower()
        out.append(low_t[:1].upper() + low_t[1:] if idx == 0 else low_t)
        keep_next = False

    res = " ".join(out)
    return res[:1].upper() + res[1:] if res else res


def _split_tail(token: str):
    """Отделяет знаки препинания в конце слова."""
    m = re.match(r"^(.*?)([\.,;:()«»\"']*)$", token, flags=re.S)
    return m.group(1), m.group(2)


def _is_oblique(word: str) -> bool:
    low = word.lower()
    if low in NOM_EXCEPTIONS:
        return False
    return low.endswith(OBLIQUE_ENDINGS)


def _is_declinable(word: str) -> bool:
    if not word or len(word) < 3:
        return False
    if "-" in word:                       # HR-директор, инженер-технолог
        return any(_is_declinable(p) for p in word.split("-"))
    if not CYR_RE.match(word):
        return False
    if word.lower() in STOPWORDS:
        return False
    if word.isupper():          # ООО, РФ, ИТ
        return False
    return True


def _is_adj(word: str) -> bool:
    low = word.lower()
    return low.endswith(ADJ_ENDINGS) and len(low) > 4


def _keep_case(src: str, new: str) -> str:
    return new[:1].upper() + new[1:] if src[:1].isupper() else new


# ------------------------------------------------------------------ правила

def decline_adjective(word: str) -> str:
    low = word.lower()
    stem, end = low[:-2], low[-2:]
    if end in ("ый", "ой"):
        res = stem + "ому"
    elif end == "ий":
        res = stem + ("ому" if stem[-1:] in "кгх" else "ему")
    elif end == "ая":
        res = stem + ("ей" if stem[-1:] in HUSHING else "ой")
    elif end == "яя":
        res = stem + "ей"
    elif end == "ое":
        res = stem + "ому"
    elif end == "ее":
        res = stem + ("ому" if stem[-1:] in "кгх" else "ему")
    else:
        return word
    return _keep_case(word, res)


def decline_noun(word: str) -> str:
    # составные: инженер-технолог -> инженеру-технологу, ИТ-директор -> ИТ-директору
    if "-" in word:
        parts = word.split("-")
        return "-".join(decline_noun(p) if _is_declinable(p) else p for p in parts)

    low = word.lower()

    if low.endswith("ия"):                       # бухгалтерия -> бухгалтерии
        res = low[:-1] + "и"
    elif low.endswith("ие"):                     # подразделение -> подразделению
        res = low[:-1] + "ю"
    elif low.endswith(("а", "я")):               # глава -> главе, судья -> судье
        res = low[:-1] + "е"
    elif low.endswith("о"):                      # лицо -> лицу
        res = low[:-1] + "у"
    elif low.endswith("ь"):                      # руководитель -> руководителю
        res = low[:-1] + "ю"
    elif low.endswith("й"):                      # ... -> ...ю
        res = low[:-1] + "ю"
    elif low.endswith("ец") and len(low) > 4:    # продавец -> продавцу
        res = low[:-2] + "цу"
    elif low.endswith(("е", "и", "у", "ю", "ы", "э")):
        return word                              # атташе, кадры — не склоняем
    else:                                        # директор -> директору
        res = low + "у"

    return _keep_case(word, res)


# ------------------------------------------------------------------ основное

def decline_position(text: str, fix_case: bool = True, speller=None) -> PositionResult:
    original = _clean(text)
    if not original:
        return PositionResult("", "", "пустая строка")

    work = original
    spell_notes = []
    if speller is not None:
        work, spell_notes = speller.correct(work)
    work = fix_position_case(work) if fix_case else work
    low_first = work.split(" ")[0].lower()

    if low_first.startswith(FROZEN_STARTS):
        return PositionResult(original, work,
                              "; ".join(spell_notes + ["должность не склоняется (и.о. / врио)"]))

    tokens = work.split(" ")
    out = list(tokens)
    comment = ""
    i = 0
    declined = False

    # аббревиатуры в начале («Зам. директора») пропускаем, но не склоняем дальше
    if tokens and "." in tokens[0] and len(tokens[0]) <= 5:
        return PositionResult(original, work,
                              "; ".join(spell_notes + ["сокращение в начале — строка оставлена как есть"]))

    # прилагательные
    while i < len(tokens):
        core, tail = _split_tail(tokens[i])
        if _is_declinable(core) and _is_adj(core):
            out[i] = decline_adjective(core) + tail
            declined = True
            i += 1
        else:
            break

    # первое существительное = вершина
    if i < len(tokens):
        core, tail = _split_tail(tokens[i])
        if _is_declinable(core) and not _is_oblique(core):
            out[i] = decline_noun(core) + tail
            declined = True

    if not declined:
        comment = "не удалось определить склоняемое слово — оставлено как есть"

    notes = spell_notes + ([comment] if comment else [])
    return PositionResult(original, " ".join(out), "; ".join(notes))


def decline_positions(rows, fix_case: bool = True, speller=None):
    return [decline_position(r, fix_case=fix_case, speller=speller) for r in rows]
