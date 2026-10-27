"""Схемы сущностей: таблица «Структура» и таблица зависимых свойств из formats/<формат>.md.

Правила чтения — «Схема сущности» в syntax.md. Ошибка в «Структуре» — FormatError: это ошибка
фреймворка, а не файла в specs/. Команда examples проверяет все форматы.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .ident import IDENTS
from .props import NAMES
from .syntax import Document, Part, parse

FORMATS = Path(__file__).resolve().parent.parent / "formats"
STRUCTURE = "Структура"
ONLY_SECTIONS = "только разделы"
# Сущность → файл формата.
FILES = {
    "requirements": "requirements.md",
    "domain-docs": "domain-docs.md",
    "contracts": "contracts.md",
    "architecture": "project.md",
    "conventions": "project.md",
    "project-doc": "project.md",
    "adr": "adr.md",
    "spec": "spec.md",
    "plan": "plan.md",
}
_CODE = re.compile(r"`([^`]+)`")
_PLACEHOLDER = re.compile(r"<([^<>]+)>")
_CELL = re.compile(r"(?<!\\)\|")


class FormatError(Exception):
    pass


@dataclass
class Template:
    """Шаблон заголовка: `## <ID требования>: <название>`."""
    text: str
    level: int
    rx: re.Pattern
    idents: list[str]  # идентификатор каждой группы, "" — любой текст
    named: bool        # начинается с идентификатора: он — имя части

    def match(self, title: str) -> list[tuple[str, str]] | None:
        """[(идентификатор, значение)] заголовка. None — заголовок не по шаблону."""
        m = self.rx.fullmatch(title)
        if m is None:
            return None
        return [(i, v) for i, v in zip(self.idents, m.groups()) if i]


@dataclass
class Depends:
    """Свойства и разделы по значению свойства: таблица вида «Элемент»."""
    prop: str
    cases: dict[str, tuple[list[str], list[str]]]  # значение → (свойства, метки разделов)

    @property
    def props(self) -> set[str]:
        return {p for props, _ in self.cases.values() for p in props}

    @property
    def sections(self) -> set[str]:
        return {s for _, sections in self.cases.values() for s in sections}


@dataclass
class Row:
    """Строка заголовка «Структуры» и строки её свойств."""
    label: str
    templates: list[Template]
    required: bool
    only_sections: bool
    index: int
    props: list[tuple[str, bool]] = field(default_factory=list)  # (имя, обязательно)
    sections: list[Row] = field(default_factory=list)
    depends: Depends | None = None

    @property
    def level(self) -> int:
        return self.templates[0].level

    @property
    def text(self) -> str:
        return " или ".join(f"`{t.text}`" for t in self.templates)

    @property
    def repeat(self) -> bool:
        return any(t.idents for t in self.templates)

    def match(self, title: str) -> tuple[Template, list[tuple[str, str]]] | None:
        for t in self.templates:
            found = t.match(title)
            if found is not None:
                return t, found
        return None

    def name(self, title: str) -> str:
        """Имя части: идентификатор, с которого начинается шаблон, иначе заголовок целиком."""
        found = self.match(title)
        if found and found[0].named and found[1]:
            return found[1][0][1]
        return title


@dataclass
class Schema:
    format: str
    header: Row | None
    blocks: list[Row]

    def rows(self) -> list[Row]:
        out = [self.header] if self.header else []
        for b in self.blocks:
            out += [b, *b.sections]
        return out

    def block_row(self, title: str) -> Row | None:
        return next((r for r in self.blocks if r.match(title)), None)

    def block_name(self, title: str) -> str:
        row = self.block_row(title)
        return row.name(title) if row else title


def _template(text: str, where: str) -> Template:
    m = re.fullmatch(r"(#{1,3}) (.+)", text)
    if not m:
        raise FormatError(f"{where}: шаблон «{text}» — не заголовок `#`–`###`")
    body, rx, idents, pos = m.group(2), "", [], 0
    for p in _PLACEHOLDER.finditer(body):
        rx += re.escape(body[pos:p.start()])
        name = p.group(1)
        rx += f"({IDENTS[name]})" if name in IDENTS else "(.+)"
        idents.append(name if name in IDENTS else "")
        pos = p.end()
    rx += re.escape(body[pos:])
    first = _PLACEHOLDER.match(body)
    return Template(text, len(m.group(1)), re.compile(rx), idents, bool(first) and first.group(1) in IDENTS)


def _table(doc: Document, part: Part) -> list[dict[str, str]]:
    """Первая таблица в теле части вне fence: строки как {столбец: ячейка}."""
    rows: list[list[str]] = []
    for line in doc.body_text(part):
        if line.startswith("|"):
            rows.append([c.strip().replace("\\|", "|") for c in _CELL.split(line.strip())[1:-1]])
        elif rows:
            break
    return [dict(zip(rows[0], r)) for r in rows[2:]] if len(rows) > 2 else []


def _required(cell: str, where: str) -> bool:
    if cell == "да":
        return True
    if cell == "нет" or cell.startswith("если "):
        return False
    raise FormatError(f"{where}: «Обязательно» — `да`, `нет` или `если <условие>`, а не «{cell}»")


def _prop(cell: str, where: str) -> str:
    m = re.fullmatch(r"`([^`]+):`", cell)
    if not m:
        raise FormatError(f"{where}: свойство «{cell}» — не `<Имя>:`")
    if m.group(1) not in NAMES:
        raise FormatError(f"{where}: свойства «{m.group(1)}:» нет в «Реестре» syntax.md")
    return m.group(1)


def _structure(name: str, doc: Document, part: Part) -> tuple[Row | None, list[Row]]:
    header, blocks, by_label = None, [], {}
    for i, cells in enumerate(_table(doc, part)):
        where = f"formats/{name}, «{STRUCTURE}», строка {i + 1}"
        label, heading, prop = cells.get("Что", ""), cells.get("Заголовок", ""), cells.get("Свойство", "")
        required = _required(cells.get("Обязательно", ""), where)
        if heading:
            templates = [_template(t, where) for t in _CODE.findall(heading)]
            if not templates or len({t.level for t in templates}) > 1:
                raise FormatError(f"{where}: в «Заголовке» нет шаблона или у вариантов разный уровень")
            row = Row(label, templates, required, cells.get("Содержание", "").startswith(ONLY_SECTIONS), i)
            by_label[label] = row
            if row.level == 1:
                header = row
            elif row.level == 2:
                blocks.append(row)
            elif blocks:
                blocks[-1].sections.append(row)
            else:
                raise FormatError(f"{where}: раздел `###` до первого блока `##`")
        elif prop and prop != "—":
            if label not in by_label:
                raise FormatError(f"{where}: свойство без строки заголовка «{label}» выше")
            by_label[label].props.append((_prop(prop, where), required))
    return header, blocks


def _depends(name: str, doc: Document, part: Part, rows: list[Row]) -> None:
    """Таблица `| `<Имя>:` | Свойства | Разделы |` — к строке схемы с этим свойством."""
    data = _table(doc, part)
    if not data:
        return
    first = next(iter(data[0]))
    m = re.fullmatch(r"`([^`]+):`", first)
    if not m or "Свойства" not in data[0] or "Разделы" not in data[0]:
        return
    where = f"formats/{name}, «{part.title}»"
    owner = next((r for r in rows if any(p == m.group(1) for p, _ in r.props)), None)
    if owner is None:
        raise FormatError(f"{where}: свойства «{m.group(1)}:» нет в «{STRUCTURE}»")
    labels = {s.label for s in owner.sections}
    cases = {}
    for cells in data:
        sections = [s.strip() for s in cells["Разделы"].split(",") if s.strip() not in ("", "—")]
        unknown = [s for s in sections if s not in labels]
        if unknown:
            raise FormatError(f"{where}: раздела «{unknown[0]}» нет в «{STRUCTURE}»")
        cases[cells[first]] = ([p.rstrip(":") for p in _CODE.findall(cells["Свойства"])], sections)
    owner.depends = Depends(m.group(1), cases)


@cache
def load(entity: str) -> Schema:
    """Схема сущности из её формата."""
    name = FILES[entity]
    doc = parse((FORMATS / name).read_text(encoding="utf-8"))
    if doc.problems:
        p = doc.problems[0]
        raise FormatError(f"formats/{name}:{p.line + 1}: {p.message}")
    part = next((b for b in doc.blocks if b.title == STRUCTURE), None)
    if part is None:
        raise FormatError(f"formats/{name}: нет блока «{STRUCTURE}»")
    header, blocks = _structure(name, doc, part)
    schema = Schema(name, header, blocks)
    for other in doc.blocks:
        if other is not part:
            _depends(name, doc, other, schema.rows())
    return schema
