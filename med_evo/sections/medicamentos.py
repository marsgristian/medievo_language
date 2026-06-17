from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from med_evo.models import (
    ClinicalDate,
    ClinicalDatePeriod,
    ClinicalDocument,
    ClinicalItem,
    ClinicalSection,
    CompilerDiagnostic,
)
from med_evo.sections.base import (
    AssociatedErrorsConfig,
    BaseSpecificSectionParser,
    ItemParserConfig,
    NormalizationConfig,
    SectionParserConfig,
    SubsectionParserConfig,
    normalize_name,
)
from med_evo.minimal.dates import parse_clinical_date
from med_evo.minimal.text import find_structural_colon, split_top_level


@dataclass(frozen=True, slots=True)
class ParsedMedication:
    raw_text: str
    nome: str
    dose: str | None = None
    intervalo: str | None = None
    data: ClinicalDate | ClinicalDatePeriod | None = None
    estado: str = "Ativo"
    extras: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "nome": self.nome,
            "dose": self.dose,
            "intervalo": self.intervalo,
            "data": self.data,
            "estado": self.estado,
            "extras": self.extras or [],
        }


class MedicamentosSection(BaseSpecificSectionParser):
    """Parser especifico da secao MEDICAMENTOS."""

    STATE_ALIASES = {
        "ativo": "Ativo",
        "ativa": "Ativo",
        "atual": "Ativo",
        "suspenso": "Suspenso",
        "suspensa": "Suspenso",
        "fez uso": "Suspenso",
        "anterior": "Suspenso",
        "inativo": "Suspenso",
        "inativa": "Suspenso",
    }

    section_parser = SectionParserConfig(
        canonical_name="MEDICAMENTOS",
        accepted_names=(
            "MEDICAMENTOS",
            "MEDICAÇÕES",
            "MEDICACOES",
            "MEDICAMENTO",
        ),
        required=True,
        required_section_value=False,
    )

    subsection_parser = SubsectionParserConfig(
        default_subsections=("Ativo", "Suspenso"),
        required_subsections=(),
        allow_new=False,
        inline_states=(
            "ativo",
            "ativa",
            "atual",
            "suspenso",
            "suspensa",
            "fez uso",
            "anterior",
            "inativo",
            "inativa",
        ),
        use_default_subsections_as_inline_states=True,
    )

    item_parser = ItemParserConfig(
        allow_free_text=False,
        require_key=True,
        allow_children=True,
    )

    normalization = NormalizationConfig(
        normalized_section_name="MEDICAMENTOS",
    )

    associated_errors = AssociatedErrorsConfig(
        missing_required_section="medicamentos_missing_section",
        free_text_not_allowed="medicamentos_free_text_not_allowed",
        item_key_required="medicamentos_item_key_required",
        unknown_subsection="medicamentos_unknown_subsection",
    )

    def matches(self, section_name: str) -> bool:
        normalized = _strip_accents(normalize_name(section_name))
        accepted = {_strip_accents(normalize_name(name)) for name in self.accepted_names}
        return normalized in accepted

    def validate_subsections(self, section: ClinicalSection) -> list[CompilerDiagnostic]:
        diagnostics: list[CompilerDiagnostic] = []
        allowed = {_strip_accents(normalize_name(name)) for name in self.subsection_parser.default_subsections}
        allowed.update(_strip_accents(normalize_name(alias)) for alias in self.STATE_ALIASES)

        for sub in section.states:
            if _strip_accents(normalize_name(sub.subsec_name)) not in allowed:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="warning",
                        code=self.associated_errors.unknown_subsection,
                        message=f"Subseção não prevista em {section.section_name}: {sub.subsec_name}.",
                        phase="semantic",
                        line=sub.line,
                        section=section.section_name,
                        raw_text=sub.raw_text,
                    )
                )

        return diagnostics

    def validate_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
    ) -> list[CompilerDiagnostic]:
        diagnostics = super().validate_section(section, document)

        if not section.items and not self._section_says_no_medications(section):
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="medicamentos_empty_without_explicit_marker",
                    message="Seção MEDICAMENTOS vazia sem marcador explícito como `sem medicamentos`.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )

        for item in section.items:
            diagnostics.extend(self._validate_medication_item(item, section, document))

        return diagnostics

    def parse_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
        diagnostics: list[CompilerDiagnostic],
    ) -> dict[str, Any]:
        return {
            "sem_medicamentos": self._section_says_no_medications(section),
            "items": [
                self._parse_medication_item(item, section, document.reference_datetime).to_dict()
                for item in section.items
            ],
        }

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        return {
            "section_name": self.normalization.normalized_section_name,
            "sem_medicamentos": data.get("sem_medicamentos", False),
            "items": [
                {
                    "nome": item.get("nome"),
                    "dose": item.get("dose"),
                    "intervalo": item.get("intervalo"),
                    "data": self._format_date(item.get("data")),
                    "estado": item.get("estado"),
                    "extras": item.get("extras", []),
                }
                for item in data.get("items", [])
                if isinstance(item, dict)
            ],
        }

    def _validate_medication_item(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
        document: ClinicalDocument,
    ) -> list[CompilerDiagnostic]:
        diagnostics: list[CompilerDiagnostic] = []
        parsed = self._parse_medication_item(item, section, document.reference_datetime)

        if item.key is None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="medicamentos_key_value_required",
                    message="Itens de MEDICAMENTOS devem usar `medicamento: valores`.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        subsection_state = self._state_from_subsection_context(item, section)
        inline_state = self._inline_state_from_item(item, subsection_state=subsection_state)
        if subsection_state is not None and inline_state is not None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="medicamentos_multiple_states_for_item",
                    message="Item de MEDICAMENTOS possui estado por subseção e estado inline.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        if parsed.intervalo is None and not parsed.extras:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="medicamentos_missing_interval_or_extra",
                    message="Medicamento sem intervalo ou mais informações.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        if parsed.estado == "Suspenso":
            if parsed.data is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="medicamentos_suspended_missing_period",
                        message="Medicamento suspenso deve informar o período de uso.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )
            elif isinstance(parsed.data, ClinicalDate):
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="warning",
                        code="medicamentos_suspended_date_should_be_period",
                        message="Medicamento suspenso com data deve usar período de uso.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )

        return diagnostics

    def _parse_medication_item(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
        reference_datetime: datetime | None,
    ) -> ParsedMedication:
        nome = _normalize_spaces(item.key or "")
        values = self._value_texts(item)

        dose: str | None = None
        intervalo: str | None = None
        data: ClinicalDate | ClinicalDatePeriod | None = None
        extras: list[str] = []

        subsection_state = self._state_from_subsection_context(item, section)
        inline_state = self._inline_state_from_item(item, subsection_state=subsection_state)
        estado = inline_state or subsection_state or "Ativo"

        for value in values:
            has_date_marker = self._has_date_marker(value)
            clean = self._strip_date_marker(value)
            clean = self._remove_inline_state(clean)
            if not clean:
                continue

            if has_date_marker and data is None:
                parsed_date, remainder = self._extract_medication_date(
                    clean,
                    reference_datetime=reference_datetime,
                    item=item,
                    section=section,
                )
                if parsed_date is not None:
                    data = parsed_date
                    if remainder:
                        extras.append(remainder)
                    continue

            if dose is None and _DOSE_RE.search(clean):
                dose = _DOSE_RE.search(clean).group(0)  # type: ignore[union-attr]
                remainder = _normalize_spaces(_DOSE_RE.sub(" ", clean, count=1))
                if remainder:
                    extras.append(remainder)
                continue

            if intervalo is None and _INTERVAL_RE.search(clean):
                intervalo = _INTERVAL_RE.search(clean).group(0)  # type: ignore[union-attr]
                remainder = _normalize_spaces(_INTERVAL_RE.sub(" ", clean, count=1))
                if remainder:
                    extras.append(remainder)
                continue

            if data is None:
                parsed_date, remainder = self._extract_medication_date(
                    clean,
                    reference_datetime=reference_datetime,
                    item=item,
                    section=section,
                )
                if parsed_date is not None:
                    data = parsed_date
                    if remainder:
                        extras.append(remainder)
                    continue

            extras.append(clean)

        return ParsedMedication(
            raw_text=item.raw_text,
            nome=nome,
            dose=dose,
            intervalo=intervalo,
            data=data,
            estado=estado,
            extras=extras,
        )

    def _value_texts(self, item: ClinicalItem) -> list[str]:
        raw_values = self._raw_value_texts(item)
        if raw_values:
            return raw_values

        values = [value.value for value in item.values if value.value]
        values.extend(value for value in item.commented_values if value)

        for child in item.children:
            values.append(self._child_text(child))

        return [_normalize_spaces(value) for value in values if _normalize_spaces(value)]

    def _raw_value_texts(self, item: ClinicalItem) -> list[str]:
        colon = find_structural_colon(item.raw_text)
        if colon is None:
            return []

        value_text = item.raw_text[colon + 1 :]
        return [
            _normalize_spaces(value)
            for value in split_top_level(value_text, ";")
            if _normalize_spaces(value)
        ]

    def _child_text(self, item: ClinicalItem) -> str:
        parts: list[str] = []
        if item.key:
            parts.append(item.key)
        parts.extend(value.value for value in item.values if value.value)
        parts.extend(item.commented_values)
        return _normalize_spaces(" ".join(parts))

    def _section_says_no_medications(self, section: ClinicalSection) -> bool:
        value = section.section_value or ""
        normalized = _strip_accents(normalize_name(value))
        return normalized in {
            "sem medicamentos",
            "sem medicacoes",
            "sem medicacao",
            "sem uso",
        }

    def _state_from_subsection_context(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
    ) -> str | None:
        if item.line is None:
            return self._canonical_state(item.state)

        active_state: str | None = None
        for subsection in section.states:
            if subsection.line is not None and subsection.line <= item.line:
                active_state = subsection.subsec_name

        return self._canonical_state(active_state)

    def _inline_state_from_item(
        self,
        item: ClinicalItem,
        *,
        subsection_state: str | None,
    ) -> str | None:
        item_state = self._canonical_state(item.state)
        if item_state is not None and (subsection_state is None or item_state != subsection_state):
            return item_state

        raw_text_state = self._inline_state_from_text(item.raw_text)
        if raw_text_state is not None and raw_text_state == item_state:
            return raw_text_state

        return self._inline_state_from_text(" ".join(self._value_texts(item)))

    def _inline_state_from_text(self, text: str) -> str | None:
        normalized = _strip_accents(normalize_name(text))
        for alias, canonical in _SORTED_STATE_ALIASES:
            normalized_alias = _strip_accents(normalize_name(alias))
            if normalized == normalized_alias:
                return canonical
            if normalized.startswith(normalized_alias + " "):
                return canonical
            if normalized.endswith(" " + normalized_alias):
                return canonical
        return None

    def _remove_inline_state(self, text: str) -> str:
        for alias, _canonical in _SORTED_STATE_ALIASES:
            text = _remove_edge_phrase(text, alias)
        return _normalize_spaces(text)

    def _canonical_state(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _strip_accents(normalize_name(value))
        for alias, canonical in self.STATE_ALIASES.items():
            if normalized == _strip_accents(normalize_name(alias)):
                return canonical
        return None

    def _has_date_marker(self, value: str) -> bool:
        return re.search(r"\bD[Ii]\b\.?", value) is not None

    def _strip_date_marker(self, value: str) -> str:
        return _normalize_spaces(re.sub(r"\bD[Ii]\b\.?\s*", " ", value))

    def _extract_medication_date(
        self,
        value: str,
        *,
        reference_datetime: datetime | None,
        item: ClinicalItem,
        section: ClinicalSection,
    ) -> tuple[ClinicalDate | ClinicalDatePeriod | None, str]:
        period_match = _DATE_PERIOD_RE.search(value)
        if period_match is not None:
            start_text = period_match.group("start")
            end_text = period_match.group("end")
            parsed_period = self._parse_date_period(
                period_match.group(0),
                start_text,
                end_text,
                reference_datetime=reference_datetime,
                item=item,
                section=section,
            )
            if parsed_period is not None:
                return parsed_period, _normalize_spaces(
                    value[: period_match.start()] + " " + value[period_match.end() :]
                )

        day_period_match = _DAY_DATE_PERIOD_RE.search(value)
        if day_period_match is not None:
            end_text = day_period_match.group("end")
            end_parts = end_text.split("/", maxsplit=2)
            start_text = f"{day_period_match.group('start_day')}/{end_parts[1]}"
            if len(end_parts) == 3:
                start_text = f"{start_text}/{end_parts[2]}"
            parsed_period = self._parse_date_period(
                day_period_match.group(0),
                start_text,
                end_text,
                reference_datetime=reference_datetime,
                item=item,
                section=section,
            )
            if parsed_period is not None:
                return parsed_period, _normalize_spaces(
                    value[: day_period_match.start()] + " " + value[day_period_match.end() :]
                )

        date_match = _DATE_RE.search(value)
        if date_match is None:
            return None, value

        diagnostics: list[CompilerDiagnostic] = []
        parsed_date = parse_clinical_date(
            date_match.group("date"),
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
            line=item.line,
            section=section.section_name,
        )
        if parsed_date is None:
            return None, value

        return parsed_date, _normalize_spaces(value[: date_match.start()] + " " + value[date_match.end() :])

    def _parse_date_period(
        self,
        raw_text: str,
        start_text: str,
        end_text: str,
        *,
        reference_datetime: datetime | None,
        item: ClinicalItem,
        section: ClinicalSection,
    ) -> ClinicalDatePeriod | None:
        diagnostics: list[CompilerDiagnostic] = []
        start = parse_clinical_date(
            start_text,
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
            line=item.line,
            section=section.section_name,
        )
        end = parse_clinical_date(
            end_text,
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
            line=item.line,
            section=section.section_name,
        )
        if start is None or end is None:
            return None

        return ClinicalDatePeriod(
            raw_text=raw_text,
            start=start,
            end=end,
            delta_time=end.value - start.value,
        )

    def _format_date(self, value: Any) -> Any:
        if isinstance(value, ClinicalDate):
            return value.value.isoformat(timespec="minutes")

        if isinstance(value, ClinicalDatePeriod):
            return {
                "start": value.start.value.isoformat(timespec="minutes"),
                "end": value.end.value.isoformat(timespec="minutes"),
            }

        if isinstance(value, datetime):
            return value.isoformat(timespec="minutes")

        return None


_NUMBER_RE = r"\d+(?:[,.]\d+)?"
_UNIT_RE = r"(?:mcg|µg|ug|mg|g|ml|mL|gotas?|gts?|UI|U)"
_DOSE_RE = re.compile(
    rf"\b{_NUMBER_RE}\s*{_UNIT_RE}(?:\s*/\s*kg)?(?:\s*/\s*dose)?\b",
    flags=re.IGNORECASE,
)
_INTERVAL_RE = re.compile(
    r"\b(?:[1-9]\d?\s*/\s*[1-9]\d?\s*h|[1-9]\d?\s*/\s*[1-9]\d?|\d+\s*x\s*/\s*dia|\d+\s*/\s*dia)\b",
    flags=re.IGNORECASE,
)
_DATE_TEXT = r"\d{1,2}/\d{1,2}(?:/\d{2,4})?"
_DATE_PERIOD_RE = re.compile(
    rf"(?<!\d)(?P<start>{_DATE_TEXT})\s*-\s*(?P<end>{_DATE_TEXT})(?![\dh])",
    flags=re.IGNORECASE,
)
_DAY_DATE_PERIOD_RE = re.compile(
    rf"(?<!\d)(?P<start_day>\d{{1,2}})\s*-\s*(?P<end>{_DATE_TEXT})(?![\dh])",
    flags=re.IGNORECASE,
)
_DATE_RE = re.compile(rf"(?<!\d)(?P<date>{_DATE_TEXT})(?![\dh])", flags=re.IGNORECASE)

_SORTED_STATE_ALIASES = sorted(
    MedicamentosSection.STATE_ALIASES.items(),
    key=lambda item: len(item[0]),
    reverse=True,
)


def _remove_edge_phrase(text: str, phrase: str) -> str:
    normalized_text = _strip_accents(normalize_name(text))
    normalized_phrase = _strip_accents(normalize_name(phrase))

    if normalized_text == normalized_phrase:
        return ""

    if normalized_text.startswith(normalized_phrase + " "):
        return _normalize_spaces(text[len(phrase) :])

    if normalized_text.endswith(" " + normalized_phrase):
        return _normalize_spaces(text[: -len(phrase)])

    return text


def _normalize_spaces(text: str) -> str:
    return " ".join(text.strip().split())


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
