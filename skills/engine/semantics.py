"""Семантика файла: дерево против схемы его сущности (schema.py). Правила — «Схема сущности» в syntax.md.

Проверяет заголовки по шаблонам, порядок и повторы частей, обязательные части и свойства, порядок
и значения свойств, «только разделы», идентификаторы из пути, уникальность имён в файле и блоке.
Уникальность ID требования в домене и связи между файлами — в links.py.
"""
from __future__ import annotations

from .ident import components
from .props import SEE_SYNTAX, value_errors
from .schema import Row, Schema
from .syntax import Document, Part

_EXTRA = "Если это текст — отдели его пустой строкой"


class _Checker:
    def __init__(self, doc: Document, schema: Schema, bind: dict[str, str], prefix: str):
        self.doc = doc
        self.prefix = prefix
        self.bind = bind
        self.see = f" → formats/{schema.format}"
        self.schema = schema
        self.out: list[str] = []

    def place(self, where: str) -> str:
        """Место: файл, затем часть. Пустая часть — файл целиком."""
        return f"{self.prefix}, {where}" if where else self.prefix

    def add(self, where: str, message: str) -> None:
        self.out.append(f"{self.place(where)}: {message}{self.see}")

    def run(self) -> list[str]:
        head, row = self.doc.header, self.schema.header
        if head is None:
            if row and row.required:
                self.add("", f"нет шапки {row.text}")
        elif row is None or not row.match(head.title):
            self.add("шапка", f"«{head.title}» не по шаблону {row.text if row else '—'}")
        else:
            self.part(head, row, "шапка")
        for block, brow in self.level(None, self.doc.blocks, self.schema.blocks, "блок"):
            self.part(block, brow, brow.name(block.title))
        return self.out

    def level(self, parent: str | None, parts: list[Part], rows: list[Row], noun: str) -> list[tuple[Part, Row]]:
        """Части одного уровня: шаблоны, порядок, повторы, обязательные, уникальность имён."""
        where = parent or ""
        matched: list[tuple[Part, Row]] = []
        for part in parts:
            row = next((r for r in rows if r.match(part.title)), None)
            if row is None:
                variants = ", ".join(r.text for r in rows) or "нет"
                self.add(where, f"{noun} «{part.title}» не по формату. Возможные: {variants}")
            else:
                matched.append((part, row))
        last = -1
        for part, row in matched:
            if row.index < last:
                self.add(where, f"{noun} «{part.title}» не на месте. Порядок: {', '.join(r.text for r in rows)}")
            last = max(last, row.index)
        count: dict[int, int] = {}
        names: dict[str, int] = {}
        for part, row in matched:
            count[row.index] = count.get(row.index, 0) + 1
            if count[row.index] == 2 and not row.repeat:
                self.add(where, f"{noun} {row.text} повторяется")
            name = row.name(part.title)
            names[name] = names.get(name, 0) + 1
            if names[name] == 2 and row.repeat:
                self.add(where, f"имя «{name}» повторяется")
        for row in rows:
            if row.required and row.index not in count:
                self.add(where, f"нет {row.text}")
        return matched

    def part(self, part: Part, row: Row, where: str) -> None:
        self.bound(part, row, where)
        self.props(part, row, where)
        if row.only_sections and any(self.doc.lines[b.line].strip() for b in part.body):
            self.add(where, "текст до разделов — здесь только разделы `###`")
        if part.level != 2:
            return
        rows, dep = row.sections, row.depends
        if dep and part.prop(dep.prop) in dep.cases:
            own = set(dep.cases[part.prop(dep.prop)][1])
            rows = [r for r in rows if r.label not in dep.sections or r.label in own]
        for s, srow in self.level(where, part.sections, rows, "раздел"):
            self.part(s, srow, f"{where}, «{s.title}»")

    def bound(self, part: Part, row: Row, where: str) -> None:
        """Идентификаторы в заголовке совпадают с путём файла."""
        _, found = row.match(part.title)
        for ident, value in found:
            for name, got in components(ident, value).items():
                want = self.bind.get(name)
                if want is not None and got != want:
                    self.add(where, f"`<{name}>` в заголовке — «{got}», по пути файла — «{want}»")

    def props(self, part: Part, row: Row, where: str) -> None:
        allowed = list(row.props)
        dep, values = row.depends, None
        if dep:
            values = tuple(dep.cases)
            key = part.prop(dep.prop)
            if key in dep.cases:
                own = set(dep.cases[key][0])
                allowed = [(n, r) for n, r in allowed if n not in dep.props or n in own]
        names = [n for n, _ in allowed]
        seen: list[str] = []
        for p in part.props:
            if p.name in seen:
                self.add(where, f"свойство «{p.name}:» повторяется")
                continue
            seen.append(p.name)
            if p.name in names:
                self.out += value_errors(self.place(where), p.name, p.value, values if dep and p.name == dep.prop else None)
            elif dep and p.name in dep.props:
                self.add(where, f"свойство «{p.name}:» не для «{dep.prop}: {part.prop(dep.prop)}»")
            else:
                self.out.append(f"{self.place(where)}: лишнее свойство «{p.name}:». {_EXTRA}{SEE_SYNTAX}")
        for name, required in allowed:
            if required and name not in seen:
                self.add(where, f"нет свойства «{name}:»")
        order = [n for n in seen if n in names]
        if order != sorted(order, key=names.index):
            self.add(where, f"свойства не по порядку. Порядок: {', '.join(n + ':' for n in names if n in order)}")


def check(doc: Document, schema: Schema, bind: dict[str, str], prefix: str) -> list[str]:
    """Нарушения схемы в файле без ошибок синтаксиса. prefix — файл. Место — часть файла, без номеров строк."""
    return _Checker(doc, schema, bind, prefix).run()
