from __future__ import annotations

from datetime import datetime

from med_evo import compile_medievo
from med_evo.models import ClinicalItem, ClinicalSection, CompilerDiagnostic
from med_evo.sections import (
    BaseSpecificSectionParser,
    DiagnosticoSection,
    InformacoesPacienteSection,
    ItemParserConfig,
    MedicamentosSection,
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


def test_diagnostico_parses_free_text_items_with_cid_state_and_dates():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNÓSTICO",
                "R09 Hipoxemia a/e (cissurite em lobo inferior direito)",
                "J98.1 Atelectasia crônica",
                "R13 Disfagia? (precisa de exames para saber ao certo)",
                "> Em tratamento:",
                "J18 Pneumonia nasocomial / bronco aspirativa",
                "I90 Derrame pleural a direita- PO drenagem 05/06",
                "> Tratado: E87.6 Hipocalemia 01/06-05/06",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    result = compiled.processed_sections["DIAGNÓSTICO"][0]
    items = result.data["items"]

    assert items[0]["cid"] == "R09"
    assert items[0]["cid_version"] == "CID-10"
    assert items[0]["diagnostico"] == "Hipoxemia a/e"
    assert items[0]["estado"] == "Ativo"
    assert items[0]["commented_values"] == ["cissurite em lobo inferior direito"]

    assert items[2]["diagnostico"] == "Disfagia"
    assert items[2]["estado"] == "Investigação"

    assert items[4]["estado"] == "Em tratamento"
    assert items[4]["diagnostico"] == "Derrame pleural a direita- PO drenagem"

    assert items[5]["estado"] == "Tratado"
    assert items[5]["data"] is not None


def test_diagnostico_accepts_case_accent_and_plural_aliases():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# hipoteses diagnosticas",
                "R09 Hipoxemia",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert "DIAGNÓSTICO" in compiled.processed_sections


def test_diagnostico_parses_icd11_code():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "1A00 Cólera",
            ]
        ),
        section_registry=registry,
    )

    item = compiled.processed_sections["DIAGNÓSTICO"][0].data["items"][0]
    assert item["cid"] == "1A00"
    assert item["cid_version"] == "CID-11"
    assert item["diagnostico"] == "Cólera"


def test_diagnostico_requires_section():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo("# MEDICAMENTOS:\nDipirona\n", section_registry=registry)

    assert "diagnostico_missing_section" in {diagnostic.code for diagnostic in compiled.errors()}


def test_diagnostico_rejects_key_value_items():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "HD: Pneumonia",
            ]
        ),
        section_registry=registry,
    )

    assert "diagnostico_key_value_not_allowed" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_diagnostico_requires_diagnosis_text_after_parseable_fields():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "R09 ?",
            ]
        ),
        section_registry=registry,
    )

    assert "diagnostico_missing_diagnosis" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_diagnostico_warns_about_possible_invalid_cid_without_removing_it():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "R9999 Hipoxemia",
            ]
        ),
        section_registry=registry,
    )

    assert "diagnostico_possible_invalid_cid" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }
    item = compiled.processed_sections["DIAGNÓSTICO"][0].data["items"][0]
    assert item["cid"] is None
    assert item["diagnostico"] == "R9999 Hipoxemia"


def test_diagnostico_data_period_rules_follow_state():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "J18 Pneumonia 01/06-05/06",
                "E87.6 Hipocalemia tratada 01/06",
            ]
        ),
        section_registry=registry,
    )

    assert "diagnostico_date_period_only_for_treated" in {
        diagnostic.code for diagnostic in compiled.errors()
    }
    assert "diagnostico_treated_date_should_be_period" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }


def test_diagnostico_inline_state_wins_and_multiple_states_errors():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "> Tratado:",
                "J18 Pneumonia em tratamento",
            ]
        ),
        section_registry=registry,
    )

    item = compiled.processed_sections["DIAGNÓSTICO"][0].data["items"][0]
    assert item["estado"] == "Em tratamento"
    assert "diagnostico_multiple_states_for_item" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_medicamentos_parses_key_value_items_with_dose_interval_date_and_extras():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# MEDICAMENTOS",
                "Clonidina: 3 mcg/kg/dose; 6/6h; Di 09/06; VS",
                "Dipirona: 14 mg/kg/dose; ACM; se dor ou febre",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    items = compiled.processed_sections["MEDICAMENTOS"][0].data["items"]

    assert items[0]["nome"] == "Clonidina"
    assert items[0]["dose"] == "3 mcg/kg/dose"
    assert items[0]["intervalo"] == "6/6h"
    assert items[0]["data"] is not None
    assert items[0]["estado"] == "Ativo"
    assert items[0]["extras"] == ["VS"]

    assert items[1]["dose"] == "14 mg/kg/dose"
    assert items[1]["intervalo"] is None
    assert items[1]["extras"] == ["ACM", "se dor ou febre"]


def test_medicamentos_accepts_aliases_and_empty_marker():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# medicacoes: sem medicamentos",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert not compiled.warnings()
    result = compiled.processed_sections["MEDICAMENTOS"][0]
    assert result.data["sem_medicamentos"] is True
    assert result.data["items"] == []


def test_medicamentos_warns_when_empty_without_explicit_marker():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# MEDICAMENTOS",
            ]
        ),
        section_registry=registry,
    )

    assert "medicamentos_empty_without_explicit_marker" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }


def test_medicamentos_requires_section():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo("# DIAGNOSTICO\nR09 Hipoxemia\n", section_registry=registry)

    assert "medicamentos_missing_section" in {diagnostic.code for diagnostic in compiled.errors()}


def test_medicamentos_rejects_free_text_items():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# MEDICAMENTOS",
                "Clonidina 3 mcg/kg/dose 6/6h",
            ]
        ),
        section_registry=registry,
    )

    assert "medicamentos_key_value_required" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_medicamentos_warns_when_missing_interval_and_extra():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# MEDICAMENTOS",
                "Clonidina: 3 mcg/kg/dose",
            ]
        ),
        section_registry=registry,
    )

    assert "medicamentos_missing_interval_or_extra" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }


def test_medicamentos_suspended_requires_period_and_warns_on_single_date():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# MEDICAMENTOS",
                "> Suspenso:",
                "Lorazepam: 0,1 mg/kg/dose; 4/4h",
                "Metadona: 0,15 mg/kg/dose; 4/4h; 04/06",
                "Furosemida: 1 mg/kg/dose; 12/12h; 04/06-10/06",
            ]
        ),
        section_registry=registry,
    )

    assert "medicamentos_suspended_missing_period" in {
        diagnostic.code for diagnostic in compiled.errors()
    }
    assert "medicamentos_suspended_date_should_be_period" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }


def test_medicamentos_inline_state_wins_and_multiple_states_errors():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medievo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# MEDICAMENTOS",
                "> Suspenso:",
                "Clonidina: 3 mcg/kg/dose; 6/6h; atual",
            ]
        ),
        section_registry=registry,
    )

    item = compiled.processed_sections["MEDICAMENTOS"][0].data["items"][0]
    assert item["estado"] == "Ativo"
    assert "medicamentos_multiple_states_for_item" in {
        diagnostic.code for diagnostic in compiled.errors()
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
