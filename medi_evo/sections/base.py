from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from medi_evo.models import ClinicalDocument, ClinicalItem, ClinicalSection, CompilerDiagnostic


def normalize_name(value: str) -> str:
    """Normalização mínima para matching de nomes.

    Não remove acentos de propósito: cada seção específica pode decidir seus aliases.
    """
    return " ".join(value.strip().lower().split())


@dataclass(frozen=True, slots=True)
class SectionParserConfig:
    """Regras da linha de seção."""

    canonical_name: str
    accepted_names: tuple[str, ...]
    required: bool = False
    required_section_value: bool = False


@dataclass(frozen=True, slots=True)
class SubsectionParserConfig:
    """Regras das subseções dentro da seção."""

    default_subsections: tuple[str, ...] = ()
    required_subsections: tuple[str, ...] = ()
    allow_new: bool = True
    inline_states: tuple[str, ...] = ()
    use_default_subsections_as_inline_states: bool = True

    def all_inline_states(self) -> set[str]:
        states = set(self.inline_states)
        if self.use_default_subsections_as_inline_states:
            states.update(self.default_subsections)
        return states


@dataclass(frozen=True, slots=True)
class ItemParserConfig:
    """Regras genéricas de item para uma seção específica.

    Regras clínicas complexas devem ser implementadas sobrescrevendo `parse_item` ou
    `validate_item` na seção específica.
    """

    allow_free_text: bool = True
    require_key: bool = False
    allow_children: bool = True
    accepted_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizationConfig:
    """Configuração para renderização/normalização futura."""

    normalized_section_name: str | None = None
    normalized_subsection_names: dict[str, str] = field(default_factory=dict)
    normalized_item_keys: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssociatedErrorsConfig:
    """Códigos de diagnostics gerados pela seção específica."""

    missing_required_section: str = "required_section_missing"
    missing_section_value: str = "required_section_value_missing"
    missing_required_subsection: str = "required_subsection_missing"
    unknown_subsection: str = "unknown_subsection"
    free_text_not_allowed: str = "free_text_not_allowed"
    item_key_required: str = "item_key_required"
    unknown_item_key: str = "unknown_item_key"


@dataclass(slots=True)
class SectionProcessingResult:
    canonical_name: str
    raw_section_name: str | None = None
    data: Any | None = None
    normalized: Any | None = None
    diagnostics: list[CompilerDiagnostic] = field(default_factory=list)


class SpecificSectionParser(Protocol):
    """Contrato para seções específicas plugáveis.

    A linguagem mínima não deve ser modificada para criar novas seções. Uma seção
    nova deve implementar este contrato, ser registrada no `SectionRegistry` e cuidar
    de validação, parsing clínico, normalização e diagnostics próprios.
    """

    section_parser: SectionParserConfig
    subsection_parser: SubsectionParserConfig
    item_parser: ItemParserConfig
    normalization: NormalizationConfig
    associated_errors: AssociatedErrorsConfig

    @property
    def inline_states(self) -> set[str]: ...

    def matches(self, section_name: str) -> bool: ...

    def process(self, section: ClinicalSection, document: ClinicalDocument) -> SectionProcessingResult: ...


class BaseSpecificSectionParser:
    """Base segura para implementar seções específicas incrementalmente."""

    section_parser: SectionParserConfig
    subsection_parser: SubsectionParserConfig = SubsectionParserConfig()
    item_parser: ItemParserConfig = ItemParserConfig()
    normalization: NormalizationConfig = NormalizationConfig()
    associated_errors: AssociatedErrorsConfig = AssociatedErrorsConfig()

    @property
    def inline_states(self) -> set[str]:
        return self.subsection_parser.all_inline_states()

    @property
    def canonical_name(self) -> str:
        return self.section_parser.canonical_name

    @property
    def accepted_names(self) -> set[str]:
        names = set(self.section_parser.accepted_names)
        names.add(self.section_parser.canonical_name)
        return {normalize_name(name) for name in names}

    def matches(self, section_name: str) -> bool:
        return normalize_name(section_name) in self.accepted_names

    def process(self, section: ClinicalSection, document: ClinicalDocument) -> SectionProcessingResult:
        diagnostics: list[CompilerDiagnostic] = []
        diagnostics.extend(self.validate_section(section, document))
        data = self.parse_section(section, document, diagnostics)
        normalized = self.normalize_section(section, data)
        return SectionProcessingResult(
            canonical_name=self.canonical_name,
            raw_section_name=section.section_name,
            data=data,
            normalized=normalized,
            diagnostics=diagnostics,
        )

    def validate_missing_required_section(self, document: ClinicalDocument) -> list[CompilerDiagnostic]:
        if not self.section_parser.required:
            return []
        if any(self.matches(section.section_name) for section in document.sections):
            return []
        return [
            CompilerDiagnostic(
                severity="error",
                code=self.associated_errors.missing_required_section,
                message=f"Seção obrigatória ausente: {self.canonical_name}.",
                phase="semantic",
                section=self.canonical_name,
            )
        ]

    def validate_section(self, section: ClinicalSection, document: ClinicalDocument) -> list[CompilerDiagnostic]:
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
            diagnostics.extend(self.validate_item(item, section))
        return diagnostics

    def validate_subsections(self, section: ClinicalSection) -> list[CompilerDiagnostic]:
        diagnostics: list[CompilerDiagnostic] = []
        present = {normalize_name(sub.subsec_name) for sub in section.states}
        required = {normalize_name(name) for name in self.subsection_parser.required_subsections}
        for required_name in sorted(required - present):
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code=self.associated_errors.missing_required_subsection,
                    message=f"Subseção obrigatória ausente em {section.section_name}: {required_name}.",
                    phase="semantic",
                    line=section.start_line,
                    section=section.section_name,
                    raw_text=section.raw_text,
                )
            )
        if not self.subsection_parser.allow_new:
            allowed = {normalize_name(name) for name in self.subsection_parser.default_subsections}
            allowed.update(required)
            for sub in section.states:
                if normalize_name(sub.subsec_name) not in allowed:
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

    def validate_item(self, item: ClinicalItem, section: ClinicalSection) -> list[CompilerDiagnostic]:
        diagnostics: list[CompilerDiagnostic] = []
        if self.item_parser.require_key and not item.key:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code=self.associated_errors.item_key_required,
                    message=f"Item da seção {section.section_name} exige key explícita antes de `:`.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )
        if item.key is None and not self.item_parser.allow_free_text:
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code=self.associated_errors.free_text_not_allowed,
                    message=f"Texto livre não é permitido na seção {section.section_name}.",
                    phase="semantic",
                    line=item.line,
                    section=section.section_name,
                    raw_text=item.raw_text,
                )
            )
        if item.key and self.item_parser.accepted_keys:
            accepted = {normalize_name(key) for key in self.item_parser.accepted_keys}
            if normalize_name(item.key) not in accepted:
                diagnostics.append(
                    CompilerDiagnostic(
                        severity="warning",
                        code=self.associated_errors.unknown_item_key,
                        message=f"Key não prevista em {section.section_name}: {item.key}.",
                        phase="semantic",
                        line=item.line,
                        section=section.section_name,
                        raw_text=item.raw_text,
                    )
                )
        for child in item.children:
            diagnostics.extend(self.validate_item(child, section))
        return diagnostics

    def parse_section(
        self,
        section: ClinicalSection,
        document: ClinicalDocument,
        diagnostics: list[CompilerDiagnostic],
    ) -> Any:
        """Transforma a AST genérica em dados específicos.

        A implementação default retorna um dicionário simples. Seções clínicas reais
        devem sobrescrever este método.
        """
        return {
            "section_name": section.section_name,
            "section_value": section.section_value,
            "items": [self.parse_item(item, section, diagnostics) for item in section.items],
        }

    def parse_item(
        self,
        item: ClinicalItem,
        section: ClinicalSection,
        diagnostics: list[CompilerDiagnostic],
    ) -> Any:
        return item

    def normalize_section(self, section: ClinicalSection, data: Any) -> Any:
        """Retorna forma normalizada futura.

        Por enquanto, a base não renderiza texto normalizado; só reserva o ponto de
        extensão para cada seção específica.
        """
        return data
