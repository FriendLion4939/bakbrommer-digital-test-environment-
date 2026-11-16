"""The reading steps of the import page: file → raw log (CSV mapping or CAN decoding)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from pydantic import ValidationError

from bakbrommer_twin import paths
from bakbrommer_twin.data_import import can_log, csv_log
from bakbrommer_twin.data_import.can_defs import CanDefinitions, load_definitions, save_definitions
from bakbrommer_twin.data_import.channels import LOG_CHANNELS
from bakbrommer_twin.data_import.dbc import parse_dbc
from bakbrommer_twin.data_import.mapping import ColumnMap, LogMapping, MappingStore, suggest
from bakbrommer_twin.data_import.rawlog import RawLog
from bakbrommer_twin.i18n import t
from bakbrommer_twin.params import units

_SUGGEST = "__suggest__"
_PREVIEW_ROWS = 5


def pick_file() -> tuple[str, str, bool] | None:
    """File upload or example picker. Returns (name, text, is_synthetic_example)."""
    examples = sorted(p.name for p in paths.example_logs_dir().glob("example_*"))
    upload_col, example_col = st.columns(2)
    uploaded = upload_col.file_uploader(t("import.upload"), type=["csv", "log", "txt"])
    example = example_col.selectbox(t("import.example"), [None, *examples],
                                    format_func=lambda n: n or "—")
    if uploaded is not None:
        return uploaded.name, uploaded.getvalue().decode("utf-8", errors="replace"), False
    if example is not None:
        example_col.caption(t("import.example_note"))
        text = (paths.example_logs_dir() / example).read_text(encoding="utf-8")
        return example, text, True
    return None


def _mapping_table(frame: pd.DataFrame, mapping: LogMapping) -> pd.DataFrame:
    mapped = {item.column: item for item in mapping.columns}
    rows = []
    for column in frame.columns:
        if column == mapping.time_column:
            continue
        item = mapped.get(column)
        rows.append({"column": column, "example": str(frame[column].iloc[0]),
                     "channel": item.channel if item else None,
                     "unit": item.unit if item else None,
                     "scale": item.scale if item else 1.0,
                     "offset": item.offset if item else 0.0})
    return pd.DataFrame(rows)


def read_csv(name: str, text: str) -> RawLog | None:
    """The column-mapping wizard. Returns the raw log once the mapping is valid."""
    frame = csv_log.read_table(text)
    st.dataframe(frame.head(_PREVIEW_ROWS), hide_index=True, width="stretch")
    store = MappingStore(paths.mappings_dir())
    keys = store.list_keys()
    chosen = st.selectbox(t("import.mapping"), [_SUGGEST, *keys],
                          format_func=lambda k: t("import.mapping_suggest") if k == _SUGGEST
                          else k)
    base = suggest(list(frame.columns)) if chosen == _SUGGEST else store.load(chosen)
    columns = list(frame.columns)
    time_col, unit_col = st.columns(2)
    time_column = time_col.selectbox(
        t("import.time_column"), columns,
        columns.index(base.time_column) if base.time_column in columns else 0)
    time_units = ["s", "ms", "us"]
    time_unit = unit_col.selectbox(t("import.time_unit"), time_units,
                                   time_units.index(base.time_unit))
    base = base.model_copy(update={"time_column": time_column})
    st.caption(t("import.mapping_help"))
    edited = st.data_editor(
        _mapping_table(frame, base), hide_index=True, width="stretch",
        key=f"mapping_{name}_{chosen}_{time_column}", disabled=["column", "example"],
        column_config={
            "channel": st.column_config.SelectboxColumn(options=list(LOG_CHANNELS)),
            "unit": st.column_config.SelectboxColumn(options=[u for u in units.UNITS if u]),
        })
    try:
        mapping = LogMapping(name=name, time_column=time_column, time_unit=time_unit, columns=[
            ColumnMap(column=row["column"], channel=row["channel"],
                      unit=row["unit"] or LOG_CHANNELS[row["channel"]].unit,
                      scale=float(row["scale"]), offset=float(row["offset"]))
            for row in edited.to_dict("records") if row["channel"]])
        raw = csv_log.apply_mapping(frame, mapping, name)
    except (ValueError, ValidationError) as exc:
        st.error(t("import.mapping_invalid", error=exc))
        return None
    key_col, save_col = st.columns([3, 1])
    key = key_col.text_input(t("import.mapping_name"), "" if chosen == _SUGGEST else chosen)
    if save_col.button(t("import.mapping_save"), disabled=not key, width="stretch"):
        try:
            store.save(key, mapping.model_copy(update={"name": key}))
            st.toast(t("import.mapping_saved"))
        except ValueError as exc:
            st.error(str(exc))
    return raw


def _definition_files() -> list[Path]:
    return sorted(paths.can_dir().glob("*.yaml"))


def read_can(name: str, text: str) -> RawLog | None:
    """CAN decoding: pick (or convert, or edit) a definition file, then decode."""
    with st.expander(t("import.dbc_title")):
        st.caption(t("import.dbc_help"))
        dbc = st.file_uploader(t("import.dbc_upload"), type=["dbc"])
        dbc_name = st.text_input(t("import.dbc_name"), "from_dbc")
        if dbc is not None and st.button(t("import.dbc_convert")):
            definitions, notes = parse_dbc(dbc.getvalue().decode("utf-8", errors="replace"),
                                           dbc_name)
            save_definitions(paths.can_dir() / f"{dbc_name}.yaml", definitions)
            st.success(t("import.dbc_done", count=len(definitions.messages)))
            for note in notes:
                st.caption(note)
    files = _definition_files()
    if not files:
        st.warning(t("import.no_definitions"))
        return None
    chosen = st.selectbox(t("import.definitions"), files, format_func=lambda p: p.name)
    with st.expander(t("import.edit_definitions")):
        st.caption(t("import.edit_definitions_help"))
        edited = st.text_area(t("import.definitions_text"), chosen.read_text(encoding="utf-8"),
                              height=320, key=f"defs_{chosen.name}")
        if st.button(t("import.definitions_save")):
            try:
                CanDefinitions.model_validate(yaml.safe_load(edited))
                chosen.write_text(edited, encoding="utf-8")
                st.toast(t("import.definitions_saved"))
            except (ValueError, yaml.YAMLError) as exc:
                st.error(t("import.definitions_invalid", error=exc))
    try:
        frames, bad = can_log.parse(text)
        raw = can_log.decode_frames(frames, load_definitions(chosen), name)
    except (ValueError, yaml.YAMLError) as exc:
        st.error(str(exc))
        return None
    st.caption(t("import.can_summary", frames=len(frames), bad=bad, channels=len(raw.channels)))
    return raw
