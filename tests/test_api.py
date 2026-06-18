from __future__ import annotations

from medi_evo import compile_json, compile_text


COMPLETE_TEXT = "\n".join(
    [
        "EVOLUCAO 16/06/2026",
        "# INFORMACOES DO PACIENTE",
        "Nome: Maria",
        "Idade: 2 anos",
        "Data internacao: 10/06/2026",
        "Sexo: feminino",
        "Peso: 16/06 10 kg",
        "# DIAGNOSTICO",
        "R09 Hipoxemia",
        "# MEDICAMENTOS",
        "Clonidina: 3 mcg/kg/dose; 6/6h; Di 09/06; VS",
        "# BALANCO HIDRICO: +60 ml",
        "Entradas: 100 ml | Saidas: 40 ml | Diurese: 2 ml/kg/h",
        "# PRISMIV: 90%",
        "PRISMIII: Neurologico: 90; Nao Neurologico: 90",
        "# CONTROLES",
        "FC: 59-180 bpm | Dist. resp: N 16/06",
        "# EXAMES",
        "10/06: Hb 10",
        "# EXAMES DE IMAGEM",
        "10/06: RX torax normal",
        "# INTERCORRENCIAS",
        "> 10/06:",
        "10:00: Sem intercorrencias",
        "# HMA",
        "Paciente em acompanhamento",
        "# EXAME FISICO",
        "BEG | AR: MV presente",
        "# DIETA",
        "Enteral plena",
        "# CONDUTAS",
        "Manter",
        "# PLANO DE CUIDADO",
        "Reavaliar",
        "# DISPOSITIVOS",
        "SNE: posicionada",
    ]
)


def test_compile_text_returns_public_object_and_normalized_text():
    result = compile_text(COMPLETE_TEXT, normalization="line_min")

    assert result["errors"] == []
    assert "document" in result["object"]
    assert "sections" in result["object"]
    assert "INFORMAÇÕES DO PACIENTE" in result["object"]["sections"]
    assert "#INFORMACOES DO PACIENTE" in result["normalized_text"]
    assert "Nome: Maria | Idade: 2 anos" in result["normalized_text"]


def test_compile_json_renders_complete_compile_text_result():
    result = compile_text(COMPLETE_TEXT, normalization="line_min")
    rendered = compile_json(result, normalization="char_min")

    assert "#INFORMACOES DO PACIENTE" in rendered
    assert "Nome:Maria|Idade:2 anos" in rendered


def test_compile_text_returns_normalized_text_even_with_errors():
    result = compile_text("# DIAGNOSTICO\nR09 Hipoxemia", normalization="line_min")

    assert result["errors"]
    assert result["normalized_text"]
    assert "#DIAGNOSTICO" in result["normalized_text"]
