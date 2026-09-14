# -*- coding: utf-8 -*-
"""Разбивка ФИО и склонение должностей — Streamlit-приложение."""

import io
import re
import pandas as pd
import streamlit as st

from fio_utils import process_fio, process_many, GENDER_RU
from dolzhnost_utils import decline_position, decline_positions
from spell_utils import PositionSpeller

st.set_page_config(page_title="Разбивка ФИО", page_icon="👤", layout="wide")

NONE = "— не обрабатывать —"

COLS = {
    "original": "ФИО",
    "dative_initials": "Фамилия И.О. (дат.)",
    "name_patronymic": "Имя Отчество",
    "suffix": "Окончание",
    "greeting": "Обращение",
    "gender": "Пол",
    "comment": "Комментарий (ФИО)",
}
BASE_ORDER = ["original", "dative_initials", "name_patronymic", "suffix"]
EXTRA_ORDER = ["greeting", "gender", "comment"]

POS_HINTS = ("должн", "позиц", "post", "position", "статус")
FIO_HINTS = ("фио", "фамил", "имя", "name", "контакт", "руковод")


@st.cache_data(show_spinner=False)
def read_reference(data: bytes, name: str):
    if name.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "cp1251"):
            try:
                return pd.read_csv(io.BytesIO(data), encoding=enc, sep=None, engine="python")
            except UnicodeDecodeError:
                continue
        raise ValueError("не удалось определить кодировку")
    return pd.read_excel(io.BytesIO(data))


def guess_column(columns, hints, default=0):
    for i, c in enumerate(columns):
        low = str(c).lower()
        if any(h in low for h in hints):
            return i
    return default


# ---------------------------------------------------------------- настройки
with st.sidebar:
    st.header("Настройки")
    strict = st.toggle(
        "Режим «как в макросе»", value=False,
        help="Точное повторение старого Excel-макроса: строки без отчества, "
             "с нестандартным отчеством или длиннее трёх слов пропускаются.",
    )
    fix_case = st.toggle("Исправлять регистр", value=True,
                         help="ИВАНОВ → Иванов; должность — с заглавной буквы, "
                              "остальные слова строчными (аббревиатуры и названия в кавычках не трогаем).")
    spell = st.toggle("Исправлять опечатки", value=True,
                      help="Должности — по словарю; имена и отчества — по списку имён. "
                           "Фамилии не проверяются. Все правки видны в колонке «Комментарий».")
    show_extra = st.toggle("Показывать доп. колонки", value=True)

    st.divider()
    st.caption("**Свой справочник должностей** (необязательно)")
    ref_file = st.file_uploader("xlsx / csv с эталонными должностями",
                                type=["xlsx", "xlsm", "csv"], key="ref")
    ref_phrases = []
    if ref_file is not None:
        try:
            ref_df = read_reference(ref_file.getvalue(), ref_file.name)
            ref_col = st.selectbox("Колонка справочника", [str(c) for c in ref_df.columns])
            ref_phrases = [str(x) for x in ref_df[ref_col].dropna().unique()]
            st.success(f"Загружено эталонных должностей: {len(ref_phrases)}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Справочник не прочитан: {e}")

speller = PositionSpeller(ref_phrases) if spell else None


def fio_frame(results):
    order = BASE_ORDER + (EXTRA_ORDER if show_extra else [])
    rows = []
    for r in results:
        d = r.as_dict()
        d["gender"] = GENDER_RU.get(d["gender"], d["gender"])
        rows.append({COLS[k]: d[k] for k in order})
    return pd.DataFrame(rows)


def position_frame(results):
    rows = []
    for r in results:
        row = {"Должность": r.original, "Должность (дат.)": r.dative}
        if show_extra:
            row["Комментарий (должность)"] = r.comment
        rows.append(row)
    return pd.DataFrame(rows)


def combine(pos_res, fio_res):
    """Готовая строка «Кому»."""
    return [" ".join(x for x in (p.dative if p else "",
                                 f.dative_initials if f else "") if x).strip()
            for p, f in zip(pos_res, fio_res)]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Результат")
        ws = writer.sheets["Результат"]
        for i, col in enumerate(df.columns, start=1):
            width = max([len(str(col))] + [len(str(v)) for v in df[col].head(500)]) + 2
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(width, 50)
    return buf.getvalue()


def download_buttons(df: pd.DataFrame, stem: str):
    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ Скачать Excel", to_excel_bytes(df), f"{stem}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    c2.download_button(
        "⬇️ Скачать CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{stem}.csv",
        "text/csv", use_container_width=True,
    )


def show_stats(results):
    ok = sum(1 for r in results if r.status == "ok")
    warn = sum(1 for r in results if r.status == "warning")
    err = sum(1 for r in results if r.status == "error")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Всего строк", len(results))
    c2.metric("Без замечаний", ok)
    c3.metric("С замечаниями", warn)
    c4.metric("Не обработано", err)


# ---------------------------------------------------------------- интерфейс
st.title("👤 Разбивка ФИО и склонение должностей")
st.caption("Должность и ФИО в дательном падеже — по отдельности или обе колонки сразу.")

tab1, tab2, tab3 = st.tabs(["Одна запись", "Список строк", "Файл"])

# --- одна запись ------------------------------------------------------------
with tab1:
    c1, c2 = st.columns(2)
    pos = c1.text_input("Должность (им. падеж)", placeholder="Генеральный директор")
    fio = c2.text_input("ФИО полностью", placeholder="Иванов Иван Иванович")

    p = decline_position(pos, fix_case=fix_case, speller=speller) if pos.strip() else None
    r = process_fio(fio, strict=strict, fix_case=fix_case, spell=spell) if fio.strip() else None

    if r is not None and r.status == "error":
        st.error(r.comment or "Не удалось разобрать ФИО")
        r = None

    if p is not None or r is not None:
        if p is not None and r is not None:
            st.markdown("**Кому**")
            st.code(f"{p.dative} {r.dative_initials}", language=None)
        c1, c2 = st.columns(2)
        with c1:
            if p is not None:
                st.markdown("**Должность (дат.)**")
                st.code(p.dative, language=None)
            if r is not None:
                st.markdown("**Фамилия И.О. (дат.)**")
                st.code(r.dative_initials, language=None)
        with c2:
            if r is not None:
                st.markdown("**Имя Отчество**")
                st.code(r.name_patronymic, language=None)
                st.markdown("**Обращение**")
                st.code(r.greeting or "—", language=None)

        notes = [x for x in ((p.comment if p else ""), (r.comment if r else "")) if x]
        if notes:
            st.warning(" · ".join(notes))

# --- список -----------------------------------------------------------------
with tab2:
    what = st.radio("Что обрабатываем",
                    ["Должность + ФИО", "Только ФИО", "Только должности"],
                    horizontal=True, key="list_mode")

    if what == "Должность + ФИО":
        st.caption("Скопируйте из Excel сразу две колонки (должность слева, ФИО справа) "
                   "и вставьте сюда — разделитель Tab, ; или | подхватится сам.")
        placeholder = "Генеральный директор\tИванов Иван Иванович\nГлавный бухгалтер\tПетрова Мария Сергеевна"
    elif what == "Только ФИО":
        placeholder = "Иванов Иван Иванович\nПетрова Мария Сергеевна"
    else:
        placeholder = "Генеральный директор\nГлавный бухгалтер"

    text = st.text_area("По одной записи в строке", height=220, placeholder=placeholder)
    lines = [l for l in (text or "").splitlines() if l.strip()]

    if lines:
        if what == "Должность + ФИО":
            pairs = [re.split(r"\t|;|\|", l, maxsplit=1) for l in lines]
            pos_src = [p[0].strip() for p in pairs]
            fio_src = [(p[1].strip() if len(p) > 1 else "") for p in pairs]
            pos_res = decline_positions(pos_src, fix_case=fix_case, speller=speller)
            fio_res = process_many(fio_src, strict=strict, fix_case=fix_case, spell=spell)
            show_stats(fio_res)
            df = pd.concat([position_frame(pos_res), fio_frame(fio_res)], axis=1)
            df.insert(0, "Кому", combine(pos_res, fio_res))
            stem = "Должности_и_ФИО"
        elif what == "Только ФИО":
            fio_res = process_many(lines, strict=strict, fix_case=fix_case, spell=spell)
            show_stats(fio_res)
            df = fio_frame(fio_res)
            stem = "ФИО_разбивка"
        else:
            pos_res = decline_positions(lines, fix_case=fix_case, speller=speller)
            st.caption(f"Обработано строк: {len(pos_res)}")
            df = position_frame(pos_res)
            stem = "Должности_дат_падеж"

        st.dataframe(df, use_container_width=True, hide_index=True)
        download_buttons(df, stem)

# --- файл -------------------------------------------------------------------
with tab3:
    up = st.file_uploader("Excel или CSV", type=["xlsx", "xlsm", "xls", "csv"], key="main")
    if up is not None:
        try:
            if up.name.lower().endswith(".csv"):
                df_in = read_reference(up.getvalue(), up.name)
            else:
                xls = pd.ExcelFile(up)
                sheet = st.selectbox("Лист", xls.sheet_names)
                df_in = pd.read_excel(xls, sheet_name=sheet)
        except Exception as e:  # noqa: BLE001
            st.error(f"Не удалось прочитать файл: {e}")
            st.stop()

        st.caption(f"Строк в файле: {len(df_in)}")
        cols = [NONE] + [str(c) for c in df_in.columns]
        c1, c2 = st.columns(2)
        pos_col = c1.selectbox("Колонка с должностью", cols,
                               index=guess_column(cols, POS_HINTS, default=0))
        fio_col = c2.selectbox("Колонка с ФИО", cols,
                               index=guess_column(cols, FIO_HINTS, default=0))
        keep_all = st.checkbox("Оставить остальные колонки исходного файла", value=True)

        if st.button("Обработать", type="primary"):
            if fio_col == NONE and pos_col == NONE:
                st.warning("Выберите хотя бы одну колонку.")
                st.stop()

            pieces, used = [], []
            pos_res = fio_res = None

            with st.spinner("Обрабатываю…"):
                if pos_col != NONE:
                    src = df_in[pos_col].fillna("").astype(str).tolist()
                    pos_res = decline_positions(src, fix_case=fix_case, speller=speller)
                    pieces.append(position_frame(pos_res))
                    used.append(pos_col)

                if fio_col != NONE:
                    src = df_in[fio_col].fillna("").astype(str).tolist()
                    fio_res = process_many(src, strict=strict, fix_case=fix_case, spell=spell)
                    pieces.append(fio_frame(fio_res))
                    used.append(fio_col)

            if fio_res is not None:
                show_stats(fio_res)

            out = pd.concat(pieces, axis=1)
            if pos_res is not None and fio_res is not None:
                out.insert(0, "Кому", combine(pos_res, fio_res))

            if keep_all:
                extra = df_in.drop(columns=[c for c in used if c in df_in.columns]).reset_index(drop=True)
                out = pd.concat([out, extra], axis=1)

            st.dataframe(out.head(200), use_container_width=True, hide_index=True)
            if len(out) > 200:
                st.caption("Показаны первые 200 строк — в файле будут все.")
            download_buttons(out, up.name.rsplit(".", 1)[0] + "_обработка")
