from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lark import Lark, Token, Tree
from lark.exceptions import LarkError, UnexpectedInput

from .grammar import medi_evo_GRAMMAR
from ..models import CompilerDiagnostic, SourceLine

_LINE_PARSER = Lark(medi_evo_GRAMMAR, parser="lalr", propagate_positions=True, maybe_placeholders=False)


@dataclass(slots=True)
class LexResult:
    lines: list[SourceLine]
    diagnostics: list[CompilerDiagnostic]


def parse_lines(text: str) -> LexResult:
    diagnostics: list[CompilerDiagnostic] = []
    try:
        tree = _LINE_PARSER.parse(text)
    except LarkError as exc:
        line = exc.line if isinstance(exc, UnexpectedInput) else None
        column = exc.column if isinstance(exc, UnexpectedInput) else None
        raw_text = None
        if line is not None:
            source_lines = text.splitlines()
            if 1 <= line <= len(source_lines):
                raw_text = source_lines[line - 1]
        diagnostics.append(
            CompilerDiagnostic(
                severity="error",
                code="syntax_error",
                message=f"Erro sintatico Medi Evo language: {exc}",
                phase="syntactic",
                line=line,
                column=column,
                raw_text=raw_text,
            )
        )
        return LexResult(lines=[], diagnostics=diagnostics)

    lines = _tree_to_lines(tree)
    return LexResult(lines=lines, diagnostics=diagnostics)


def _tree_to_lines(tree: Tree) -> list[SourceLine]:
    result: list[SourceLine] = []
    for child in tree.children:
        if not isinstance(child, Tree):
            continue
        line_kind = _line_kind(child.data)
        token = _first_token(child)
        if line_kind == "blank":
            line_number = token.line if token is not None else (result[-1].line_number + 1 if result else 1)
            raw = ""
            text = ""
        elif token is not None:
            line_number = token.line
            raw = str(token)
            text = str(token)
        else:
            line_number = result[-1].line_number + 1 if result else 1
            raw = ""
            text = ""
        result.append(SourceLine(line_number=line_number, kind=line_kind, text=text, raw=raw))
    return result


def _line_kind(rule_name: str) -> Literal["section", "subsection", "text", "blank"]:
    if rule_name == "section_line":
        return "section"
    if rule_name == "subsection_line":
        return "subsection"
    if rule_name == "text_line":
        return "text"
    return "blank"


def _first_token(tree: Tree) -> Token | None:
    for item in tree.scan_values(lambda value: isinstance(value, Token)):
        return item
    return None
