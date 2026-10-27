"""Ссылки в дереве: syntax.md, «Поиск ссылок».

Свойства со ссылками читаются целиком (ident.prop_idents). Остальные свойства и тело вне fence — поиском
по строке. Заголовки и fence не читаются.
"""
from __future__ import annotations

from .ident import Ref, find_refs
from .props import REF_PROPS
from .syntax import Document, Part


def part_text_refs(doc: Document, part: Part) -> list[Ref]:
    """Ссылки в тексте части и её разделов."""
    out = [r for p in part.props if p.name not in REF_PROPS for r in find_refs(p.value)]
    out += [r for line in doc.body_text(part) for r in find_refs(line)]
    return out + [r for s in part.sections for r in part_text_refs(doc, s)]


def text_refs(doc: Document) -> list[Ref]:
    return [r for part in doc.parts for r in part_text_refs(doc, part)]
