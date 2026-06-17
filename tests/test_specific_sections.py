from __future__ import annotations

from datetime import datetime

from med_evo import compile_medievo
from med_evo.models import ClinicalItem, ClinicalSection, CompilerDiagnostic
from med_evo.sections import (
    BaseSpecificSectionParser,
    InformacoesPacienteSection,
    ItemParserConfig,
    SectionParserConfig,
    SectionRegistry,
    SubsectionParserConfig,
)


class ExamesSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="EXAMES",
        accepted_names=("EXAMES",),
        required=True,
        required_section_value=True,
    )
    subsection_parser = SubsectionParserConfig(
        default_subsections=("Atual", "Prévio"),
        required_subsections=("Prévio",),
        allow_new=False,
        inline_states=("atual", "prévio", "previo"),
    )
    item_parser = ItemParserConfig(
        allow_free_text=False,
        require_key=True,
        accepted_keys=("Hb", "PCR"),
    )

    def parse_item(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
        diagnostics: list[CompilerDiagnostic],
    ) -> dict[str, object]:
        return {
            "key": item.key,
            "state": item.state,
            "values": [value.value for value in item.values],
            "children": [self.parse_item(child, section, diagnostics) for child in item.children],
        }


def test_specific_section_registry_processes_section_without_changing_minimal_language():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medievo(
        "EVOLUÇÃO 16/06/2026\n# EXAMES: laboratoriais\n> Prévio: Hb: 10; PCR: 20\n",
        section_registry=registry,
    )

    assert not compiled.errors()
    assert "EXAMES" in compiled.processed_sections
    result = compiled.processed_sections["EXAMES"][0]
    assert result.data["items"][0]["key"] == "Hb"
    assert result.data["items"][0]["state"] == "Prévio"
    assert result.data["items"][0]["children"][0]["key"] == "PCR"


def test_specific_section_can_emit_missing_required_section_error():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medievo("# MEDICAMENTOS:\nDipirona\n", section_registry=registry)

    assert "required_section_missing" in {diagnostic.code for diagnostic in compiled.diagnostics}


def test_specific_section_can_recognize_inline_state_semantically():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medievo(
        "# EXAMES: laboratoriais\n> Prévio:\nHb: 10 atual\n",
        reference_datetime=datetime(2026, 6, 16, 10, 30),
        section_registry=registry,
    )

    item = compiled.sections[0].items[0]
    assert item.state is not None
    assert item.state.lower() == "atual"


def test_informacoes_paciente_processes_age_without_mutating_ast():
    registry = SectionRegistry([InformacoesPacienteSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# INFORMACOES DO PACIENTE",
                "Nome: Maria Silva",
                "Idade: 2 anos 3 meses 4 dias",
                "Data internacao: 10/06/2026",
                "Sexo: feminino",
                "Peso: 56,987 kg",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()

    age_item = next(item for item in compiled.sections[0].items if item.key == "Idade")
    assert [value.value for value in age_item.values] == ["2 anos 3 meses 4 dias"]
    assert age_item.children == []

    result = next(iter(compiled.processed_sections.values()))[0]
    assert result.data["idade"].value == {"anos": 2, "meses": 3, "dias": 4}
    assert result.normalized["idade"] == "2 anos 3 meses 4 dias"
    assert result.normalized["nome"] == "Maria Silva"


def test_informacoes_paciente_allows_unknown_item_keys():
    registry = SectionRegistry([InformacoesPacienteSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# INFORMACOES DO PACIENTE",
                "Nome: Maria Silva",
                "Idade: 2 anos",
                "Data internacao: 10/06/2026",
                "Sexo: feminino",
                "Peso: 16/06 56,987 kg",
                "Leito: 123",
            ]
        ),
        section_registry=registry,
    )

    assert "informacoes_paciente_unknown_item_key" not in {
        diagnostic.code for diagnostic in compiled.diagnostics
    }


def test_informacoes_paciente_errors_when_weight_is_seven_days_old():
    registry = SectionRegistry([InformacoesPacienteSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 17/06/2026",
                "# INFORMACOES DO PACIENTE",
                "Nome: Maria Silva",
                "Idade: 2 anos",
                "Data internacao: 10/06/2026",
                "Sexo: feminino",
                "Peso: 10/06 56,987 kg",
            ]
        ),
        section_registry=registry,
    )

    assert "informacoes_paciente_weight_measurement_too_old" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_informacoes_paciente_warns_when_weight_has_no_date():
    registry = SectionRegistry([InformacoesPacienteSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 17/06/2026",
                "# INFORMACOES DO PACIENTE",
                "Nome: Maria Silva",
                "Idade: 2 anos",
                "Data internacao: 10/06/2026",
                "Sexo: feminino",
                "Peso: 56,987 kg",
            ]
        ),
        section_registry=registry,
    )

    assert "informacoes_paciente_weight_without_date" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }


def test_specific_section_registry_preserves_repeated_canonical_sections():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# EXAMES: laboratoriais",
                "> Pr\u00e9vio: Hb: 10",
                "# EXAMES: imagem",
                "> Pr\u00e9vio: PCR: 20",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert len(compiled.processed_sections["EXAMES"]) == 2
    assert [result.raw_section_name for result in compiled.processed_sections["EXAMES"]] == ["EXAMES", "EXAMES"]
