# -*- coding: utf-8 -*-
"""Разбивка ФИО — Streamlit-приложение (замена Excel-макроса SplitFIO2)."""

import io
import pandas as pd
import streamlit as st

from fio_utils import process_fio, process_many, GENDER_RU

st.set_page_config(page_title="Разбивка ФИО", page_icon="👤", layout="wide")

COLS = {
    "original": "ФИО",
    "dative_initials": "Фамилия И.О. (дат.)",
    "name_patronymic": "Имя Отчество",
    "suffix": "Окончание",
    "greeting": "Обращение",
    "gender": "Пол",
    "comment": "Комментарий",
}
BASE_ORDER = ["original", "dative_initials", "name_patronymic", "suffix"]
EXTRA_ORDER = ["greeting", "gender", "comment"]


# ---------------------------------------------------------------- настройки
with st.sidebar:
    st.header("Настройки")
    strict = st.toggle(
        "Режим «как в макросе»",
        value=False,
        help="Точное повторение старого Excel-макроса: строки без отчества, "
             "с нестандартным отчеством или длиннее трёх слов пропускаются, "
             "правила склонения — исходные.",
    )
    fix_case = st.toggle(
        "Исправлять регистр (ИВАНОВ → Иванов)", value=True
    )
    show_extra = st.toggle("Показывать доп. колонки (обращение, пол, комментарий)", value=True)
    st.divider()
    st.caption(
        "Колонки на выходе:\n\n"
        "• **ФИО** — как ввели\n"
        "• **Фамилия И.О. (дат.)** — «Иванову И.И.»\n"
        "• **Имя Отчество** — «Иван Иванович»\n"
        "• **Окончание** — «ый» / «ая» для «Уважаем…»"
    )


def to_frame(results):
    order = BASE_ORDER + (EXTRA_ORDER if show_extra else [])
    rows = []
    for r in results:
        d = r.as_dict()
        d["gender"] = GENDER_RU.get(d["gender"], d["gender"])
        rows.append({COLS[k]: d[k] for k in order})
    return pd.DataFrame(rows)


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
    c2.metric("Обработано без замечаний", ok)
    c3.metric("С замечаниями", warn)
    c4.metric("Не обработано", err)
    if warn or err:
        st.caption("Строки с замечаниями стоит проверить глазами — смотрите колонку «Комментарий».")


# ---------------------------------------------------------------- интерфейс
st.title("👤 Разбивка ФИО")
st.caption("Фамилия в дательном падеже с инициалами, имя-отчество и окончание обращения.")

tab1, tab2, tab3 = st.tabs(["Одно ФИО", "Список строк", "Файл"])

# --- одно ФИО ---------------------------------------------------------------
with tab1:
    fio = st.text_input("ФИО полностью", placeholder="Иванов Иван Иванович")
    if fio.strip():
        r = process_fio(fio, strict=strict, fix_case=fix_case)
        if r.status == "error":
            st.error(r.comment or "Не удалось разобрать строку")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Фамилия И.О. (дат.)**")
                st.code(r.dative_initials, language=None)
                st.markdown("**Имя Отчество**")
                st.code(r.name_patronymic, language=None)
            with c2:
                st.markdown("**Окончание**")
                st.code(r.suffix or "—", language=None)
                st.markdown("**Обращение**")
                st.code(r.greeting or "—", language=None)
            st.caption(f"Пол: {GENDER_RU.get(r.gender, r.gender)}")
            if r.comment:
                st.warning(r.comment)

# --- список -----------------------------------------------------------------
with tab2:
    text = st.text_area(
        "По одному ФИО в строке",
        height=220,
        placeholder="Иванов Иван Иванович\nПетрова Мария Сергеевна",
    )
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if lines:
        results = process_many(lines, strict=strict, fix_case=fix_case)
        show_stats(results)
        df = to_frame(results)
        st.dataframe(df, use_container_width=True, hide_index=True)
        download_buttons(df, "ФИО_разбивка")

# --- файл -------------------------------------------------------------------
with tab3:
    up = st.file_uploader("Excel или CSV с колонкой ФИО", type=["xlsx", "xlsm", "xls", "csv"])
    if up is not None:
        try:
            if up.name.lower().endswith(".csv"):
                raw = up.getvalue()
                for enc in ("utf-8-sig", "cp1251"):
                    try:
                        df_in = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=None, engine="python")
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                xls = pd.ExcelFile(up)
                sheet = st.selectbox("Лист", xls.sheet_names)
                df_in = pd.read_excel(xls, sheet_name=sheet)
        except Exception as e:  # noqa: BLE001
            st.error(f"Не удалось прочитать файл: {e}")
            st.stop()

        st.caption(f"Строк в файле: {len(df_in)}")
        col = st.selectbox("Колонка с ФИО", list(df_in.columns))
        keep_all = st.checkbox("Оставить остальные колонки исходного файла", value=True)

        if st.button("Разбить", type="primary"):
            src = df_in[col].astype(str).fillna("").tolist()
            results = process_many(src, strict=strict, fix_case=fix_case)
            show_stats(results)
            out = to_frame(results)
            if keep_all:
                extra = df_in.drop(columns=[col]).reset_index(drop=True)
                out = pd.concat([out, extra], axis=1)
            st.dataframe(out.head(200), use_container_width=True, hide_index=True)
            if len(out) > 200:
                st.caption("Показаны первые 200 строк — в файле будут все.")
            download_buttons(out, up.name.rsplit(".", 1)[0] + "_разбивка")
