from __future__ import annotations

from datetime import datetime

from med_evo.minimal import compile_minimal_medievo


REF = datetime(2026, 6, 16, 10, 30)


def test_partial_date_uses_header_year_when_not_future():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026 10:30\n# EXAMES:\n10/06 Hb: 10\n")
    item = compiled.sections[0].items[0]
    assert item.date is not None
    assert item.date.value.year == 2026
    assert item.date.explicit_year is False
    assert item.date.inferred_year == 2026
    assert item.key == "Hb"


def test_partial_date_future_relative_to_header_uses_previous_year():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026 10:30\n# EXAMES:\n20/06 Hb: 10\n")
    item = compiled.sections[0].items[0]
    assert item.date is not None
    assert item.date.value.year == 2025


def test_parenthesized_date_only_is_recognized_as_date():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026\n# INTERCORRÊNCIAS:\n(10/06) Sem intercorrências\n")
    item = compiled.sections[0].items[0]
    assert item.date is not None
    assert item.date.raw_text == "10/06"
    assert item.values[0].value == "Sem intercorrências"


def test_date_period_has_delta_time():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026\n# DISPOSITIVOS:\nSVD: 10/06-12/06\n")
    item = compiled.sections[0].items[0]
    assert item.date is not None
    assert item.date.raw_text == "10/06-12/06"
    assert item.date.delta_time.days == 2


def test_day_to_date_period_uses_end_month():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026\n# DISPOSITIVOS:\nSVD: 10-12/06\n")
    item = compiled.sections[0].items[0]
    assert item.date is not None
    assert item.date.start.value.month == 6
    assert item.date.end.value.day == 12


def test_date_key_is_allowed_when_date_before_colon():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026\n# INTERCORRÊNCIAS:\n10/06: melhora clínica\n")
    item = compiled.sections[0].items[0]
    assert item.key == "10/06"
    assert item.date is not None
    assert item.values[0].value == "melhora clínica"


def test_parentheses_are_commented_values_not_ignored_comments():
    compiled = compile_minimal_medievo("# MEDICAMENTOS:\nDipirona: se febre (T > 37,8°C) /* não renderizar */\n", reference_datetime=REF)
    section = compiled.sections[0]
    item = section.items[0]
    assert section.ignored_comments == ["não renderizar"]
    assert item.values[0].commented_values == ["T > 37,8°C"]
    assert item.values[0].value == "se febre"


def test_compound_item_creates_children():
    compiled = compile_minimal_medievo("# EXAMES:\nHb: 10,2; Leuco: 12000; Plaquetas: 250000\n", reference_datetime=REF)
    item = compiled.sections[0].items[0]
    assert item.key == "Hb"
    assert item.values[0].value == "10,2"
    assert [child.key for child in item.children] == ["Leuco", "Plaquetas"]
    assert [child.values[0].value for child in item.children] == ["12000", "250000"]


def test_json_serializes_datetime_and_timedelta():
    compiled = compile_minimal_medievo("EVOLUÇÃO 16/06/2026\n# DISPOSITIVOS:\nSVD: 10/06-12/06\n")
    payload = compiled.to_json()
    assert "2026-06-10T00:00" in payload
    assert "seconds" in payload
