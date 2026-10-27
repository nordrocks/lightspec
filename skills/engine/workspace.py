"""Папка specs/: файлы main, фича, части delta и ADR.

Каждый файл разбирается один раз. Части дальше живут как узлы дерева и их строки: свойства изменения
снимаются по узлам `Prop`. main — набор файлов из шапки и блоков, delta накладывается на него в памяти
(merge.py). Собранный в памяти файл main разбирается заново целиком — для проверок.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import form
from .ident import prop_idents
from .paths import Location, locate, main_bind, main_entity
from .props import CHANGE, CHANGE_PROPS, NONE, SOURCE
from .syntax import Document, Part, parse

HEADER = "#"
DELTA = "delta"
REPLACES = "Заменяет"
# Части delta, которыми владеет скил документа: rules.md, «Доступ к сущностям».
OWNERS = {"spec": ("requirements", "contracts"), "plan": ("domain-docs", "architecture", "conventions", "project-doc", "adr")}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_blank(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def source_id(value: str | None) -> str | None:
    """Фича из `Источник:`: `feature:007-login-lockout` → 007-login-lockout, `None` → None."""
    return None if value in (None, NONE) else value.removeprefix("feature:")


@dataclass
class Fragment:
    """Часть в своём документе: узел дерева и строки от заголовка до следующей части."""
    part: Part
    lines: list[str]
    doc: Document

    def prop(self, name: str) -> str | None:
        return self.part.prop(name)

    def without(self, names: tuple[str, ...]) -> list[str]:
        """Строки без свойств с этими именами: по первому вхождению каждого. Повтор остаётся для проверки."""
        drop, seen = set(), set()
        for p in self.part.props:
            if p.name in names and p.name not in seen:
                drop.add(p.line - self.part.line)
                seen.add(p.name)
        return [line for i, line in enumerate(self.lines) if i not in drop]

    def with_source(self, slug: str, names: tuple[str, ...]) -> list[str]:
        """Как часть ляжет в main: без этих свойств, `Источник:` фичи первым, пустая строка в конце."""
        lines = strip_blank(self.without(names))
        return lines[:1] + [f"{SOURCE}: feature:{slug}"] + lines[1:] + [""]


def fragments(doc: Document) -> list[Fragment]:
    """Шапка и блоки документа. Строки шапки — до первого блока, блока — до следующего."""
    starts = [b.line for b in doc.blocks] + [len(doc.lines)]
    out = [Fragment(doc.header, doc.lines[doc.header.line:starts[0]], doc)] if doc.header else []
    return out + [Fragment(b, doc.lines[b.line:starts[i + 1]], doc) for i, b in enumerate(doc.blocks)]


# --- main ---

@dataclass
class Block:
    name: str
    frag: Fragment    # узел в документе, из которого блок взят: файл main или файл delta
    lines: list[str]  # строки в main
    source: str | None

    @property
    def part(self) -> Part:
        return self.frag.part


@dataclass
class MainFile:
    rel: str      # путь от main/
    entity: str
    header: list[str] = field(default_factory=list)  # строки до первого блока
    header_source: str | None = None
    has_head: bool = False
    blocks: list[Block] = field(default_factory=list)

    @classmethod
    def from_text(cls, rel: str, text: str) -> MainFile:
        doc = parse(text)
        f = cls(rel, main_entity(rel))
        f.header = doc.lines[:doc.blocks[0].line] if doc.blocks else list(doc.lines)
        if doc.header:
            f.has_head = True
            f.header_source = source_id(doc.header.prop(SOURCE))
        for frag in fragments(doc):
            if frag.part.level == 2:
                name = form.block_name(f.entity, frag.part.title)
                f.blocks.append(Block(name, frag, frag.lines, source_id(frag.prop(SOURCE))))
        return f

    @property
    def empty(self) -> bool:
        return not any(line.strip() for line in self.header) and not self.blocks

    def text(self) -> str:
        lines = list(self.header)
        for b in self.blocks:
            if lines and lines[-1].strip():
                lines.append("")
            lines += b.lines
        return "\n".join(lines).rstrip("\n") + "\n"

    def doc(self) -> Document:
        """Файл, собранный в памяти, — дерево."""
        return parse(self.text())

    def find(self, name: str) -> Block | None:
        return next((b for b in self.blocks if b.name == name), None)


class Main:
    """Файлы main, кроме ADR. Файлы не по путям из «Сущностей» в rules.md — в bad, не читаются.

    Имена ADR проверяет main_adrs.
    """

    def __init__(self, root: Path):
        self.root = root
        self.files: dict[str, MainFile] = {}
        self.original: dict[str, str] = {}
        self.bad: list[str] = []
        for path in sorted(root.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            entity = main_entity(rel)
            if entity is None and not rel.startswith("_project/adr/"):
                self.bad.append(f"{rel}: путь не по «Сущностям» → rules.md")
            elif entity and entity != "adr":
                text = read(path)
                self.files[rel] = MainFile.from_text(rel, text)
                self.original[rel] = text.rstrip("\n") + "\n"

    def file(self, rel: str) -> MainFile:
        if rel not in self.files:
            self.files[rel] = MainFile(rel, main_entity(rel))
        return self.files[rel]

    def locate(self, entity: str, name: str, rel: str) -> tuple[MainFile, Block] | None:
        """Блок в main. Требование ищется по ID во всём домене."""
        if entity == "requirements":
            domain = rel.split("/")[0] + "/"
            candidates = [f for r, f in self.files.items() if f.entity == "requirements" and r.startswith(domain)]
        else:
            candidates = [self.files[rel]] if rel in self.files else []
        for f in candidates:
            block = f.find(name)
            if block:
                return f, block
        return None

    def has_source(self, slug: str) -> bool:
        """В main уже есть блок или шапка от этой фичи: вливание прерывалось."""
        return any(f.header_source == slug or any(b.source == slug for b in f.blocks) for f in self.files.values())

    def problems(self, entities: set[str]) -> list[str]:
        """Пути файлов main, файлы этих сущностей по схемам, ID требования уникален в домене."""
        out = list(self.bad)
        for rel, f in self.files.items():
            if f.entity in entities and not f.empty:
                out += form.check(rel, f.doc(), f.entity, main_bind(rel), lines=False)
        return out + (self.unique_requirements() if "requirements" in entities else [])

    def unique_requirements(self) -> list[str]:
        """ID требования уникален в домене: syntax.md, «Схема сущности»."""
        seen: dict[str, str] = {}
        out = []
        for rel, f in sorted(self.files.items()):
            if f.entity == "requirements":
                for b in f.blocks:
                    key = rel.split("/")[0] + "/" + b.name
                    if key in seen and seen[key] != rel:
                        out.append(f"{rel}, {b.name}: ID уже есть в {seen[key]}")
                    seen.setdefault(key, rel)
        return out


# --- ADR ---

@dataclass
class Adr:
    path: Path
    slug: str          # ID ADR
    head: Fragment     # файл целиком: шапка и всё после неё
    doc: Document

    @property
    def replaces(self) -> list[str]:
        return prop_idents(self.head.prop(REPLACES))

    @property
    def content(self) -> str:
        """Текст решения без свойств изменения, `Источник:` и `Заменяет:`: так ADR фичи сравнивается с main."""
        return "\n".join(self.head.without(CHANGE_PROPS + (REPLACES,))).strip()

    def main_lines(self, slug: str) -> list[str]:
        """ADR фичи, как он ляжет в main: `Источник:` фичи, без `Заменяет:`."""
        return self.head.with_source(slug, CHANGE_PROPS + (REPLACES,))


def adr_of(path: Path, slug: str, doc: Document) -> Adr | None:
    if doc.header is None:
        return None
    return Adr(path, slug, Fragment(doc.header, doc.lines[doc.header.line:], doc), doc)


def main_adrs(root: Path) -> tuple[list[Adr], list[str]]:
    """ADR в main/_project/adr/ и файлы с именем не по правилу."""
    adrs, bad = [], []
    for path in sorted((root / "_project" / "adr").glob("*.md")):
        if not main_entity(f"_project/adr/{path.name}"):
            bad.append(f"_project/adr/{path.name}: имя не `<ID ADR>.md`{form.SEE_ADR}")
        elif adr := adr_of(path, path.stem, parse(read(path))):
            adrs.append(adr)
    return adrs, bad


# --- фича ---

@dataclass
class SourceFile:
    path: Path
    loc: Location
    doc: Document


@dataclass
class Change:
    """Часть delta: шапка или блок со свойствами изменения. У ADR часть — файл целиком."""
    file: str      # путь от delta/: он же путь от main/
    entity: str
    name: str      # имя части: `#` у шапки
    frag: Fragment

    @property
    def part(self) -> Part:
        return self.frag.part

    def prop(self, name: str) -> str | None:
        return self.frag.prop(name)

    @property
    def action(self) -> str | None:
        return self.prop(CHANGE)

    @property
    def source(self) -> str | None:
        return source_id(self.prop(SOURCE))

    @property
    def clean(self) -> list[str]:
        """Часть без свойств изменения."""
        return self.frag.without(CHANGE_PROPS)

    def main_lines(self, slug: str) -> list[str]:
        """Часть, как она ляжет в main."""
        return self.frag.with_source(slug, CHANGE_PROPS)

    @property
    def key(self) -> tuple[str, str]:
        return self.file, self.name

    @property
    def label(self) -> str:
        return f"{self.action} {self.file} — {self.name}"


@dataclass
class Feature:
    folder: Path
    spec: SourceFile
    plan: SourceFile | None
    delta: list[SourceFile]
    changes: list[Change]
    adrs: list[Adr]  # ADR фичи из delta/_project/adr/
    bad: list[str]   # пути delta/ не по правилам и ADR без шапки

    @property
    def slug(self) -> str:
        return self.folder.name

    @property
    def specs(self) -> Path:
        return self.folder.parent.parent

    @property
    def status(self) -> str | None:
        head = self.spec.doc.header
        return head.prop("Статус") if head else None

    def owned(self, doc: str) -> list[Change]:
        """Части delta, которыми владеет скил документа."""
        return [c for c in self.changes if c.entity in OWNERS[doc]]

    @property
    def blocks(self) -> list[Change]:
        """Части, которые вливаются в файлы main. ADR переносится отдельно."""
        return [c for c in self.changes if c.entity != "adr"]

    @property
    def tasks(self) -> list[Part]:
        return form.tasks(self.plan.doc) if self.plan else []


def load_feature(folder: Path) -> Feature:
    specs = folder.parent.parent

    def source(path: Path, loc: Location | None = None) -> SourceFile:
        loc = loc or locate(path.relative_to(specs).as_posix())
        return SourceFile(path, loc, parse(read(path), loc.start))

    spec = source(folder / "spec.md")
    plan = source(folder / "plan.md") if (folder / "plan.md").is_file() else None
    delta, changes, adrs, bad = [], [], [], []
    root = folder / DELTA
    for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        loc = locate(path.relative_to(specs).as_posix())
        if loc is None or loc.feature != folder.name:
            bad.append(f"delta/{rel}: путь не повторяет файл main → formats/delta.md")
            continue
        src = source(path, loc)
        delta.append(src)
        if loc.entity == "adr":
            adr = adr_of(path, path.stem, src.doc)
            if adr is None:
                bad.append(f"delta/{rel}: нет шапки `#`{form.SEE_ADR}")
                continue
            adrs.append(adr)
            changes.append(Change(rel, "adr", HEADER, adr.head))
            continue
        for frag in fragments(src.doc):
            name = HEADER if frag.part.level == 1 else form.block_name(loc.entity, frag.part.title)
            changes.append(Change(rel, loc.entity, name, frag))
    return Feature(folder, spec, plan, delta, changes, adrs, bad)


def feature_names(specs: Path) -> set[str]:
    """Фичи в new/ и archive/."""
    return {d.name for folder in ("new", "archive") if (specs / folder).is_dir()
            for d in (specs / folder).iterdir() if d.is_dir()}
