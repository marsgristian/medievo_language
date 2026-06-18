from __future__ import annotations

import unicodedata
from typing import Any

from medi_evo.models import ClinicalDocument, ClinicalItem, ClinicalSection, CompilerDiagnostic
from medi_evo.sections.base import (
    AssociatedErrorsConfig,
    BaseSpecificSectionParser,
    ItemParserConfig,
    NormalizationConfig,
    SectionParserConfig,
    SubsectionParserConfig,
    normalize_name,
)


class FreeClinicalSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="FREE",
        accepted_names=("FREE",),
        required=True,
    )
    subsection_parser = SubsectionParserConfig(
        default_subsections=(),
        required_subsections=(),
        allow_new=True,
        inline_states=(),
        use_default_subsections_as_inline_states=False,
    )
    item_parser = ItemParserConfig(
        allow_free_text=True,
        require_key=False,
        allow_children=True,
    )
    normalization = NormalizationConfig()
    associated_errors = AssociatedErrorsConfig()

    def matches(self, section_name: str) -> bool:
        normalized = _strip_accents(normalize_name(section_name))
        accepted = {_strip_accents(normalize_name(name)) for name in self.accepted_names}
        return normalized in accepted

    def validate_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
    ) -> list[CompilerDiagnostic]:
        diagnostics = super().validate_section(section, document)
        if not section.section_value and not section.items and not section.states:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code=f"{self._code_prefix()}_empty_section",
                    message=f"Seção {section.section_name} está vazia.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )
        return diagnostics

    def parse_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
        diagnostics: list[CompilerDiagnostic],
    ) -> dict[str, Any]:
        free_text_items = []
        key_value_items = []

        for item in section.items:
            parsed = self._parse_item(item)
            if item.key is None:
                free_text_items.append(parsed)
            else:
                key_value_items.append(parsed)

        return {
            "section_value": section.section_value,
            "subsections": [
                {
                    "name": subsection.subsec_name,
                    "line": subsection.line,
                    "raw_text": subsection.raw_text,
                }
                for subsection in section.states
            ],
            "free_text_items": free_text_items,
            "key_value_items": key_value_items,
        }

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "section_name": self.normalization.normalized_section_name or self.canonical_name,
            **data,
        }

    def _parse_item(self, item: ClinicalItem) -> dict[str, Any]:
        return {
            "key": item.key,
            "values": [value.value for value in item.values],
            "state": item.state,
            "date": item.date,
            "commented_values": item.commented_values,
            "children": [self._parse_item(child) for child in item.children],
            "raw_text": item.raw_text,
        }

    def _code_prefix(self) -> str:
        return _strip_accents(normalize_name(self.canonical_name)).replace(" ", "_")


class ResumoCasoSection(FreeClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="RESUMO DO CASO",
        accepted_names=(
            "RESUMO DO CASO",
            "HISTÓRIA DA MOLÉSTIA ATUAL",
            "HISTORIA DA MOLESTIA ATUAL",
            "HMA",
        ),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="RESUMO DO CASO")
    associated_errors = AssociatedErrorsConfig(missing_required_section="resumo_do_caso_missing_section")


class ExameFisicoSection(FreeClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="EXAME FISICO",
        accepted_names=("EXAME FÍSICO", "EXAME FISICO"),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="EXAME FISICO")
    associated_errors = AssociatedErrorsConfig(missing_required_section="exame_fisico_missing_section")


class AporteSection(FreeClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="APORTE",
        accepted_names=("APORTE", "DIETA"),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="APORTE")
    associated_errors = AssociatedErrorsConfig(missing_required_section="aporte_missing_section")


class CondutaSection(FreeClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="CONDUTA",
        accepted_names=("CONDUTA", "CONDUTAS"),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="CONDUTA")
    associated_errors = AssociatedErrorsConfig(missing_required_section="conduta_missing_section")


class PlanoCuidadoSection(FreeClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="PLANO DE CUIDADO",
        accepted_names=("PLANO DE CUIDADO",),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="PLANO DE CUIDADO")
    associated_errors = AssociatedErrorsConfig(missing_required_section="plano_de_cuidado_missing_section")


class DispositivosSection(FreeClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="DISPOSITIVOS",
        accepted_names=("DISPOSITIVOS",),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="DISPOSITIVOS")
    associated_errors = AssociatedErrorsConfig(missing_required_section="dispositivos_missing_section")


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
