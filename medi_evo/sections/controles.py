from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from medi_evo.models import (
    ClinicalDate,
    ClinicalDatePeriod,
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


@dataclass(frozen=True, slots=True)
class ParsedControl:
    raw_text: str
    chave: str
    tipo: str
    min: float | None = None
    max: float | None = None
    medicao: float | str | None = None
    unidade: str | None = None
    data: ClinicalDate | None = None
    periodo: ClinicalDatePeriod | str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "chave": self.chave,
            "tipo": self.tipo,
            "min": self.min,
            "max": self.max,
            "medicao": self.medicao,
            "unidade": self.unidade,
            "data": self.data,
            "periodo": self.periodo,
        }


class ControlesSection(BaseSpecificSectionParser):
    """Parser especifico da secao CONTROLES / SINAIS VITAIS."""

    section_parser = SectionParserConfig(
        canonical_name="CONTROLES",
        accepted_names=("CONTROLES", "SINAIS VITAIS"),
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
        allow_children=False,
    )

    normalization = NormalizationConfig(
        normalized_section_name="CONTROLES",
    )

    associated_errors = AssociatedErrorsConfig(
        missing_required_section="controles_missing_section",
        free_text_not_allowed="controles_free_text_not_allowed",
        item_key_required="controles_item_key_required",
        unknown_subsection="controles_unknown_subsection",
    )

    def validate_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
    ) -> list[CompilerDiagnostic]:
        diagnostics = super().validate_section(section, document)

        for item in section.items:
            parsed = self._parse_control(item)
            if item.key is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="controles_key_value_required",
                        message="Itens de CONTROLES devem usar `chave: valor`.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )
                continue

            if parsed.tipo == "invalid":
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="controles_invalid_item",
                        message="Controle deve ser numérico, básico com data, ou textual unitário.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )

            if parsed.tipo in {"basico", "textual"} and parsed.data is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="controles_basic_date_required",
                        message="Controle básico ou textual deve conter data.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )

            if parsed.tipo in {"numerico", "basico"} and parsed.unidade is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="warning",
                        code="controles_missing_unit",
                        message="Controle numérico sem unidade; confira se isso é intencional.",
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
        return {
            "items": [self._parse_control(item).to_dict() for item in section.items],
        }

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        return {
            "section_name": self.normalization.normalized_section_name,
            "items": [
                {
                    **item,
                    "data": self._format_date(item.get("data")),
                    "periodo": self._format_period(item.get("periodo")),
                }
                for item in data.get("items", [])
                if isinstance(item, dict)
            ],
        }

    def _parse_control(self, item: ClinicalItem) -> ParsedControl:
        chave = item.key or ""
        text = self._item_value_text(item)

        range_match = _RANGE_RE.search(text)
        if range_match is not None:
            unidade = self._unit_after(text, range_match.end())
            return ParsedControl(
                raw_text=item.raw_text,
                chave=chave,
                tipo="numerico",
                min=_parse_number(range_match.group("min")),
                max=_parse_number(range_match.group("max")),
                unidade=unidade,
                periodo=item.date if isinstance(item.date, ClinicalDatePeriod) else "ultimas_24h",
            )

        if item.date is not None:
            numeric_match = _LEADING_NUMBER_RE.search(text)
            if numeric_match is not None:
                unidade = self._unit_after(text, numeric_match.end())
                return ParsedControl(
                    raw_text=item.raw_text,
                    chave=chave,
                    tipo="basico",
                    medicao=_parse_number(numeric_match.group("number")),
                    unidade=unidade,
                    data=item.date if isinstance(item.date, ClinicalDate) else None,
                )

            return ParsedControl(
                raw_text=item.raw_text,
                chave=chave,
                tipo="textual",
                medicao=text,
                data=item.date if isinstance(item.date, ClinicalDate) else None,
            )

        if self._is_textual_unit(text):
            return ParsedControl(
                raw_text=item.raw_text,
                chave=chave,
                tipo="textual",
                medicao=text,
            )

        numeric_match = _LEADING_NUMBER_RE.search(text)
        if numeric_match is not None:
            unidade = self._unit_after(text, numeric_match.end())
            return ParsedControl(
                raw_text=item.raw_text,
                chave=chave,
                tipo="basico",
                medicao=_parse_number(numeric_match.group("number")),
                unidade=unidade,
            )

        return ParsedControl(raw_text=item.raw_text, chave=chave, tipo="invalid", medicao=text)

    def _item_value_text(self, item: ClinicalItem) -> str:
        return " ".join(value.value for value in item.values if value.value).strip()

    def _unit_after(self, text: str, start: int) -> str | None:
        trailing = text[start:].strip()
        if not trailing:
            return None
        if _DATE_LIKE_RE.search(trailing):
            trailing = _DATE_LIKE_RE.sub(" ", trailing, count=1).strip()
        if not trailing:
            return None
        unit = trailing.split(maxsplit=1)[0]
        return unit or None

    def _is_textual_unit(self, text: str) -> bool:
        return bool(text.strip()) and _LEADING_NUMBER_RE.search(text) is None and _RANGE_RE.search(text) is None

    def _format_date(self, value: Any) -> str | None:
        if isinstance(value, ClinicalDate):
            return value.value.isoformat(timespec="minutes")
        if isinstance(value, datetime):
            return value.isoformat(timespec="minutes")
        return None

    def _format_period(self, value: Any) -> Any:
        if isinstance(value, ClinicalDatePeriod):
            return {
                "start": value.start.value.isoformat(timespec="minutes"),
                "end": value.end.value.isoformat(timespec="minutes"),
            }
        if isinstance(value, timedelta):
            return str(value)
        return value


_NUMBER = r"\d+(?:[,.]\d+)?"
_RANGE_RE = re.compile(rf"(?P<min>{_NUMBER})\s*-\s*(?P<max>{_NUMBER})")
_LEADING_NUMBER_RE = re.compile(rf"^\s*(?P<number>{_NUMBER})\b")
_DATE_LIKE_RE = re.compile(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?")


def _parse_number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))
