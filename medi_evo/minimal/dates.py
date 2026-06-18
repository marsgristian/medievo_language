from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from medi_evo.models import ClinicalDate, ClinicalDatePeriod, CompilerDiagnostic

_DATE_WITH_OPTIONAL_YEAR = r"\d{1,2}/\d{1,2}(?:/\d{2,4})?(?:\s+\d{1,2}:\d{2})?"
_DAY_TO_DATE_PERIOD_RE = re.compile(
    rf"(?<!\d)(?P<start_day>\d{{1,2}})\s*-\s*(?P<end>{_DATE_WITH_OPTIONAL_YEAR})(?!\d)"
)
_DATE_TO_DATE_PERIOD_RE = re.compile(
    rf"(?<!\d)(?P<start>{_DATE_WITH_OPTIONAL_YEAR})\s*-\s*(?P<end>{_DATE_WITH_OPTIONAL_YEAR})(?!\d)"
)
_DATE_RE = re.compile(r"(?<!\d)(?P<date>\d{1,2}/\d{1,2}(?:/\d{2,4})?(?:\s+\d{1,2}:\d{2})?)(?!\d)")


@dataclass(slots=True)
class DateMatch:
    value: ClinicalDate | ClinicalDatePeriod
    start: int
    end: int


def find_first_period(
    text: str,
    *,
    reference_datetime: datetime | None,
    diagnostics: list[CompilerDiagnostic],
    line: int | None = None,
    section: str | None = None,
) -> DateMatch | None:
    candidates: list[tuple[int, re.Match[str], str]] = []
    for kind, pattern in (("date_date", _DATE_TO_DATE_PERIOD_RE), ("day_date", _DAY_TO_DATE_PERIOD_RE)):
        match = pattern.search(text)
        if match:
            candidates.append((match.start(), match, kind))
    if not candidates:
        return None
    _, match, kind = min(candidates, key=lambda item: item[0])
    if kind == "day_date":
        end_text = match.group("end")
        end_parts = _parse_date_parts(end_text)
        if end_parts is None:
            return None
        start_text = f"{match.group('start_day')}/{end_parts.month}"
        if end_parts.year_text:
            start_text = f"{start_text}/{end_parts.year_text}"
        if end_parts.time_text:
            start_text = f"{start_text} {end_parts.time_text}"
    else:
        start_text = match.group("start")
        end_text = match.group("end")

    start_date = parse_clinical_date(
        start_text,
        reference_datetime=reference_datetime,
        diagnostics=diagnostics,
        line=line,
        section=section,
    )
    end_date = parse_clinical_date(
        end_text,
        reference_datetime=reference_datetime,
        diagnostics=diagnostics,
        line=line,
        section=section,
    )
    if start_date is None or end_date is None:
        return None

    if end_date.value < start_date.value:
        diagnostics.append(
            CompilerDiagnostic(
                severity="error",
                code="invalid_date_period",
                message=f"Período com data final anterior à inicial: {match.group(0)}.",
                phase="semantic",
                line=line,
                section=section,
                raw_text=match.group(0),
            )
        )

    period = ClinicalDatePeriod(
        raw_text=match.group(0),
        start=start_date,
        end=end_date,
        delta_time=end_date.value - start_date.value,
    )
    return DateMatch(value=period, start=match.start(), end=match.end())


def find_first_date(
    text: str,
    *,
    reference_datetime: datetime | None,
    diagnostics: list[CompilerDiagnostic],
    line: int | None = None,
    section: str | None = None,
) -> DateMatch | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    parsed = parse_clinical_date(
        match.group("date"),
        reference_datetime=reference_datetime,
        diagnostics=diagnostics,
        line=line,
        section=section,
    )
    if parsed is None:
        return None
    return DateMatch(value=parsed, start=match.start(), end=match.end())


def parse_clinical_date(
    text: str,
    *,
    reference_datetime: datetime | None,
    diagnostics: list[CompilerDiagnostic],
    line: int | None = None,
    section: str | None = None,
) -> ClinicalDate | None:
    parts = _parse_date_parts(text)
    if parts is None:
        return None

    day = int(parts.day)
    month = int(parts.month)
    explicit_year = parts.year_text is not None
    inferred_year: int | None = None
    if explicit_year:
        year = _normalize_year(parts.year_text or "")
    elif reference_datetime is not None:
        year = reference_datetime.year
        try:
            candidate = date(year, month, day)
            if candidate > reference_datetime.date():
                year -= 1
            inferred_year = year
        except ValueError:
            # Erro será emitido abaixo ao tentar montar o datetime.
            inferred_year = year
    else:
        diagnostics.append(
            CompilerDiagnostic(
                severity="error",
                code="date_without_reference_year",
                message=f"Data sem ano e sem data explícita no cabeçalho: {text}.",
                phase="semantic",
                line=line,
                section=section,
                raw_text=text,
            )
        )
        return None

    hour = 0
    minute = 0
    precision = "day"
    if parts.time_text:
        hour_text, minute_text = parts.time_text.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
        precision = "minute"

    try:
        value = datetime.combine(date(year, month, day), time(hour, minute))
    except ValueError as exc:
        diagnostics.append(
            CompilerDiagnostic(
                severity="error",
                code="invalid_date",
                message=f"Data inválida: {text} ({exc}).",
                phase="semantic",
                line=line,
                section=section,
                raw_text=text,
            )
        )
        return None

    return ClinicalDate(
        raw_text=text,
        value=value,
        precision=precision,  # type: ignore[arg-type]
        explicit_year=explicit_year,
        inferred_year=inferred_year,
    )


def remove_date_span(text: str, start: int, end: int) -> str:
    """Remove uma data/período e também parênteses externos quando a data está sozinha neles."""
    left = start
    right = end
    while left > 0 and text[left - 1].isspace():
        left -= 1
    while right < len(text) and text[right].isspace():
        right += 1
    if left > 0 and right < len(text) and text[left - 1] == "(" and text[right] == ")":
        left -= 1
        right += 1
    return " ".join((text[:left] + " " + text[right:]).split())


def extract_reference_datetime(text: str) -> datetime | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    date_text = match.group("date")
    parts = _parse_date_parts(date_text)
    if parts is None or parts.year_text is None:
        return None
    diagnostics: list[CompilerDiagnostic] = []
    parsed = parse_clinical_date(
        date_text,
        reference_datetime=None,
        diagnostics=diagnostics,
    )
    return parsed.value if parsed is not None else None


@dataclass(slots=True)
class _DateParts:
    day: str
    month: str
    year_text: str | None
    time_text: str | None


def _parse_date_parts(text: str) -> _DateParts | None:
    clean = text.strip()
    match = re.fullmatch(
        r"(?P<day>\d{1,2})/(?P<month>\d{1,2})(?:/(?P<year>\d{2,4}))?(?:\s+(?P<time>\d{1,2}:\d{2}))?",
        clean,
    )
    if not match:
        return None
    return _DateParts(
        day=match.group("day"),
        month=match.group("month"),
        year_text=match.group("year"),
        time_text=match.group("time"),
    )


def _normalize_year(year_text: str) -> int:
    year = int(year_text)
    if year < 100:
        return 2000 + year
    return year
