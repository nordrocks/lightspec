"""Лексика: строки файла → токены. README.md пакета, «Лексика».

Строка — ровно один токен. Автомат с двумя режимами: обычным и fence.
Строка с ошибкой лексики токена не даёт: ошибка в списке, строка пропускается.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BLANK = "BLANK"
FENCE_OPEN = "FENCE-OPEN"
FENCE_CLOSE = "FENCE-CLOSE"
H1, H2, H3 = "H1", "H2", "H3"
PROP = "PROP"
LINE = "LINE"
EOF = "EOF"
HEADINGS = (H1, H2, H3)

_LETTER = "A-Za-zА-Яа-яЁё"
_PROP = re.compile(rf"^([A-ZА-ЯЁ][{_LETTER}]*(?: [{_LETTER}]+)*): (\S.*)$")
_HEADING = re.compile(r"^(#+)(?: (.*))?$")
_FENCE_OPEN = re.compile(r"^(`{3,})[^`]*$")
_FENCE_CLOSE = re.compile(r"^(`{3,})$")


@dataclass(frozen=True)
class Token:
    kind: str
    line: int        # номер строки с 0. У EOF — число строк
    value: str = ""  # заголовок или имя свойства
    extra: str = ""  # значение свойства


@dataclass(frozen=True)
class Problem:
    line: int
    message: str


def lex(lines: list[str]) -> tuple[list[Token], list[Problem]]:
    tokens: list[Token] = []
    problems: list[Problem] = []
    fence = 0  # число бэктиков открытого fence, 0 — обычный режим
    for no, line in enumerate(lines):
        if fence:
            m = _FENCE_CLOSE.match(line)
            if m and len(m.group(1)) >= fence:
                tokens.append(Token(FENCE_CLOSE, no))
                fence = 0
            else:
                tokens.append(Token(LINE, no))
            continue
        if not line.strip(" "):
            tokens.append(Token(BLANK, no))
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = len(m.group(1))
            tokens.append(Token(FENCE_OPEN, no))
            continue
        m = _HEADING.match(line)
        if m:
            level, title = len(m.group(1)), (m.group(2) or "").strip()
            if level > 3:
                problems.append(Problem(no, f"заголовок «{line.strip()}» глубже `###`"))
            elif not title:
                problems.append(Problem(no, "пустой заголовок"))
            else:
                tokens.append(Token(HEADINGS[level - 1], no, title))
            continue
        m = _PROP.match(line)
        if m:
            tokens.append(Token(PROP, no, m.group(1), m.group(2).rstrip()))
            continue
        tokens.append(Token(LINE, no))
    tokens.append(Token(EOF, len(lines)))
    return tokens, problems
