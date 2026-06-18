from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
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
class ParsedDiagnosis:
    raw_text: str
    diagnostico: str
    cid: str | None = None
    cid_version: str | None = None
    data: ClinicalDate | ClinicalDatePeriod | None = None
    estado: str = "Ativo"
    commented_values: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "cid": self.cid,
            "cid_version": self.cid_version,
            "diagnostico": self.diagnostico,
            "data": self.data,
            "estado": self.estado,
            "commented_values": self.commented_values or [],
        }


class DiagnosticoSection(BaseSpecificSectionParser):
    """Parser especifico da secao DIAGNOSTICO."""

    STATE_ALIASES = {
        "ativo": "Ativo",
        "ativa": "Ativo",
        "atual": "Ativo",
        "em tratamento": "Em tratamento",
        "tratando": "Em tratamento",
        "tratamento": "Em tratamento",
        "tratado": "Tratado",
        "tratada": "Tratado",
        "investigacao": "Investigação",
        "investigação": "Investigação",
        "investigando": "Investigação",
        "?": "Investigação",
    }

    section_parser = SectionParserConfig(
        canonical_name="DIAGNÓSTICO",
        accepted_names=(
            "DIAGNÓSTICO",
            "DIAGNOSTICO",
            "DIAGNÓSTICOS",
            "DIAGNOSTICOS",
            "HIPÓTESE DIAGNÓSTICA",
            "HIPOTESE DIAGNOSTICA",
            "HIPÓTESES DIAGNÓSTICAS",
            "HIPOTESES DIAGNOSTICAS",
        ),
        required=True,
        required_section_value=False,
    )

    subsection_parser = SubsectionParserConfig(
        default_subsections=("Ativo", "Em tratamento", "Tratado", "Investigação"),
        required_subsections=(),
        allow_new=False,
        inline_states=(
            "ativo",
            "ativa",
            "atual",
            "em tratamento",
            "tratando",
            "tratamento",
            "tratado",
            "tratada",
            "investigação",
            "investigacao",
            "investigando",
            "?",
        ),
        use_default_subsections_as_inline_states=True,
    )

    item_parser = ItemParserConfig(
        allow_free_text=True,
        require_key=False,
        allow_children=False,
    )

    normalization = NormalizationConfig(
        normalized_section_name="DIAGNÓSTICO",
    )

    associated_errors = AssociatedErrorsConfig(
        missing_required_section="diagnostico_missing_section",
        unknown_subsection="diagnostico_unknown_subsection",
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

        for item in section.items:
            diagnostics.extend(self._validate_diagnosis_item(item, section))

        return diagnostics

    def parse_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
        diagnostics: list[CompilerDiagnostic],
    ) -> dict[str, Any]:
        return {
            "items": [self._parse_diagnosis_item(item, section).to_dict() for item in section.items],
        }

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        return {
            "section_name": self.normalization.normalized_section_name,
            "items": [
                {
                    "cid": item.get("cid"),
                    "diagnostico": item.get("diagnostico"),
                    "data": self._format_date(item.get("data")),
                    "estado": item.get("estado"),
                }
                for item in data.get("items", [])
                if isinstance(item, dict)
            ],
        }

    def _validate_diagnosis_item(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
    ) -> list[CompilerDiagnostic]:
        diagnostics: list[CompilerDiagnostic] = []
        parsed = self._parse_diagnosis_item(item, section)

        if item.key is not None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="diagnostico_key_value_not_allowed",
                    message="Itens de DIAGNÓSTICO devem ser texto livre, sem `key: value`.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        if not parsed.diagnostico:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="diagnostico_missing_diagnosis",
                    message="Item de DIAGNÓSTICO precisa conter o texto do diagnóstico.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        invalid_cid = self._invalid_cid_candidate(item)
        if invalid_cid is not None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="diagnostico_possible_invalid_cid",
                    message=f"'{invalid_cid}' é um CID? Se for, confira o formato.",
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
                    code="diagnostico_multiple_states_for_item",
                    message="Item de DIAGNÓSTICO possui estado por subseção e estado inline.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        if isinstance(item.date, ClinicalDatePeriod) and parsed.estado != "Tratado":
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="diagnostico_date_period_only_for_treated",
                    message="Data em período só é permitida para diagnóstico tratado.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        if isinstance(item.date, ClinicalDate) and parsed.estado == "Tratado":
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="diagnostico_treated_date_should_be_period",
                    message="Diagnóstico tratado com data deve usar período.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )

        return diagnostics

    def _parse_diagnosis_item(self, item: ClinicalItem, section: ClinicalSection) -> ParsedDiagnosis:
        text = self._item_text(item)
        cid, cid_version = self._parse_cid(text)
        if cid is not None:
            text = _remove_token(text, cid)

        subsection_state = self._state_from_subsection_context(item, section)
        inline_state = self._inline_state_from_item(item, subsection_state=subsection_state)
        estado = inline_state or subsection_state or "Ativo"
        if inline_state is not None:
            text = self._remove_inline_state(text)

        diagnostico = _normalize_spaces(text)

        return ParsedDiagnosis(
            raw_text=item.raw_text,
            cid=cid,
            cid_version=cid_version,
            diagnostico=diagnostico,
            data=item.date,
            estado=estado,
            commented_values=item.commented_values,
        )

    def _item_text(self, item: ClinicalItem) -> str:
        values = [value.value for value in item.values if value.value]
        if item.key is not None:
            values.insert(0, item.key)
        return _normalize_spaces(" ".join(values))

    def _parse_cid(self, text: str) -> tuple[str | None, str | None]:
        match = _CID_RE.match(text)
        if match is None:
            return None, None

        cid = match.group(0).upper()
        version = "CID-11" if _ICD11_RE.fullmatch(cid) else "CID-10"
        return cid, version

    def _invalid_cid_candidate(self, item: ClinicalItem) -> str | None:
        text = self._item_text(item)
        first = text.split(maxsplit=1)[0] if text else ""
        if not first or self._parse_cid(first)[0] is not None:
            return None
        if _POSSIBLE_CID_RE.fullmatch(first.upper()):
            return first
        return None

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

        inline_text_state = self._inline_state_from_text(self._item_text(item))
        if inline_text_state is not None:
            return inline_text_state

        raw_text_state = self._inline_state_from_text(item.raw_text)
        if raw_text_state is not None and raw_text_state == item_state:
            return raw_text_state

        return None

    def _inline_state_from_text(self, text: str) -> str | None:
        if "?" in text:
            return "Investigação"

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
        text = text.replace("?", " ")
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


_ICD10_RE = re.compile(r"[A-Z][0-9]{2}(?:\.[0-9])?", flags=re.IGNORECASE)
_ICD11_RE = re.compile(
    r"[1-9A-HJ-NP-Z][A-HJ-NP-Z][0-9][0-9A-HJ-NP-Z](?:\.[0-9A-HJ-NP-Z]{1,2})?",
    flags=re.IGNORECASE,
)
_CID_RE = re.compile(rf"(?:{_ICD10_RE.pattern}|{_ICD11_RE.pattern})(?=\s|$)", flags=re.IGNORECASE)
_POSSIBLE_CID_RE = re.compile(r"[A-Z0-9][A-Z0-9.]{2,}")

_SORTED_STATE_ALIASES = sorted(
    DiagnosticoSection.STATE_ALIASES.items(),
    key=lambda item: len(item[0]),
    reverse=True,
)


def _remove_token(text: str, token: str) -> str:
    return _normalize_spaces(text[len(token) :]) if text.upper().startswith(token.upper()) else text


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
