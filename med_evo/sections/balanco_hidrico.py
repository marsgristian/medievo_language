from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from med_evo.models import (
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


@dataclass(frozen=True, slots=True)
class ParsedFluidValue:
    raw_text: str
    value: float | None
    unit: str | None
    sign: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "value": self.value,
            "unit": self.unit,
            "sign": self.sign,
        }


class BalancoHidricoSection(BaseSpecificSectionParser):
    """Parser especifico da secao BALANCO HIDRICO."""

    REQUIRED_KEYS = ("entradas", "saidas", "bh", "diurese")

    section_parser = SectionParserConfig(
        canonical_name="BALANÇO HÍDRICO",
        accepted_names=(
            "BALANÇO HÍDRICO",
            "BALANCO HIDRICO",
        ),
        required=True,
        required_section_value=False,
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

    normalization = NormalizationConfig(
        normalized_section_name="BALANÇO HÍDRICO",
        normalized_item_keys={
            "entradas": "entradas",
            "saidas": "saidas",
            "bh": "bh",
            "diurese": "diurese",
        },
    )

    associated_errors = AssociatedErrorsConfig(
        missing_required_section="balanco_hidrico_missing_section",
        free_text_not_allowed="balanco_hidrico_free_text_not_allowed",
        item_key_required="balanco_hidrico_item_key_required",
    )

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
        parsed = self._parse_balanco(section)

        for required_key in self.REQUIRED_KEYS:
            if required_key == "bh":
                if parsed["bh"] is None and parsed["bh_calculado"] is None:
                    diagnostics.append(self._missing_required_item(section, "BH"))
                continue

            if parsed[required_key] is None:
                diagnostics.append(self._missing_required_item(section, required_key))

        for field_name in ("entradas", "saidas", "bh", "diurese"):
            value = parsed.get(field_name)
            if isinstance(value, ParsedFluidValue) and value.value is None:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="balanco_hidrico_invalid_value",
                        message=f"Valor inválido em {field_name}: {value.raw_text}.",
                        phase="semantic",
                        line=self._line_for_key(section, field_name),
                        section=section.section_name,
                        raw_text=value.raw_text,
                    )
                )

        entradas = parsed["entradas"]
        saidas = parsed["saidas"]
        bh = parsed["bh"]

        if isinstance(bh, ParsedFluidValue) and bh.value is not None and bh.value != 0 and bh.sign is None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="balanco_hidrico_bh_sign_required",
                    message="BH deve conter sinal de + ou - quando diferente de zero.",
                    phase="semantic",
                    line=section.start_line if parsed["bh_source"] == "section_value" else self._line_for_key(section, "bh"),
                    section=section.section_name,
                    raw_text=bh.raw_text,
                )
            )

        if (
            isinstance(entradas, ParsedFluidValue)
            and isinstance(saidas, ParsedFluidValue)
            and entradas.unit is not None
            and saidas.unit is not None
            and entradas.unit != saidas.unit
        ):
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="balanco_hidrico_entry_exit_unit_mismatch",
                    message="Entradas e saídas têm unidades diferentes; BH não será calculado automaticamente.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )

        if (
            isinstance(entradas, ParsedFluidValue)
            and isinstance(saidas, ParsedFluidValue)
            and isinstance(bh, ParsedFluidValue)
            and entradas.unit is not None
            and saidas.unit is not None
            and bh.unit is not None
            and entradas.unit == saidas.unit
            and bh.unit != entradas.unit
        ):
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="balanco_hidrico_bh_unit_mismatch",
                    message="Unidade do BH deve ser a mesma de entradas e saídas.",
                    phase="semantic",
                    line=section.start_line if parsed["bh_source"] == "section_value" else self._line_for_key(section, "bh"),
                    section=section.section_name,
                    raw_text=bh.raw_text,
                )
            )

        if (
            isinstance(entradas, ParsedFluidValue)
            and isinstance(saidas, ParsedFluidValue)
            and isinstance(bh, ParsedFluidValue)
            and entradas.value is not None
            and saidas.value is not None
            and bh.value is not None
            and entradas.unit is not None
            and entradas.unit == saidas.unit
            and bh.unit == entradas.unit
            and round(abs((entradas.value - saidas.value) - bh.value), 1) > 0
        ):
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="balanco_hidrico_bh_discrepant",
                    message="BH discrepante do cálculo, por favor verifique os valores de entradas e saídas.",
                    phase="semantic",
                    line=section.start_line if parsed["bh_source"] == "section_value" else self._line_for_key(section, "bh"),
                    section=section.section_name,
                    raw_text=bh.raw_text,
                )
            )

        if parsed["bh"] is None and parsed["bh_calculado"] is not None:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="warning",
                    code="balanco_hidrico_bh_missing_calculated",
                    message="BH ausente; calculado automaticamente a partir de entradas e saídas.",
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
        parsed = self._parse_balanco(section)
        extras = {
            key: value.to_dict()
            for key, value in parsed["extras"].items()
        }

        return {
            "entradas": self._value_to_dict(parsed["entradas"]),
            "saidas": self._value_to_dict(parsed["saidas"]),
            "bh": self._value_to_dict(parsed["bh"] or parsed["bh_calculado"]),
            "bh_source": parsed["bh_source"] or ("calculated" if parsed["bh_calculado"] is not None else None),
            "diurese": self._value_to_dict(parsed["diurese"]),
            "extras": extras,
        }

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        return {
            "section_name": self.normalization.normalized_section_name,
            "entradas": self._format_value(data.get("entradas")),
            "saidas": self._format_value(data.get("saidas")),
            "bh": self._format_value(data.get("bh")),
            "bh_source": data.get("bh_source"),
            "diurese": self._format_value(data.get("diurese")),
            "extras": {
                key: self._format_value(value)
                for key, value in data.get("extras", {}).items()
            },
        }

    def _parse_balanco(self, section: ClinicalSection) -> dict[str, Any]:
        items_by_key: dict[str, ParsedFluidValue] = {}
        extras: dict[str, ParsedFluidValue] = {}

        for item in section.items:
            canonical_key = self._canonical_key(item.key)
            if canonical_key is None:
                continue

            parsed_value = self._parse_value(self._item_value_text(item), require_bh_sign=canonical_key == "bh")

            if canonical_key in {"entradas", "saidas", "bh", "diurese"}:
                items_by_key[canonical_key] = parsed_value
            else:
                extras[canonical_key] = parsed_value

        section_bh = None
        bh_source = None
        if section.section_value:
            section_bh = self._parse_value(section.section_value, require_bh_sign=True)
            bh_source = "section_value"

        item_bh = items_by_key.get("bh")
        bh = section_bh or item_bh
        if item_bh is not None and section_bh is None:
            bh_source = "item"

        entradas = items_by_key.get("entradas")
        saidas = items_by_key.get("saidas")
        bh_calculado = self._calculate_bh(entradas, saidas)

        return {
            "entradas": entradas,
            "saidas": saidas,
            "bh": bh,
            "bh_source": bh_source,
            "bh_calculado": bh_calculado,
            "diurese": items_by_key.get("diurese"),
            "extras": extras,
        }

    def _calculate_bh(
        self,
        entradas: ParsedFluidValue | None,
        saidas: ParsedFluidValue | None,
    ) -> ParsedFluidValue | None:
        if (
            entradas is None
            or saidas is None
            or entradas.value is None
            or saidas.value is None
            or entradas.unit is None
            or saidas.unit is None
            or entradas.unit != saidas.unit
        ):
            return None

        calculated = entradas.value - saidas.value
        sign = "+" if calculated > 0 else "-" if calculated < 0 else None
        return ParsedFluidValue(
            raw_text=f"{calculated:g} {entradas.unit}",
            value=calculated,
            unit=entradas.unit,
            sign=sign,
        )

    def _parse_value(self, text: str, *, require_bh_sign: bool = False) -> ParsedFluidValue:
        clean = _normalize_spaces(text)
        match = _FLUID_VALUE_RE.search(clean)
        if match is None:
            return ParsedFluidValue(raw_text=clean, value=None, unit=None)

        sign = match.group("sign") or None
        number = float(match.group("number").replace(".", "").replace(",", "."))
        if sign == "-":
            number = -number
        unit = self._canonical_unit(match.group("unit"))
        if require_bh_sign and number == 0:
            sign = None

        return ParsedFluidValue(
            raw_text=clean,
            value=number,
            unit=unit,
            sign=sign,
        )

    def _canonical_unit(self, unit: str) -> str:
        normalized = _strip_accents(unit.strip().lower()).replace(" ", "")
        if normalized == "ml/kg/h":
            return "ml/kg/h"
        return "ml"

    def _canonical_key(self, key: str | None) -> str | None:
        if key is None:
            return None

        normalized = _strip_accents(normalize_name(key))
        aliases = {
            "entradas": "entradas",
            "entrada": "entradas",
            "saidas": "saidas",
            "saida": "saidas",
            "bh": "bh",
            "balanco hidrico": "bh",
            "balanco": "bh",
            "diurese": "diurese",
        }
        return aliases.get(normalized, normalized.replace(" ", "_"))

    def _item_value_text(self, item: ClinicalItem) -> str:
        values = [value.value for value in item.values if value.value]
        values.extend(value for value in item.commented_values if value)
        for child in item.children:
            parts = []
            if child.key:
                parts.append(child.key)
            parts.extend(value.value for value in child.values if value.value)
            values.append(" ".join(parts))
        return _normalize_spaces(" ".join(values))

    def _missing_required_item(self, section: ClinicalSection, key: str) -> CompilerDiagnostic:
        return CompilerDiagnostic(
            severity="error",
            code="balanco_hidrico_missing_required_item",
            message=f"Item obrigatório ausente em {section.section_name}: {key}.",
            phase="semantic",
            line=section.start_line,
            section=section.section_name,
            raw_text=section.raw_text,
        )

    def _line_for_key(self, section: ClinicalSection, key: str) -> int | None:
        for item in section.items:
            if self._canonical_key(item.key) == key:
                return item.line
        return section.start_line

    def _value_to_dict(self, value: ParsedFluidValue | None) -> dict[str, Any] | None:
        return value.to_dict() if value is not None else None

    def _format_value(self, value: Any) -> str | None:
        if not isinstance(value, dict) or value.get("value") is None or value.get("unit") is None:
            return None

        number = value["value"]
        sign = value.get("sign") or ""
        if number < 0:
            number_text = f"{abs(number):g}".replace(".", ",")
            sign = "-"
        else:
            number_text = f"{number:g}".replace(".", ",")
        return f"{sign}{number_text} {value['unit']}"


_FLUID_VALUE_RE = re.compile(
    r"(?P<sign>[+-])?\s*(?P<number>\d[\d.]*,?\d*)\s*(?P<unit>ml\s*/\s*kg\s*/\s*h|ml)\b",
    flags=re.IGNORECASE,
)


def _normalize_spaces(text: str) -> str:
    return " ".join(text.strip().split())


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
