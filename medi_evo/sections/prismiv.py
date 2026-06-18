from __future__ import annotations

import re
from typing import Any

from medi_evo.models import (
    ClinicalDocument,
    ClinicalItem,
    ClinicalSection,
    CompilerDiagnostic,
)
from medi_evo.sections.base import (
    AssociatedErrorsConfig,
    BaseSpecificSectionParser,
    ItemParserConfig,
    NormalizationConfig,
    SectionParserConfig,
    SubsectionParserConfig,
    normalize_name,
)
from medi_evo.minimal.text import find_structural_colon


class PrismivSection(BaseSpecificSectionParser):
    """Parser especifico da secao PRISMIV."""

    section_parser = SectionParserConfig(
        canonical_name="PRISMIV",
        accepted_names=("PRISMIV", "PRISM IV"),
        required=True,
        required_section_value=False,
    )

    subsection_parser = SubsectionParserConfig(
        default_subsections=(),
        required_subsections=(),
        allow_new=False,
        inline_states=(),
        use_default_subsections_as_inline_states=False,
    )

    item_parser = ItemParserConfig(
        allow_free_text=False,
        require_key=True,
        allow_children=True,
    )

    normalization = NormalizationConfig(
        normalized_section_name="PRISMIV",
    )

    associated_errors = AssociatedErrorsConfig(
        missing_required_section="prismiv_missing_section",
        free_text_not_allowed="prismiv_free_text_not_allowed",
        item_key_required="prismiv_item_key_required",
        unknown_item_key="prismiv_unknown_item",
        unknown_subsection="prismiv_unknown_subsection",
    )

    def validate_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
    ) -> list[CompilerDiagnostic]:
        diagnostics = super().validate_section(section, document)

        if not section.section_value or not section.section_value.strip():
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="prismiv_missing_section_value",
                    message="por favor calcule o prism",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )
        elif _PRISM_PERCENT_RE.fullmatch(section.section_value.strip()) is None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="prismiv_invalid_section_value",
                    message="PRISMIV deve conter um valor percentual, exemplo: 90%.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )

        for item in section.items:
            if self._canonical_key(item.key) != "prismiii":
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="prismiv_unexpected_item",
                        message="Seção PRISMIV só aceita o item PRISMIII.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )
                continue

            present = self._prismiii_fields(item)
            for required in ("neurologico", "nao_neurologico"):
                if required not in present:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code="prismiv_prismiii_missing_field",
                            message=f"PRISMIII deve conter o campo {self._display_field(required)}.",
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )

        return diagnostics

    def parse_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
        diagnostics: list[CompilerDiagnostic],
    ) -> dict[str, Any]:
        prismiii = None
        for item in section.items:
            if self._canonical_key(item.key) == "prismiii":
                prismiii = self._parse_prismiii(item)
                break

        return {
            "prismiv": section.section_value,
            "prismiii": prismiii,
        }

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        return {
            "section_name": self.normalization.normalized_section_name,
            "prismiv": data.get("prismiv"),
            "prismiii": data.get("prismiii"),
        }

    def _parse_prismiii(self, item: ClinicalItem) -> dict[str, str]:
        fields: dict[str, str] = {}
        for value in item.values:
            key, field_value = self._split_field_value(value.value)
            canonical = self._canonical_prismiii_field(key)
            if canonical is not None:
                fields[canonical] = field_value
        for child in item.children:
            canonical = self._canonical_prismiii_field(child.key)
            if canonical is not None:
                fields[canonical] = self._item_value_text(child)
        return fields

    def _prismiii_fields(self, item: ClinicalItem) -> set[str]:
        fields = set()
        for value in item.values:
            key, _field_value = self._split_field_value(value.value)
            canonical = self._canonical_prismiii_field(key)
            if canonical is not None:
                fields.add(canonical)
        for child in item.children:
            canonical = self._canonical_prismiii_field(child.key)
            if canonical is not None:
                fields.add(canonical)
        return fields

    def _canonical_key(self, key: str | None) -> str | None:
        if key is None:
            return None
        normalized = normalize_name(key).replace(" ", "")
        if normalized in {"prismiii", "prism3"}:
            return "prismiii"
        return normalized

    def _canonical_prismiii_field(self, key: str | None) -> str | None:
        if key is None:
            return None
        normalized = _strip_accents(normalize_name(key))
        aliases = {
            "neurologico": "neurologico",
            "nao neurologico": "nao_neurologico",
            "não neurologico": "nao_neurologico",
            "nao neurológico": "nao_neurologico",
            "não neurológico": "nao_neurologico",
        }
        return aliases.get(normalized)

    def _display_field(self, field: str) -> str:
        if field == "nao_neurologico":
            return "Nao Neurologico"
        return "Neurologico"

    def _item_value_text(self, item: ClinicalItem) -> str:
        return " ".join(value.value for value in item.values if value.value).strip()

    def _split_field_value(self, text: str) -> tuple[str | None, str]:
        colon = find_structural_colon(text)
        if colon is None:
            return None, text.strip()
        return text[:colon].strip(), text[colon + 1 :].strip()


_PRISM_PERCENT_RE = re.compile(r"\d+(?:[,.]\d+)?\s*%")


def _strip_accents(value: str) -> str:
    import unicodedata

    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
