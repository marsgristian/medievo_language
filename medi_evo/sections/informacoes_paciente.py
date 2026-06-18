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
class ParsedField:
    raw_text: str
    value: Any
    date: Any | None = None
    state: str | None = None
    commented_values: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "value": self.value,
            "date": self.date,
            "state": self.state,
            "commented_values": self.commented_values or [],
        }


@dataclass(frozen=True, slots=True)
class ParsedAge:
    anos: int = 0
    meses: int = 0
    dias: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "anos": self.anos,
            "meses": self.meses,
            "dias": self.dias,
        }


class InformacoesPacienteSection(BaseSpecificSectionParser):
    """Parser específico da seção INFORMAÇÕES DO PACIENTE.

    Regras:
    - seção obrigatória;
    - section_value não é obrigatório;
    - subseções são permitidas, mas não obrigatórias;
    - todos os itens precisam ser key/value;
    - itens obrigatórios: nome, idade, data da internação, sexo e peso;
    - idade é transformada em dicionário estruturado nos dados processados;
    - peso é convertido para float a partir de número em formato pt-BR.
    """

    REQUIRED_KEYS = (
        "nome",
        "idade",
        "data da internação",
        "sexo",
        "peso",
    )

    ACCEPTED_KEYS = (
        "nome",
        "idade",
        "data da internação",
        "data da internacao",
        "data internacao",
        "internacao",
        "sexo",
        "gênero",
        "genero",
        "peso",
    )

    section_parser = SectionParserConfig(
        canonical_name="INFORMAÇÕES DO PACIENTE",
        accepted_names=(
            "INFORMAÇÕES DO PACIENTE",
            "INFORMACOES DO PACIENTE",
            "INFO PACIENTE",
            "DADOS DO PACIENTE",
            "IDENTIFICAÇÃO",
            "IDENTIFICACAO",
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
        normalized_section_name="INFORMAÇÕES DO PACIENTE",
        normalized_item_keys={
            "nome": "nome",
            "idade": "idade",
            "data da internação": "data_da_internacao",
            "sexo": "sexo",
            "peso": "peso",
        },
    )

    associated_errors = AssociatedErrorsConfig(
        missing_required_section="informacoes_paciente_missing_section",
        free_text_not_allowed="informacoes_paciente_free_text_not_allowed",
        item_key_required="informacoes_paciente_item_key_required",
        unknown_item_key="informacoes_paciente_unknown_item_key",
    )

    def validate_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
    ) -> list[CompilerDiagnostic]:
        diagnostics = super().validate_section(section, document)

        items_by_key = self._items_by_canonical_key(section)

        for required_key in self.REQUIRED_KEYS:
            if required_key not in items_by_key:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="error",
                        code="informacoes_paciente_missing_required_item",
                        message=f"Item obrigatório ausente em {section.section_name}: {required_key}.",
                        phase="semantic",
                        line=section.start_line,
                        section=section.section_name,
                        raw_text=section.raw_text,
                    )
                )

        for item in section.items:
            canonical_key = self._canonical_key(item.key)

            if canonical_key is None:
                continue

            if canonical_key == "idade":
                if self._parse_age_text(self._item_value_text(item)) is None:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code="informacoes_paciente_invalid_age",
                            message="Idade deve usar unidades reconhecidas: ano(s), mês/mes(es), dia(s).",
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )

            elif canonical_key == "data da internação":
                if item.date is None:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code="informacoes_paciente_invalid_internacao_date",
                            message="Data da internação deve conter uma DATA parseável.",
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )

            elif canonical_key == "peso":
                if self._parse_weight(self._item_value_text(item)) is None:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code="informacoes_paciente_invalid_weight",
                            message="Peso deve conter número parseável em formato pt-BR, exemplo: 56,987 kg.",
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )
                if item.date is None:
                    diagnostics.append(
                        CompilerDiagnostic(
                            severity="warning",
                            code="informacoes_paciente_weight_without_date",
                            message=(
                                "Peso sem data associada; assume-se que foi medido na data desta evolucao."
                            ),
                            phase="semantic",
                            line=item.line,
                            section=section.section_name,
                            raw_text=item.raw_text,
                        )
                    )
                else:
                    measurement_datetime = self._weight_measurement_datetime(item.date)
                    if (
                        document.reference_datetime is not None
                        and measurement_datetime is not None
                        and (document.reference_datetime.date() - measurement_datetime.date()).days >= 7
                    ):
                        diagnostics.append(
                            CompilerDiagnostic(
                                severity="error",
                                code="informacoes_paciente_weight_measurement_too_old",
                                message="Peso deve ter sido medido ha menos de 7 dias.",
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
        data: dict[str, Any] = {}

        for item in section.items:
            canonical_key = self._canonical_key(item.key)

            if canonical_key is None:
                continue

            if canonical_key == "nome":
                value = self._item_value_text(item)
                data["nome"] = self._field_from_item(item, value)

            elif canonical_key == "sexo":
                value = self._item_value_text(item)
                data["sexo"] = self._field_from_item(item, value)

            elif canonical_key == "data da internação":
                if item.date is not None and hasattr(item.date, "value"):
                    value = item.date.value
                else:
                    value = None

                data["data_da_internacao"] = self._field_from_item(item, value)

            elif canonical_key == "peso":
                value = self._parse_weight(self._item_value_text(item))
                data["peso"] = self._field_from_item(item, value)

            elif canonical_key == "idade":
                parsed_age = self._parse_age_text(self._item_value_text(item))
                if parsed_age is not None:
                    data["idade"] = self._field_from_item(item, parsed_age.to_dict())

        return data

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        idade = self._field_value(data.get("idade")) or {}
        idade_text = self._format_age(idade) if isinstance(idade, dict) else None

        peso = self._field_value(data.get("peso"))

        return {
            "section_name": self.normalization.normalized_section_name,
            "nome": self._field_value(data.get("nome")),
            "idade": idade_text,
            "data_da_internacao": self._format_datetime(self._field_value(data.get("data_da_internacao"))),
            "sexo": self._field_value(data.get("sexo")),
            "peso": f"{peso:g} kg" if isinstance(peso, float) else None,
        }
        
    def _field_from_item(self, item: ClinicalItem, value: Any) -> ParsedField:
        return ParsedField(
            raw_text=item.raw_text,
            value=value,
            date=item.date,
            state=item.state,
            commented_values=item.commented_values,
        )

    def _field_value(self, field: Any) -> Any:
        if isinstance(field, ParsedField):
            return field.value
        return field

    def _items_by_canonical_key(self, section: ClinicalSection) -> dict[str, list[ClinicalItem]]:
        result: dict[str, list[ClinicalItem]] = {}

        for item in section.items:
            canonical = self._canonical_key(item.key)

            if canonical is None:
                continue

            result.setdefault(canonical, []).append(item)

        return result

    def _canonical_key(self, key: str | None) -> str | None:
        if key is None:
            return None

        normalized = _strip_accents(normalize_name(key))

        aliases = {
            "nome": "nome",
            "idade": "idade",
            "data da internacao": "data da internação",
            "data internacao": "data da internação",
            "internacao": "data da internação",
            "sexo": "sexo",
            "genero": "sexo",
            "peso": "peso",
        }

        return aliases.get(normalized)

    def _item_value_text(self, item: ClinicalItem) -> str:
        if item.values:
            return " ".join(value.value for value in item.values if value.value).strip()

        return ""

    def _parse_age_text(self, text: str) -> ParsedAge | None:
        matches = list(_AGE_PART_RE.finditer(text))

        if not matches:
            return None

        values = {
            "ano": 0,
            "mes": 0,
            "dia": 0,
        }

        for match in matches:
            number = int(match.group("number"))
            unit = _canonical_age_unit(match.group("unit"))
            values[unit] = number

        return ParsedAge(
            anos=values["ano"],
            meses=values["mes"],
            dias=values["dia"],
        )

    def _parse_weight(self, text: str) -> float | None:
        match = _WEIGHT_NUMBER_RE.search(text)

        if not match:
            return None

        number_text = match.group(0)

        if "," in number_text:
            # Formato pt-BR:
            # 56,987       -> 56.987
            # 1.600,1234   -> 1600.1234
            normalized = number_text.replace(".", "").replace(",", ".")
        else:
            # Aceita fallback simples:
            # 56.9 -> 56.9
            normalized = number_text

        try:
            return float(normalized)
        except ValueError:
            return None

    def _weight_measurement_datetime(self, date_value: Any) -> datetime | None:
        if isinstance(date_value, ClinicalDate):
            return date_value.value

        if isinstance(date_value, ClinicalDatePeriod):
            return date_value.end.value

        return None

    def _format_age(self, idade: dict[str, int]) -> str:
        parts: list[str] = []

        anos = int(idade.get("anos") or 0)
        meses = int(idade.get("meses") or 0)
        dias = int(idade.get("dias") or 0)

        if anos:
            parts.append(f"{anos} {'ano' if anos == 1 else 'anos'}")

        if meses:
            parts.append(f"{meses} {'mês' if meses == 1 else 'meses'}")

        if dias:
            parts.append(f"{dias} {'dia' if dias == 1 else 'dias'}")

        return " ".join(parts) if parts else "0 dias"

    def _format_datetime(self, value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat(timespec="minutes")

        return None


_AGE_PART_RE = re.compile(
    r"(?P<number>\d+)\s*(?P<unit>anos?|meses|m[eê]s|m[eê]ses|dias?)\b",
    flags=re.IGNORECASE,
)

_WEIGHT_NUMBER_RE = re.compile(r"[-+]?\d[\d.]*,?\d*")


def _canonical_age_unit(unit: str) -> str:
    normalized = _strip_accents(unit.strip().lower())

    if normalized.startswith("ano"):
        return "ano"

    if normalized.startswith("mes"):
        return "mes"

    return "dia"


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
