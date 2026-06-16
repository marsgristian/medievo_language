from __future__ import annotations

from dataclasses import dataclass, field

from med_evo.models import ClinicalDocument
from med_evo.sections.base import BaseSpecificSectionParser, SectionProcessingResult


@dataclass(slots=True)
class SectionRegistry:
    """Registro de seções específicas.

    O compilador mínimo pode ser usado sem registry. Quando um registry é fornecido,
    ele aplica parsers específicos após a AST genérica estar pronta, sem alterar a
    gramática nem o parser mínimo.
    """

    parsers: list[BaseSpecificSectionParser] = field(default_factory=list)

    def register(self, parser: BaseSpecificSectionParser) -> None:
        self.parsers.append(parser)

    def parser_for(self, section_name: str) -> BaseSpecificSectionParser | None:
        for parser in self.parsers:
            if parser.matches(section_name):
                return parser
        return None

    def inline_states_for(self, section_name: str) -> set[str]:
        parser = self.parser_for(section_name)
        return parser.inline_states if parser is not None else set()

    def process_document(self, document: ClinicalDocument) -> None:
        for parser in self.parsers:
            document.diagnostics.extend(parser.validate_missing_required_section(document))

        for section in document.sections:
            parser = self.parser_for(section.section_name)
            if parser is None:
                continue
            result = parser.process(section, document)
            document.diagnostics.extend(result.diagnostics)
            document.processed_sections[result.canonical_name] = result
