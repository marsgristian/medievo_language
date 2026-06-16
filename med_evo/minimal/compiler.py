from __future__ import annotations

from datetime import datetime

from med_evo.models import (
    ClinicalDate,
    ClinicalDatePeriod,
    ClinicalDocument,
    ClinicalItem,
    ClinicalSection,
    ClinicalValue,
    CompilerDiagnostic,
    SourceLine,
    Subsection,
)
from med_evo.parser.lark_parser import parse_lines
from med_evo.sections.registry import SectionRegistry

from .dates import DateMatch, extract_reference_datetime, find_first_date, find_first_period, remove_date_span
from .text import (
    extract_parenthesized_values,
    find_structural_colon,
    normalize_spaces,
    remove_ignored_comments,
    split_top_level,
)


class MinimalmedievoCompiler:
    """Compilador medievo mínimo.

    Pipeline:
    texto -> Lark estrutural -> AST clínica genérica -> JSON/python object.
    """

    def __init__(self, section_registry: SectionRegistry | None = None) -> None:
        self.section_registry = section_registry

    def compile(self, text: str, *, reference_datetime: datetime | None = None) -> ClinicalDocument:
        diagnostics = _prevalidate_raw_syntax(text)
        if diagnostics:
            return ClinicalDocument(raw_text=text, diagnostics=diagnostics, reference_datetime=reference_datetime)

        lex_result = parse_lines(text)
        diagnostics.extend(lex_result.diagnostics)
        if diagnostics:
            return ClinicalDocument(raw_text=text, diagnostics=diagnostics, reference_datetime=reference_datetime)

        if reference_datetime is None:
            reference_datetime = _extract_reference_datetime_from_header(lex_result.lines)

        document = ClinicalDocument(raw_text=text, diagnostics=diagnostics, reference_datetime=reference_datetime)
        self._build_sections(lex_result.lines, document)
        _validate_item_syntax(document)
        if self.section_registry is not None:
            self.section_registry.process_document(document)
        return document

    def _build_sections(self, lines: list[SourceLine], document: ClinicalDocument) -> None:
        current_section: ClinicalSection | None = None
        current_state: str | None = None
        current_raw_lines: list[str] = []

        def close_section(end_line: int | None = None) -> None:
            nonlocal current_section, current_raw_lines
            if current_section is None:
                return
            current_section.raw_text = "\n".join(current_raw_lines).strip()
            current_section.end_line = end_line
            document.sections.append(current_section)
            current_section = None
            current_raw_lines = []

        for line in lines:
            if line.kind == "blank":
                if current_section is not None:
                    current_raw_lines.append(line.raw)
                continue

            if line.kind == "section":
                close_section(line.line_number - 1)
                current_section = _parse_section_line(line)
                current_state = None
                current_raw_lines = [line.raw]
                continue

            if current_section is None:
                # Texto antes da primeira seção é considerado cabeçalho livre.
                continue

            current_raw_lines.append(line.raw)

            if line.kind == "subsection":
                subsection, inline_items = _parse_subsection_line(line)
                if not subsection.subsec_name:
                    document.diagnostics.append(
                        CompilerDiagnostic(
                            severity="error",
                            code="empty_subsection_name",
                            message="Subseção com nome vazio.",
                            phase="syntactic",
                            line=line.line_number,
                            raw_text=line.raw,
                        )
                    )
                    continue
                current_section.states.append(subsection)
                current_state = subsection.subsec_name
                if inline_items:
                    _append_items_from_text(
                        inline_items,
                        line=line,
                        section=current_section,
                        state=current_state,
                        reference_datetime=document.reference_datetime,
                        diagnostics=document.diagnostics,
                        inline_states=self._inline_states_for(current_section.section_name),
                    )
                continue

            _append_items_from_text(
                line.text,
                line=line,
                section=current_section,
                state=current_state,
                reference_datetime=document.reference_datetime,
                diagnostics=document.diagnostics,
                inline_states=self._inline_states_for(current_section.section_name),
            )

        close_section(lines[-1].line_number if lines else None)

    def _inline_states_for(self, section_name: str) -> set[str]:
        if self.section_registry is None:
            return set()
        return self.section_registry.inline_states_for(section_name)


def compile_minimal_medievo(
    text: str,
    *,
    reference_datetime: datetime | None = None,
    section_registry: SectionRegistry | None = None,
) -> ClinicalDocument:
    return MinimalmedievoCompiler(section_registry=section_registry).compile(text, reference_datetime=reference_datetime)


def compile_medievo(
    text: str,
    *,
    reference_datetime: datetime | None = None,
    section_registry: SectionRegistry | None = None,
) -> ClinicalDocument:
    """Alias principal da linguagem mínima."""
    return compile_minimal_medievo(text, reference_datetime=reference_datetime, section_registry=section_registry)


def _extract_reference_datetime_from_header(lines: list[SourceLine]) -> datetime | None:
    header_lines: list[str] = []
    for line in lines:
        if line.kind == "section":
            break
        if line.kind != "blank":
            header_lines.append(line.raw)
    return extract_reference_datetime("\n".join(header_lines))


def _parse_section_line(line: SourceLine) -> ClinicalSection:
    content = line.raw.lstrip("#").strip()
    removed = remove_ignored_comments(content)
    content = removed.text
    colon = find_structural_colon(content)
    if colon is None:
        name_part = content
        value_part = ""
    else:
        name_part = content[:colon]
        value_part = content[colon + 1 :]

    section_name, name_comments = extract_parenthesized_values(name_part)
    section_value, value_comments = extract_parenthesized_values(value_part)
    return ClinicalSection(
        section_name=normalize_spaces(section_name),
        section_value=normalize_spaces(section_value) if section_value.strip() else None,
        commented_values=name_comments + value_comments,
        ignored_comments=removed.removed,
        start_line=line.line_number,
    )


def _parse_subsection_line(line: SourceLine) -> tuple[Subsection, str]:
    content = line.raw.lstrip(">").strip()
    removed = remove_ignored_comments(content)
    content = removed.text
    colon = find_structural_colon(content)
    if colon is None:
        name_part = content
        inline_items = ""
    else:
        name_part = content[:colon]
        inline_items = content[colon + 1 :].strip()
    subsec_name, comments = extract_parenthesized_values(name_part)
    return (
        Subsection(
            subsec_name=normalize_spaces(subsec_name),
            commented_values=comments,
            raw_text=line.raw,
            line=line.line_number,
        ),
        inline_items,
    )


def _append_items_from_text(
    text: str,
    *,
    line: SourceLine,
    section: ClinicalSection,
    state: str | None,
    reference_datetime: datetime | None,
    diagnostics: list[CompilerDiagnostic],
    inline_states: set[str],
) -> None:
    removed = remove_ignored_comments(text)
    if removed.removed:
        section.ignored_comments.extend(removed.removed)
    if not removed.text.strip():
        return

    raw_items = split_top_level(removed.text, "|")
    for raw_item in raw_items:
        if not raw_item.strip():
            diagnostics.append(
                CompilerDiagnostic(
                    severity="error",
                    code="empty_item",
                    message="Item vazio entre separadores universais.",
                    phase="syntactic",
                    line=line.line_number,
                    section=section.section_name,
                    raw_text=line.raw,
                )
            )
            continue
        item = _parse_item(
            raw_item,
            state=state,
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
            section=section.section_name,
            line=line.line_number,
            inline_states=inline_states,
        )
        section.items.append(item)


def _parse_item(
    raw_item: str,
    *,
    state: str | None,
    reference_datetime: datetime | None,
    diagnostics: list[CompilerDiagnostic],
    section: str | None,
    line: int | None,
    inline_states: set[str],
) -> ClinicalItem:
    original = normalize_spaces(raw_item)
    working = original

    date_match = find_first_period(
        working,
        reference_datetime=reference_datetime,
        diagnostics=diagnostics,
        line=line,
        section=section,
    )
    if date_match is None:
        date_match = find_first_date(
            working,
            reference_datetime=reference_datetime,
            diagnostics=diagnostics,
            line=line,
            section=section,
        )
    date_value: ClinicalDate | ClinicalDatePeriod | None = date_match.value if date_match else None

    working_for_key_value = working
    if date_match is not None and not _date_is_the_key(working, date_match):
        working_for_key_value = remove_date_span(working, date_match.start, date_match.end)

    colon = find_structural_colon(working_for_key_value)
    key: str | None = None
    value_text = working_for_key_value
    if colon is not None:
        key = normalize_spaces(working_for_key_value[:colon]) or None
        value_text = working_for_key_value[colon + 1 :].strip()

    if inline_states:
        detected_state, stripped = _extract_inline_state(value_text, inline_states)
        if detected_state is not None:
            state = detected_state
            value_text = stripped

    item = ClinicalItem(
        raw_text=original,
        date=date_value,
        state=state,
        key=key,
        line=line,
    )

    if key is None:
        value_text, item_comments = extract_parenthesized_values(value_text)
        item.commented_values.extend(item_comments)
        if value_text.strip():
            item.values.append(ClinicalValue(raw_text=normalize_spaces(value_text), value=normalize_spaces(value_text)))
        return item

    value_parts = split_top_level(value_text, ";") if value_text.strip() else []
    for index, part in enumerate(value_parts):
        part = part.strip()
        if not part:
            continue
        child_colon = find_structural_colon(part)
        if index > 0 and child_colon is not None:
            child = _parse_item(
                part,
                state=state,
                reference_datetime=reference_datetime,
                diagnostics=diagnostics,
                section=section,
                line=line,
                inline_states=inline_states,
            )
            if child.date is None:
                child.date = date_value
            item.children.append(child)
        else:
            item.values.append(_parse_value(part))

    return item


def _date_is_the_key(text: str, date_match: DateMatch) -> bool:
    """True para formas como `10/06: value`, onde key e date são a mesma coisa."""
    colon = find_structural_colon(text)
    if colon is None:
        return False
    between = text[date_match.end : colon]
    before = text[: date_match.start]
    return not before.strip() and not between.strip()


def _parse_value(raw_text: str) -> ClinicalValue:
    cleaned, comments = extract_parenthesized_values(raw_text)
    return ClinicalValue(raw_text=normalize_spaces(raw_text), value=normalize_spaces(cleaned), commented_values=comments)


def _extract_inline_state(text: str, states: set[str]) -> tuple[str | None, str]:
    normalized_states = {state.lower(): state for state in states}
    stripped = text.strip()
    lower = stripped.lower()
    for normalized, original in sorted(normalized_states.items(), key=lambda item: len(item[0]), reverse=True):
        if lower == normalized:
            return original, ""
        if lower.startswith(normalized + " "):
            return original, stripped[len(normalized) :].strip()
        if lower.endswith(" " + normalized):
            return original, stripped[: -len(normalized)].strip()
    return None, text


def _prevalidate_raw_syntax(text: str) -> list[CompilerDiagnostic]:
    diagnostics: list[CompilerDiagnostic] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            content = stripped.lstrip("#").strip()
            if not content or content.startswith(":"):
                diagnostics.append(_syntax("empty_section_name", "Seção com nome vazio.", line_number, raw_line))
            elif ">" in content:
                diagnostics.append(
                    _syntax(
                        "section_contains_subsection_marker",
                        "Linha de seção não pode conter marcador de subseção `>`; coloque a subseção em outra linha.",
                        line_number,
                        raw_line,
                    )
                )
            elif "|" in content:
                diagnostics.append(
                    _syntax(
                        "section_contains_item_separator",
                        "Linha de seção não pode conter itens separados por `|`; coloque os itens nas linhas seguintes.",
                        line_number,
                        raw_line,
                    )
                )
            continue
        if stripped.startswith(">"):
            content = stripped[1:].strip()
            if not content or content.startswith(":"):
                diagnostics.append(_syntax("empty_subsection_name", "Subseção com nome vazio.", line_number, raw_line))
            elif ":" not in content:
                diagnostics.append(_syntax("subsection_missing_colon", "Subseção deve terminar o nome com `:`.", line_number, raw_line))
            continue
        if stripped.startswith(":"):
            diagnostics.append(_syntax("empty_item_key", "Item com key explicitamente vazia antes de `:`.", line_number, raw_line))
    return diagnostics


def _validate_item_syntax(document: ClinicalDocument) -> None:
    for section in document.sections:
        for item in section.items:
            _validate_single_item_syntax(item, document.diagnostics, section.section_name)


def _validate_single_item_syntax(item: ClinicalItem, diagnostics: list[CompilerDiagnostic], section: str) -> None:
    colon = find_structural_colon(item.raw_text)
    if colon is not None:
        key_text = item.raw_text[:colon].strip()
        value_text = item.raw_text[colon + 1 :].strip()
        if not key_text:
            diagnostics.append(_syntax("empty_item_key", "Item com key explicitamente vazia antes de `:`.", item.line, item.raw_text, section))
        if not value_text or value_text in {"|", ";"}:
            diagnostics.append(_syntax("empty_item_value", "Item com key explícita precisa ter value após `:`.", item.line, item.raw_text, section))
    for child in item.children:
        _validate_single_item_syntax(child, diagnostics, section)


def _syntax(
    code: str,
    message: str,
    line: int | None,
    raw_text: str,
    section: str | None = None,
) -> CompilerDiagnostic:
    return CompilerDiagnostic(
        severity="error",
        code=code,
        message=message,
        phase="syntactic",
        line=line,
        section=section,
        raw_text=raw_text,
    )
