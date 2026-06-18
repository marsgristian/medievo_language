from __future__ import annotations

import json
from typing import Any

from medi_evo.minimal import compile_medi_evo
from medi_evo.normalization import normalize_document
from medi_evo.sections import (
    AporteSection,
    BalancoHidricoSection,
    CondutaSection,
    ControlesSection,
    DiagnosticoSection,
    DispositivosSection,
    ExameFisicoSection,
    ExamesImagemSection,
    ExamesLaboratoriaisSection,
    InformacoesPacienteSection,
    IntercorrenciasSection,
    MedicamentosSection,
    PlanoCuidadoSection,
    PrismivSection,
    ResumoCasoSection,
    SectionRegistry,
)


def default_section_registry() -> SectionRegistry:
    return SectionRegistry(
        [
            InformacoesPacienteSection(),
            DiagnosticoSection(),
            MedicamentosSection(),
            BalancoHidricoSection(),
            PrismivSection(),
            ControlesSection(),
            ExamesLaboratoriaisSection(),
            ExamesImagemSection(),
            IntercorrenciasSection(),
            ResumoCasoSection(),
            ExameFisicoSection(),
            AporteSection(),
            CondutaSection(),
            PlanoCuidadoSection(),
            DispositivosSection(),
        ]
    )


def compile_text(text: str, normalization: str | None = "line_min") -> dict[str, Any]:
    compiled = compile_medi_evo(text, section_registry=default_section_registry())
    document = compiled.to_dict()
    result_object = {
        "document": document,
        "sections": document.get("processed_sections", {}),
    }

    result = {
        "object": result_object,
        "normalized_text": normalize_document({"document": document}, normalization),
        "warnings": [diagnostic for diagnostic in document.get("diagnostics", []) if diagnostic.get("severity") == "warning"],
        "errors": [diagnostic for diagnostic in document.get("diagnostics", []) if diagnostic.get("severity") == "error"],
    }
    return result


def compile_json(data: dict[str, Any] | str, normalization: str | None = "line_min") -> str:
    if isinstance(data, str):
        parsed = json.loads(data)
    else:
        parsed = data
    return normalize_document(parsed, normalization)
