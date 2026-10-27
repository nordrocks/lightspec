"""Форма файла: синтаксис (syntax.py), затем схема сущности (semantics.py). Сообщения — с местом в файле.

Файл с ошибкой синтаксиса по схеме не проверяется.
"""
from __future__ import annotations

import re

from . import schema, semantics
from .ident import IDENTS
from .props import SEE_SYNTAX
from .syntax import Document, Part

SEE_ADR = " → formats/adr.md"
SEE_PLAN = " → formats/plan.md"
# Задача plan и её отметка: `[x]` — выполнена. formats/plan.md, «Задача».
TASK = re.compile(rf"^\[([ x])\] Задача ({IDENTS['номер']}): .+$")
TASKS = "Задачи"


def block_name(entity: str, title: str) -> str:
    """Имя блока по шаблону его строки в «Структуре»."""
    return schema.load(entity).block_name(title)


def syntax(where: str, doc: Document, lines: bool = True) -> list[str]:
    """Ошибки разбора. lines — место строкой файла, иначе частью: файл main может быть собран в памяти."""
    if lines:
        return [f"{where}:{p.line + 1}: {p.message}{SEE_SYNTAX}" for p in doc.problems]
    return [f"{where}, {doc.where(p.line)}: {p.message}{SEE_SYNTAX}" for p in doc.problems]


def check(where: str, doc: Document, entity: str, bind: dict[str, str], lines: bool = True) -> list[str]:
    """Синтаксис, а без его ошибок — схема сущности."""
    if doc.problems:
        return syntax(where, doc, lines)
    return semantics.check(doc, schema.load(entity), bind, where)


def tasks(doc: Document) -> list[Part]:
    block = next((b for b in doc.blocks if b.title == TASKS), None)
    return block.sections if block else []
