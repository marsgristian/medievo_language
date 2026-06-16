from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RemovedText:
    text: str
    removed: list[str]


def normalize_spaces(text: str) -> str:
    return " ".join(text.strip().split())


def split_top_level(text: str, sep: str) -> list[str]:
    """Divide por um separador fora de parênteses e comentários /* */."""
    parts: list[str] = []
    current: list[str] = []
    paren_depth = 0
    i = 0
    while i < len(text):
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                current.append(text[i:])
                break
            current.append(text[i : end + 2])
            i = end + 2
            continue
        ch = text[i]
        if ch == "(":
            paren_depth += 1
            current.append(ch)
        elif ch == ")" and paren_depth > 0:
            paren_depth -= 1
            current.append(ch)
        elif ch == sep and paren_depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append("".join(current).strip())
    return parts


def contains_top_level(text: str, needle: str) -> bool:
    """Retorna True quando `needle` aparece fora de parenteses e comentarios."""
    paren_depth = 0
    i = 0
    while i < len(text):
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                return False
            i = end + 2
            continue
        ch = text[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")" and paren_depth > 0:
            paren_depth -= 1
        elif ch == needle and paren_depth == 0:
            return True
        i += 1
    return False


def remove_ignored_comments(text: str) -> RemovedText:
    """Remove comentários ignoráveis /* ... */ preservando o conteúdo removido."""
    removed: list[str] = []
    output: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                removed.append(text[i + 2 :].strip())
                break
            removed.append(text[i + 2 : end].strip())
            output.append(" ")
            i = end + 2
            continue
        output.append(text[i])
        i += 1
    return RemovedText(text=normalize_spaces("".join(output)), removed=[x for x in removed if x])


def extract_parenthesized_values(text: str) -> tuple[str, list[str]]:
    """Extrai valores entre parênteses fora de comentários ignoráveis.

    Se a extração deixaria o texto principal vazio, preserva o texto original. Isso evita
    transformar subseções como `> (02/06):` em nome vazio.
    """
    values: list[str] = []
    output: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "(":
            depth = 1
            j = i + 1
            while j < len(text) and depth > 0:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                values.append(text[i + 1 : j - 1].strip())
                output.append(" ")
                i = j
                continue
        output.append(text[i])
        i += 1
    cleaned = normalize_spaces("".join(output))
    values = [value for value in values if value]
    if not cleaned and values:
        return normalize_spaces(text), []
    return cleaned, values


def find_structural_colon(text: str) -> int | None:
    """Retorna o índice do primeiro ':' estrutural.

    Ignora ':' dentro de parênteses, dentro de comentários /* */ e ':' de horário HH:MM.
    """
    paren_depth = 0
    i = 0
    while i < len(text):
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                return None
            i = end + 2
            continue
        ch = text[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")" and paren_depth > 0:
            paren_depth -= 1
        elif ch == ":" and paren_depth == 0:
            before = text[max(0, i - 2) : i]
            after = text[i + 1 : i + 3]
            if before.strip().isdigit() and len(after) == 2 and after.isdigit():
                i += 1
                continue
            return i
        i += 1
    return None
