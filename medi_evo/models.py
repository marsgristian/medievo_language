from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

Severity = Literal["info", "warning", "error"]
DiagnosticPhase = Literal["syntactic", "semantic"]
DatePrecision = Literal["day", "minute"]


@dataclass(slots=True)
class CompilerDiagnostic:
    severity: Severity
    code: str
    message: str
    phase: DiagnosticPhase = "semantic"
    line: int | None = None
    column: int | None = None
    section: str | None = None
    raw_text: str | None = None


@dataclass(slots=True)
class SourceLine:
    line_number: int
    kind: Literal["section", "subsection", "text", "blank"]
    text: str
    raw: str


@dataclass(slots=True)
class ClinicalDate:
    raw_text: str
    value: datetime
    precision: DatePrecision
    explicit_year: bool
    inferred_year: int | None = None


@dataclass(slots=True)
class ClinicalDatePeriod:
    raw_text: str
    start: ClinicalDate
    end: ClinicalDate
    delta_time: timedelta


@dataclass(slots=True)
class ClinicalValue:
    raw_text: str
    value: str
    commented_values: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClinicalItem:
    raw_text: str
    date: ClinicalDate | ClinicalDatePeriod | None = None
    state: str | None = None
    key: str | None = None
    values: list[ClinicalValue] = field(default_factory=list)
    commented_values: list[str] = field(default_factory=list)
    children: list["ClinicalItem"] = field(default_factory=list)
    line: int | None = None


@dataclass(slots=True)
class Subsection:
    subsec_name: str
    commented_values: list[str] = field(default_factory=list)
    raw_text: str = ""
    line: int | None = None


@dataclass(slots=True)
class ClinicalSection:
    section_name: str
    section_value: str | None = None
    commented_values: list[str] = field(default_factory=list)
    states: list[Subsection] = field(default_factory=list)
    items: list[ClinicalItem] = field(default_factory=list)
    ignored_comments: list[str] = field(default_factory=list)
    raw_text: str = ""
    start_line: int | None = None
    end_line: int | None = None


@dataclass(slots=True)
class ClinicalDocument:
    language: str = "medi_evo"
    version: str = "1.0.1"
    reference_datetime: datetime | None = None
    sections: list[ClinicalSection] = field(default_factory=list)
    diagnostics: list[CompilerDiagnostic] = field(default_factory=list)
    processed_sections: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _to_plain_dict(self)

    def to_json(self, *, indent: int = 2, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)

    def errors(self) -> list[CompilerDiagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    def warnings(self) -> list[CompilerDiagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]


def _to_plain_dict(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, timedelta):
        return {
            "seconds": value.total_seconds(),
            "human": str(value),
        }
    if is_dataclass(value):
        return {k: _to_plain_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _to_plain_dict(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain_dict(v) for v in value]
    return value
