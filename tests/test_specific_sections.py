from __future__ import annotations

from datetime import datetime

from medi_evo import compile_medi_evo
from medi_evo.models import ClinicalItem, ClinicalSection, CompilerDiagnostic
from medi_evo.sections import (
    BalancoHidricoSection,
    BaseSpecificSectionParser,
    AporteSection,
    CondutaSection,
    ControlesSection,
    DiagnosticoSection,
    DispositivosSection,
    ExameFisicoSection,
    ExamesImagemSection,
    ExamesLaboratoriaisSection,
    InformacoesPacienteSection,
    IntercorrenciasSection,
    ItemParserConfig,
    MedicamentosSection,
    PlanoCuidadoSection,
    PrismivSection,
    ResumoCasoSection,
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
        default_subsections=("Atual", "Previo"),
        required_subsections=("Previo",),
        allow_new=False,
        inline_states=("atual", "previo"),
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
    compiled = compile_medi_evo(
        "EVOLUÇÃO 16/06/2026\n# EXAMES: laboratoriais\n> Previo: Hb: 10; PCR: 20\n",
        section_registry=registry,
    )

    assert not compiled.errors()
    assert "EXAMES" in compiled.processed_sections
    result = compiled.processed_sections["EXAMES"][0]
    assert result.data["items"][0]["key"] == "Hb"
    assert result.data["items"][0]["state"] == "Previo"
    assert result.data["items"][0]["children"][0]["key"] == "PCR"


def test_specific_section_can_emit_missing_required_section_error():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medi_evo("# MEDICAMENTOS:\nDipirona\n", section_registry=registry)

    assert "required_section_missing" in {diagnostic.code for diagnostic in compiled.diagnostics}


def test_specific_section_can_recognize_inline_state_semantically():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medi_evo(
        "# EXAMES: laboratoriais\n> Previo:\nHb: 10 atual\n",
        reference_datetime=datetime(2026, 6, 16, 10, 30),
        section_registry=registry,
    )

    item = compiled.sections[0].items[0]
    assert item.state is not None
    assert item.state.lower() == "atual"


def test_informacoes_paciente_processes_age_without_mutating_ast():
    registry = SectionRegistry([InformacoesPacienteSection()])
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo("# MEDICAMENTOS:\nDipirona\n", section_registry=registry)

    assert "diagnostico_missing_section" in {diagnostic.code for diagnostic in compiled.errors()}


def test_diagnostico_rejects_key_value_items():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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


def test_diagnostico_does_not_warn_about_plain_text_as_possible_cid():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# DIAGNOSTICO",
                "R9999 Hipoxemia",
            ]
        ),
        section_registry=registry,
    )

    assert "diagnostico_possible_invalid_cid" not in {
        diagnostic.code for diagnostic in compiled.warnings()
    }
    item = compiled.processed_sections["DIAGNÓSTICO"][0].data["items"][0]
    assert item["cid"] is None
    assert item["diagnostico"] == "R9999 Hipoxemia"


def test_diagnostico_data_period_rules_follow_state():
    registry = SectionRegistry([DiagnosticoSection()])
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo("# DIAGNOSTICO\nR09 Hipoxemia\n", section_registry=registry)

    assert "medicamentos_missing_section" in {diagnostic.code for diagnostic in compiled.errors()}


def test_medicamentos_rejects_free_text_items():
    registry = SectionRegistry([MedicamentosSection()])
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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
    compiled = compile_medi_evo(
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


def test_balanco_hidrico_parses_section_value_bh_and_required_items():
    registry = SectionRegistry([BalancoHidricoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "#BALANCO HIDRICO: +369,40 ml",
                "Entradas: 897,4 ml | Saidas: 528 ml | Diurese: 2,98 ml/kg/h",
                "Evacuações: 2 ml",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    result = compiled.processed_sections["BALANCO HIDRICO"][0]
    assert result.data["entradas"]["value"] == 897.4
    assert result.data["saidas"]["value"] == 528.0
    assert result.data["bh"]["value"] == 369.4
    assert result.data["bh"]["sign"] == "+"
    assert result.data["bh_source"] == "section_value"
    assert result.data["diurese"]["unit"] == "ml/kg/h"
    assert result.data["extras"]["evacuacoes"]["value"] == 2.0


def test_balanco_hidrico_calculates_missing_bh_with_warning():
    registry = SectionRegistry([BalancoHidricoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# BALANCO HIDRICO",
                "Entradas: 100 ml | Saidas: 40 ml | Diurese: 2 ml/kg/h",
            ]
        ),
        section_registry=registry,
    )

    assert "balanco_hidrico_bh_missing_calculated" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }
    assert not compiled.errors()
    result = compiled.processed_sections["BALANCO HIDRICO"][0]
    assert result.data["bh"]["value"] == 60.0
    assert result.data["bh"]["sign"] == "+"
    assert result.data["bh_source"] == "calculated"


def test_balanco_hidrico_warns_and_does_not_calculate_when_units_differ():
    registry = SectionRegistry([BalancoHidricoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# BALANCO HIDRICO",
                "Entradas: 100 ml | Saidas: 2 ml/kg/h | Diurese: 2 ml/kg/h",
            ]
        ),
        section_registry=registry,
    )

    assert "balanco_hidrico_entry_exit_unit_mismatch" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }
    assert "balanco_hidrico_missing_required_item" in {
        diagnostic.code for diagnostic in compiled.errors()
    }
    result = compiled.processed_sections["BALANCO HIDRICO"][0]
    assert result.data["bh"] is None


def test_balanco_hidrico_errors_when_bh_is_discrepant_at_one_decimal():
    registry = SectionRegistry([BalancoHidricoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# BALANCO HIDRICO: +58,8 ml",
                "Entradas: 100 ml | Saidas: 40 ml | Diurese: 2 ml/kg/h",
            ]
        ),
        section_registry=registry,
    )

    assert "balanco_hidrico_bh_discrepant" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_balanco_hidrico_requires_sign_for_nonzero_bh_but_not_zero():
    registry = SectionRegistry([BalancoHidricoSection()])
    nonzero = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# BALANCO HIDRICO: 60 ml",
                "Entradas: 100 ml | Saidas: 40 ml | Diurese: 2 ml/kg/h",
            ]
        ),
        section_registry=registry,
    )
    zero = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# BALANCO HIDRICO: 0 ml",
                "Entradas: 40 ml | Saidas: 40 ml | Diurese: 2 ml/kg/h",
            ]
        ),
        section_registry=registry,
    )

    assert "balanco_hidrico_bh_sign_required" in {
        diagnostic.code for diagnostic in nonzero.errors()
    }
    assert "balanco_hidrico_bh_sign_required" not in {
        diagnostic.code for diagnostic in zero.errors()
    }


def test_balanco_hidrico_requires_missing_items():
    registry = SectionRegistry([BalancoHidricoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# BALANCO HIDRICO",
                "Entradas: 100 ml",
            ]
        ),
        section_registry=registry,
    )

    codes = [diagnostic.code for diagnostic in compiled.errors()]
    assert codes.count("balanco_hidrico_missing_required_item") == 3


def test_prismiv_parses_percent_and_optional_prismiii_fields():
    registry = SectionRegistry([PrismivSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "#PRISMIV:90%",
                "PRISMIII: Neurologico: 90; Não Neurologico: 90",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    result = compiled.processed_sections["PRISMIV"][0]
    assert result.data["prismiv"] == "90%"
    assert result.data["prismiii"] == {
        "neurologico": "90",
        "nao_neurologico": "90",
    }


def test_prismiv_requires_percent_section_value():
    registry = SectionRegistry([PrismivSection()])
    missing = compile_medi_evo("# PRISMIV\n", section_registry=registry)
    invalid = compile_medi_evo("# PRISMIV: 90\n", section_registry=registry)

    assert "prismiv_missing_section_value" in {
        diagnostic.code for diagnostic in missing.errors()
    }
    assert "prismiv_invalid_section_value" in {
        diagnostic.code for diagnostic in invalid.errors()
    }


def test_prismiv_prismiii_fields_are_required_when_item_exists():
    registry = SectionRegistry([PrismivSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "#PRISMIV:90%",
                "PRISMIII: Neurologico: 90",
            ]
        ),
        section_registry=registry,
    )

    assert "prismiv_prismiii_missing_field" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_prismiv_rejects_unexpected_items():
    registry = SectionRegistry([PrismivSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "#PRISMIV:90%",
                "Outro: valor",
            ]
        ),
        section_registry=registry,
    )

    assert "prismiv_unexpected_item" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_controles_parses_numeric_textual_and_basic_controls():
    registry = SectionRegistry([ControlesSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# CONTROLES",
                "FC: 59-180 bpm | FR: 25-59 irpm | Tax: 36,5-39,2°C",
                "Dist. resp: N 16/06",
                "Glasgow: 15 16/06",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert "controles_missing_unit" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }
    items = compiled.processed_sections["CONTROLES"][0].data["items"]
    assert items[0]["tipo"] == "numerico"
    assert items[0]["min"] == 59.0
    assert items[0]["max"] == 180.0
    assert items[0]["unidade"] == "bpm"
    assert items[0]["periodo"] == "ultimas_24h"
    assert items[3]["tipo"] == "textual"
    assert items[3]["medicao"] == "N"
    assert items[3]["data"] is not None
    assert items[4]["tipo"] == "basico"
    assert items[4]["medicao"] == 15.0


def test_controles_accepts_sinais_vitais_alias():
    registry = SectionRegistry([ControlesSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# SINAIS VITAIS",
                "FC: 59-180 bpm",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert "CONTROLES" in compiled.processed_sections


def test_controles_basic_requires_date():
    registry = SectionRegistry([ControlesSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# CONTROLES",
                "Glasgow: 15",
                "Dist. resp: N",
            ]
        ),
        section_registry=registry,
    )

    assert [diagnostic.code for diagnostic in compiled.errors()].count("controles_basic_date_required") == 2
    assert "controles_missing_unit" in {
        diagnostic.code for diagnostic in compiled.warnings()
    }


def test_controles_rejects_free_text_items():
    registry = SectionRegistry([ControlesSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# CONTROLES",
                "Paciente estável",
            ]
        ),
        section_registry=registry,
    )

    assert "controles_key_value_required" in {
        diagnostic.code for diagnostic in compiled.errors()
    }


def test_controles_numeric_range_can_have_explicit_period():
    registry = SectionRegistry([ControlesSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# CONTROLES",
                "FC: 10/06-16/06 59-180 bpm",
            ]
        ),
        section_registry=registry,
    )

    item = compiled.processed_sections["CONTROLES"][0].data["items"][0]
    assert item["tipo"] == "numerico"
    assert item["periodo"] is not None
    assert item["periodo"] != "ultimas_24h"


def test_exam_sections_parse_dated_key_value_items_in_source_order():
    registry = SectionRegistry([ExamesLaboratoriaisSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# EXAMES",
                "(10/06) Hb: 10",
                "(15/06) PCR: 12",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    items = compiled.processed_sections["EXAMES LABORATORIAIS"][0].data["items"]
    assert [item["data"] for item in items] == ["2026-06-10", "2026-06-15"]
    assert [item["chave"] for item in items] == ["Hb", "PCR"]
    assert [item["valor"] for item in items] == ["10", "12"]


def test_dated_sections_accept_parenthesized_date_items_and_group_headings():
    registry = SectionRegistry([ExamesLaboratoriaisSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 18/06/2026",
                "# EXAMES LABORATORIAIS",
                "Culturas: | (16/06): Hemocultura: coletado | Painel viral externo: | (15/06): Teste Rapido VSR: positivo",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    items = compiled.processed_sections["EXAMES LABORATORIAIS"][0].data["items"]
    assert [item["data"] for item in items] == ["2026-06-16", "2026-06-15"]
    assert [item["chave"] for item in items] == ["Hemocultura", "Teste Rapido VSR"]
    assert [item["valor"] for item in items] == ["coletado", "positivo"]
    assert [item["conteudo"] for item in items] == [
        "Hemocultura: coletado",
        "Teste Rapido VSR: positivo",
    ]


def test_dated_sections_accept_parenthesized_date_items_in_analogous_sections():
    registry = SectionRegistry([ExamesImagemSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 18/06/2026",
                "# EXAME DE IMAGEM",
                "(15/06): RX torax: normal",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    item = compiled.processed_sections["EXAMES DE IMAGEM"][0].data["items"][0]
    assert item["data"] == "2026-06-15"
    assert item["chave"] == "RX torax"
    assert item["valor"] == "normal"
    assert item["conteudo"] == "RX torax: normal"


def test_exam_sections_accept_text_and_date_subcategories():
    registry = SectionRegistry([ExamesLaboratoriaisSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 23/06/2026",
                "# EXAMES Laboratoriais",
                "> Painel Viral:",
                "(19/05 - UPA) COVID 19: Nao reagente",
                "(19/05 - HU) Influenza A/B: Nao reagente",
                "> Culturas:",
                "(30/05): Hemocultura (04/06- 3 parcial): Negativa",
                "> 31/05:",
                "Antibiograma: Nao houve crescimento bacteriano.",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    items = compiled.processed_sections["EXAMES LABORATORIAIS"][0].data["items"]
    assert [item["subcategoria"] for item in items] == ["Painel Viral", "Painel Viral", "Culturas", None]
    assert [item["origem"] for item in items] == ["UPA", "HU", None, None]
    assert [item["data"] for item in items] == ["2026-05-19", "2026-05-19", "2026-05-30", "2026-05-31"]
    assert [item["chave"] for item in items] == ["COVID 19", "Influenza A/B", "Hemocultura", "Antibiograma"]
    assert items[2]["comentarios_chave"] == ["04/06- 3 parcial"]


def test_dated_sections_parse_date_state_with_time_key():
    registry = SectionRegistry([IntercorrenciasSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# EVOLUCAO",
                "> 10/06:",
                "10:00: Sem intercorrencias",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    result = next(iter(compiled.processed_sections.values()))[0]
    item = result.data["items"][0]
    assert item["data"] == "2026-06-10"
    assert item["hora"] == "10:00"
    assert item["conteudo"] == "Sem intercorrencias"


def test_exam_sections_reject_items_without_date_or_key():
    registry = SectionRegistry([ExamesImagemSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# EXAME DE IMAGEM",
                "RX: torax normal",
                "> 10/06:",
                "torax normal",
            ]
        ),
        section_registry=registry,
    )

    codes = {diagnostic.code for diagnostic in compiled.errors()}
    assert "exames_de_imagem_date_required" in codes
    assert "exames_de_imagem_item_key_required" in codes


def test_free_sections_split_free_text_and_key_value_items():
    registry = SectionRegistry([ResumoCasoSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# HMA",
                "Paciente com tosse",
                "Antecedentes: prematuridade",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    result = compiled.processed_sections["RESUMO DO CASO"][0]
    assert result.data["free_text_items"][0]["values"] == ["Paciente com tosse"]
    assert result.data["key_value_items"][0]["key"] == "Antecedentes"
    assert result.data["key_value_items"][0]["values"] == ["prematuridade"]


def test_free_sections_warn_when_present_but_empty_and_accept_aliases():
    registry = SectionRegistry(
        [
            ExameFisicoSection(),
            AporteSection(),
            CondutaSection(),
            PlanoCuidadoSection(),
            DispositivosSection(),
        ]
    )
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# EXAME FISICO",
                "# DIETA",
                "Enteral plena",
                "# CONDUTAS",
                "Manter",
                "# PLANO DE CUIDADO",
                "Reavaliar",
                "# DISPOSITIVOS",
                "SNE: posicionada",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert "exame_fisico_empty_section" in {diagnostic.code for diagnostic in compiled.warnings()}
    assert "APORTE" in compiled.processed_sections
    assert "CONDUTA" in compiled.processed_sections


def test_specific_section_registry_preserves_repeated_canonical_sections():
    registry = SectionRegistry([ExamesSection()])
    compiled = compile_medi_evo(
        "\n".join(
            [
                "EVOLUCAO 16/06/2026",
                "# EXAMES: laboratoriais",
                "> Previo: Hb: 10",
                "# EXAMES: imagem",
                "> Previo: PCR: 20",
            ]
        ),
        section_registry=registry,
    )

    assert not compiled.errors()
    assert len(compiled.processed_sections["EXAMES"]) == 2
    assert [result.raw_section_name for result in compiled.processed_sections["EXAMES"]] == ["EXAMES", "EXAMES"]
