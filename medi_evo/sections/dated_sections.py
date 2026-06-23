from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from medi_evo.minimal.dates import parse_clinical_date
from medi_evo.minimal.text import extract_parenthesized_values, find_structural_colon, normalize_spaces
from medi_evo.models import ClinicalDate, ClinicalDocument, ClinicalItem, ClinicalSection, CompilerDiagnostic
from medi_evo.sections.base import (
    AssociatedErrorsConfig,
    BaseSpecificSectionParser,
    ItemParserConfig,
    NormalizationConfig,
    SectionParserConfig,
    SubsectionParserConfig,
    normalize_name,
)


class DatedClinicalSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="DATED",
        accepted_names=("DATED",),
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
        allow_free_text=False,
        require_key=True,
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
        self._suppress_group_heading_diagnostics(section, document)

        diagnostics: list[CompilerDiagnostic] = []
        if self.section_parser.required_section_value and not section.section_value:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code=self.associated_errors.missing_section_value,
                    message=f"Seção {section.section_name} exige section_value após `:`.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )
        diagnostics.extend(self.validate_subsections(section))

        for subsection in section.states:
            if self._parse_date_text(subsection.subsec_name, document.reference_datetime) is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code=f"{self._code_prefix()}_invalid_date_state",
                        message=f"Subseção de {section.section_name} deve ser uma data.",
                        phase="semantic",
                        line=subsection.line,
                        section=section.section_name,
                        raw_text=subsection.raw_text,
                    )
                )

        for item in section.items:
            if self._is_group_heading(item):
                continue

            if item.state:
                if self._parse_date_text(item.state, document.reference_datetime) is None:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code=f"{self._code_prefix()}_invalid_date_state",
                            message=f"Estado de {section.section_name} deve ser uma data.",
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )
                if item.key is None or _TIME_KEY_RE.fullmatch(item.key.strip()) is None:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code=f"{self._code_prefix()}_time_key_required",
                            message="Item sob subseção datada deve usar hora em formato HH:MM como chave.",
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )
                continue

            if not self._has_item_date(item, document.reference_datetime):
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code=f"{self._code_prefix()}_date_key_required",
                        message=f"Item de {section.section_name} deve usar data como chave ou estar sob subseção datada.",
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
        items: list[dict[str, Any]] = []

        for item in section.items:
            parsed = self._parse_dated_item(item, document.reference_datetime)
            if parsed is not None:
                items.append(parsed)

        items.sort(
            key=lambda entry: (
                entry.get("_sort_datetime") or datetime.min,
                entry.get("hora") or "",
            ),
            reverse=True,
        )
        for entry in items:
            entry.pop("_sort_datetime", None)

        return {"items": items}

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "section_name": self.normalization.normalized_section_name or self.canonical_name,
            "items": data.get("items", []),
        }

    def _parse_dated_item(
        self,
        item: ClinicalItem,
        reference_datetime: datetime | None,
    ) -> dict[str, Any] | None:
        if item.state:
            clinical_date = self._parse_date_text(item.state, reference_datetime)
            if clinical_date is None:
                return None
            hora = item.key.strip() if item.key else None
            sort_datetime = _combine_date_time(clinical_date, hora)
            return {
                "data": clinical_date.value.date().isoformat(),
                "hora": hora,
                "conteudo": self._item_text(item),
                "raw_text": item.raw_text,
                "_sort_datetime": sort_datetime,
            }

        clinical_date = item.date if isinstance(item.date, ClinicalDate) else self._parse_date_text(item.key or "", reference_datetime)
        if clinical_date is None:
            return None
        return {
            "data": clinical_date.value.date().isoformat(),
            "hora": None,
            "conteudo": self._item_text(item),
            "raw_text": item.raw_text,
            "_sort_datetime": clinical_date.value,
        }

    def _item_text(self, item: ClinicalItem) -> str:
        parts = [value.value for value in item.values if value.value]
        for child in item.children:
            child_parts = []
            if child.key:
                child_parts.append(child.key)
            child_parts.extend(value.value for value in child.values if value.value)
            if child_parts:
                parts.append(": ".join(child_parts[:2]) if len(child_parts) == 2 else " ".join(child_parts))
        return " ".join(part.strip() for part in parts if part.strip()).strip()

    def _parse_date_text(self, text: str | None, reference_datetime: datetime | None) -> ClinicalDate | None:
        if not text:
            return None
        diagnostics: list[CompilerDiagnostic] = []
        return parse_clinical_date(
            text.strip(),
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
        )

    def _has_item_date(self, item: ClinicalItem, reference_datetime: datetime | None) -> bool:
        if isinstance(item.date, ClinicalDate):
            return True
        return item.key is not None and self._parse_date_text(item.key, reference_datetime) is not None

    def _is_group_heading(self, item: ClinicalItem) -> bool:
        return (
            item.key is not None
            and item.date is None
            and item.state is None
            and not item.values
            and not item.children
        )

    def _suppress_group_heading_diagnostics(self, section: ClinicalSection, document: ClinicalDocument) -> None:
        group_headings = {
            (item.line, item.raw_text)
            for item in section.items
            if self._is_group_heading(item)
        }
        if not group_headings:
            return

        document.diagnostics[:] = [
            diagnostic
            for diagnostic in document.diagnostics
            if not (
                diagnostic.code == "empty_item_value"
                and diagnostic.section == section.section_name
                and (diagnostic.line, diagnostic.raw_text) in group_headings
            )
        ]

    def _code_prefix(self) -> str:
        return _strip_accents(normalize_name(self.canonical_name)).replace(" ", "_")


class ExamKeyValueSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="EXAM",
        accepted_names=("EXAM",),
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
        allow_free_text=False,
        require_key=True,
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
        self._suppress_group_heading_diagnostics(section, document)

        diagnostics: list[CompilerDiagnostic] = []
        if self.section_parser.required_section_value and not section.section_value:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code=self.associated_errors.missing_section_value,
                    message=f"Seção {section.section_name} exige section_value após `:`.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )
        diagnostics.extend(self.validate_subsections(section))

        for item in section.items:
            if self._is_group_heading(item):
                continue

            parsed = self._parse_exam_item(item, document.reference_datetime)
            if parsed.get("_date") is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code=f"{self._code_prefix()}_date_required",
                        message=f"Item de {section.section_name} deve conter data explícita no item ou na subseção.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )
            if not parsed.get("chave"):
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code=self.associated_errors.item_key_required,
                        message=f"Item da seção {section.section_name} exige chave explícita antes de `:`.",
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
        items: list[dict[str, Any]] = []

        for item in section.items:
            if self._is_group_heading(item):
                continue

            parsed = self._parse_exam_item(item, document.reference_datetime)
            clinical_date = parsed.pop("_date", None)
            if clinical_date is None or not parsed.get("chave"):
                continue

            parsed["data"] = clinical_date.value.date().isoformat()
            items.append(parsed)

        return {"items": items}

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "section_name": self.normalization.normalized_section_name or self.canonical_name,
            "items": data.get("items", []),
        }

    def _parse_exam_item(
        self,
        item: ClinicalItem,
        reference_datetime: datetime | None,
    ) -> dict[str, Any]:
        clinical_date = self._item_date(item, reference_datetime)
        subcategory = self._subcategory(item, reference_datetime)
        text, origem = self._strip_leading_date_prefix(item.raw_text, reference_datetime)
        colon = find_structural_colon(text)

        if colon is None:
            key_text = ""
            value_text = text
        else:
            key_text = text[:colon]
            value_text = text[colon + 1 :]

        key, key_comments = extract_parenthesized_values(key_text)
        value, value_comments = extract_parenthesized_values(value_text)
        key = normalize_spaces(key)
        value = normalize_spaces(value)

        return {
            "_date": clinical_date,
            "subcategoria": subcategory,
            "origem": origem,
            "chave": key,
            "valor": value,
            "conteudo": f"{key}: {value}".strip(": ") if key or value else "",
            "comentarios_chave": key_comments,
            "comentarios_valor": value_comments,
            "raw_text": item.raw_text,
        }

    def _item_date(self, item: ClinicalItem, reference_datetime: datetime | None) -> ClinicalDate | None:
        if isinstance(item.date, ClinicalDate):
            return item.date
        return self._parse_date_text(item.state, reference_datetime)

    def _subcategory(self, item: ClinicalItem, reference_datetime: datetime | None) -> str | None:
        if not item.state:
            return None
        if self._parse_date_text(item.state, reference_datetime) is not None:
            return None
        return item.state

    def _strip_leading_date_prefix(
        self,
        text: str,
        reference_datetime: datetime | None,
    ) -> tuple[str, str | None]:
        match = _LEADING_PARENTHESIZED_DATE_RE.match(text)
        if match is None:
            return text.strip(), None

        inside = match.group("inside").strip()
        date_text, separator, detail = inside.partition("-")
        if self._parse_date_text(date_text.strip(), reference_datetime) is None:
            return text.strip(), None

        origem = normalize_spaces(detail) if separator and detail.strip() else None
        return text[match.end() :].strip(), origem

    def _parse_date_text(self, text: str | None, reference_datetime: datetime | None) -> ClinicalDate | None:
        if not text:
            return None
        diagnostics: list[CompilerDiagnostic] = []
        return parse_clinical_date(
            text.strip(),
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
        )

    def _is_group_heading(self, item: ClinicalItem) -> bool:
        return (
            item.key is not None
            and item.date is None
            and item.state is None
            and not item.values
            and not item.children
        )

    def _suppress_group_heading_diagnostics(self, section: ClinicalSection, document: ClinicalDocument) -> None:
        group_headings = {
            (item.line, item.raw_text)
            for item in section.items
            if self._is_group_heading(item)
        }
        if not group_headings:
            return

        document.diagnostics[:] = [
            diagnostic
            for diagnostic in document.diagnostics
            if not (
                diagnostic.code == "empty_item_value"
                and diagnostic.section == section.section_name
                and (diagnostic.line, diagnostic.raw_text) in group_headings
            )
        ]

    def _code_prefix(self) -> str:
        return _strip_accents(normalize_name(self.canonical_name)).replace(" ", "_")


class ExamesLaboratoriaisSection(ExamKeyValueSection):
    section_parser = SectionParserConfig(
        canonical_name="EXAMES LABORATORIAIS",
        accepted_names=("EXAMES LABORATORIAIS", "EXAME LABORATORIAL", "EXAMES", "EXAME COMPLEMENTAR"),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="EXAMES LABORATORIAIS")
    associated_errors = AssociatedErrorsConfig(
        missing_required_section="exames_laboratoriais_missing_section",
        free_text_not_allowed="exames_laboratoriais_free_text_not_allowed",
        item_key_required="exames_laboratoriais_item_key_required",
    )


class ExamesImagemSection(ExamKeyValueSection):
    section_parser = SectionParserConfig(
        canonical_name="EXAMES DE IMAGEM",
        accepted_names=("EXAMES DE IMAGEM", "EXAME DE IMAGEM"),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="EXAMES DE IMAGEM")
    associated_errors = AssociatedErrorsConfig(
        missing_required_section="exames_de_imagem_missing_section",
        free_text_not_allowed="exames_de_imagem_free_text_not_allowed",
        item_key_required="exames_de_imagem_item_key_required",
    )


class IntercorrenciasSection(DatedClinicalSection):
    section_parser = SectionParserConfig(
        canonical_name="INTERCORRÊNCIAS",
        accepted_names=("INTERCORRÊNCIAS", "INTERCORRENCIAS", "INTERCORRÊNCIA", "INTERCORRENCIA", "EVOLUÇÃO", "EVOLUCAO"),
        required=True,
    )
    normalization = NormalizationConfig(normalized_section_name="INTERCORRÊNCIAS")
    associated_errors = AssociatedErrorsConfig(
        missing_required_section="intercorrencias_missing_section",
        free_text_not_allowed="intercorrencias_free_text_not_allowed",
        item_key_required="intercorrencias_item_key_required",
    )


_TIME_KEY_RE = re.compile(r"\d{1,2}:\d{2}")
_LEADING_PARENTHESIZED_DATE_RE = re.compile(r"^\s*\((?P<inside>[^)]*)\)\s*:?\s*")


def _combine_date_time(clinical_date: ClinicalDate, hora: str | None) -> datetime:
    if not hora:
        return clinical_date.value
    hour_text, minute_text = hora.split(":", maxsplit=1)
    return clinical_date.value.replace(hour=int(hour_text), minute=int(minute_text))


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
