from __future__ import annotations

from datetime import datetime

import pytest

from med_evo.minimal import compile_minimal_medievo


BASE_REFERENCE = datetime(2026, 6, 16, 10, 30)


def codes(text: str) -> set[str]:
    compiled = compile_minimal_medievo(text, reference_datetime=BASE_REFERENCE)
    return {diagnostic.code for diagnostic in compiled.diagnostics}


def test_error_empty_section_name():
    assert "empty_section_name" in codes("#\n")


def test_error_section_cannot_contain_subsection_marker():
    assert "section_contains_subsection_marker" in codes("# MEDICAMENTOS > Antibiótico:\n")


def test_error_section_cannot_contain_item_separator():
    assert "section_contains_item_separator" in codes("# CONTROLES: FC: 100 | FR: 20\n")


def test_error_empty_subsection_name():
    assert "empty_subsection_name" in codes("# MEDICAMENTOS:\n>: item\n")


def test_error_subsection_missing_colon():
    assert "subsection_missing_colon" in codes("# MEDICAMENTOS:\n> Prévio\n")


def test_error_empty_item_key():
    assert "empty_item_key" in codes("# MEDICAMENTOS:\n: value\n")


@pytest.mark.parametrize("source", ["# MEDICAMENTOS:\nkey:\n", "# MEDICAMENTOS:\nkey : |\n", "# MEDICAMENTOS:\nkey : ;\n"])
def test_error_empty_item_value(source: str):
    assert "empty_item_value" in codes(source)


def test_free_text_item_without_colon_is_allowed():
    compiled = compile_minimal_medievo("# RESUMO:\nPaciente em bom estado geral\n", reference_datetime=BASE_REFERENCE)
    assert not compiled.errors()
    assert compiled.sections[0].items[0].key is None
    assert compiled.sections[0].items[0].values[0].value == "Paciente em bom estado geral"


def test_subsection_can_have_items_in_same_line():
    compiled = compile_minimal_medievo("# EXAMES:\n> Prévio: Hb: 10 | PCR: 20\n", reference_datetime=BASE_REFERENCE)
    assert not compiled.errors()
    section = compiled.sections[0]
    assert section.states[0].subsec_name == "Prévio"
    assert [item.state for item in section.items] == ["Prévio", "Prévio"]
    assert [item.key for item in section.items] == ["Hb", "PCR"]


def test_section_line_accepts_name_and_optional_value_only():
    compiled = compile_minimal_medievo("# EXAMES: laboratoriais (últimas 24h)\nHb: 10\n", reference_datetime=BASE_REFERENCE)
    assert not compiled.errors()
    section = compiled.sections[0]
    assert section.section_name == "EXAMES"
    assert section.section_value == "laboratoriais"
    assert section.commented_values == ["últimas 24h"]
