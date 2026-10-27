"""Вливание delta в main: форма delta, конфликты, наложение в памяти, запись и перенос ADR.

Повторный запуск после прерванного вливания пропускает уже влитые блоки и перенесённые ADR.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import form
from .ident import IDENTS
from .paths import main_bind
from .props import ACTIONS, CHANGE, CHANGE_PROPS, NONE, REASON, SOURCE
from .syntax import parse
from .workspace import HEADER, REPLACES, Adr, Block, Change, Feature, Main, main_adrs, strip_blank

SEE_DELTA = " → formats/delta.md"
SEE_ADR = form.SEE_ADR
CONFLICT = (" → блок в main изменила другая фича. Следующий шаг — sdd-spec:"
            " верни spec в draft и обнови delta по текущему main")


def same_text(a: list[str], b: list[str]) -> bool:
    """Тексты блоков равны без пустых строк в конце."""
    return "\n".join(a).rstrip() == "\n".join(b).rstrip()


# --- форма delta ---

def check_form(feature: Feature) -> list[str]:
    """Пути и синтаксис файлов delta/, свойства изменения и их сочетания."""
    out = list(feature.bad)
    for src in feature.delta:
        out += form.syntax(f"delta/{src.loc.main_rel}", src.doc)
    keys = set()
    for c in feature.changes:
        where = f"delta/{c.file}, {c.name}"
        names = [p.name for p in c.part.props]
        if names[:3] != [CHANGE, SOURCE, REASON]:
            out.append(f"{where}: первые свойства не «{CHANGE}:», «{SOURCE}:», «{REASON}:»{SEE_DELTA}")
            continue
        action, source, reason = c.prop(CHANGE), c.prop(SOURCE), c.prop(REASON)
        if action not in ACTIONS:
            out.append(f"{where}: «{CHANGE}: {action}» не из {', '.join(ACTIONS)}{SEE_DELTA}")
            continue
        if action == "ADDED" and source != NONE:
            out.append(f"{where}: у ADDED «{SOURCE}: {NONE}»{SEE_DELTA}")
        if action != "ADDED" and not re.fullmatch("feature:" + IDENTS["ID фичи"], source):
            out.append(f"{where}: «{SOURCE}:» не `feature:<ID фичи>` — значение из блока в main{SEE_DELTA}")
        if action == "REMOVED" and reason == NONE:
            out.append(f"{where}: у REMOVED «{REASON}:» — почему часть удаляется{SEE_DELTA}")
        if action != "REMOVED" and reason != NONE:
            out.append(f"{where}: «{REASON}:» — только у REMOVED, здесь {NONE}{SEE_DELTA}")
        if action == "REMOVED" and any(line.strip() for line in c.clean[1:]):
            out.append(f"{where}: у REMOVED после свойств изменения ничего нет{SEE_DELTA}")
        if c.entity == "adr" and action != "ADDED":
            out.append(f"{where}: ADR — только ADDED, замена — «{REPLACES}:»{SEE_ADR}")
        if names.count(SOURCE) > 1:
            out.append(f"{where}: второй «{SOURCE}:» — в main его ставит вливание")
        if c.key in keys:
            out.append(f"{where}: вторая часть на блок {c.name}")
        keys.add(c.key)
    return out


# --- конфликты и наложение ---

def conflicts(main: Main, changes: list[Change], slug: str) -> list[str]:
    """delta против текущего main: блоки и источники на месте.

    Блок с `Источник:` этой фичи и тем же текстом уже влит прерванным запуском — не конфликт.
    """
    resumed = main.has_source(slug)
    out = []
    for c in changes:
        where = c.label
        expected = c.main_lines(slug)
        if c.name == HEADER:
            f = main.files.get(c.file)
            if f and f.has_head and f.header_source == slug and c.action != "REMOVED":
                if not same_text(strip_blank(f.header), expected):
                    out.append(f"{where}: в main шапка этой фичи, но текст другой")
                continue
            if c.action == "ADDED" and f:
                out.append(f"{where}: файл уже есть в main{CONFLICT}")
            if c.action != "ADDED":
                if not f:
                    if not (resumed and c.action == "REMOVED"):
                        out.append(f"{where}: файла нет в main{CONFLICT}")
                elif f.header_source != c.source:
                    out.append(f"{where}: в main источник {f.header_source}, в delta — {c.source}{CONFLICT}")
            continue
        found = main.locate(c.entity, c.name, c.file)
        if found and found[1].source == slug and c.action != "REMOVED":
            if not same_text(found[1].lines, expected):
                out.append(f"{where}: в main блок этой фичи, но текст другой")
            continue
        if c.action == "ADDED" and found:
            out.append(f"{where}: блок уже есть в main, в {found[0].rel}{CONFLICT}")
        if c.action != "ADDED":
            if not found:
                if not (resumed and c.action == "REMOVED"):
                    out.append(f"{where}: блока нет в main{CONFLICT}")
            elif found[1].source != c.source:
                out.append(f"{where}: в main источник {found[1].source}, в delta — {c.source}{CONFLICT}")
    return out


def apply(main: Main, changes: list[Change], slug: str) -> None:
    """Накладывает части delta на main в памяти."""
    for c in changes:
        if c.entity == "adr" or c.action not in ACTIONS:
            continue
        if c.name == HEADER:
            f = main.file(c.file)
            removed = c.action == "REMOVED"
            f.header = [] if removed else c.main_lines(slug)
            f.header_source, f.has_head = (None, False) if removed else (slug, True)
            continue
        found = main.locate(c.entity, c.name, c.file)
        if c.action == "REMOVED":
            if found:
                found[0].blocks.remove(found[1])
            continue
        block = Block(c.name, c.frag, c.main_lines(slug), slug)
        target = main.file(c.file)
        if found and found[0] is target:
            target.blocks[target.blocks.index(found[1])] = block
        else:
            if found:
                found[0].blocks.remove(found[1])
            target.blocks.append(block)


def write(main: Main) -> list[str]:
    """Записывает изменённые файлы main, удаляет опустевшие."""
    root = main.root
    writes, removes = {}, []
    for rel, f in main.files.items():
        path = root / rel
        if f.empty:
            if path.exists():
                removes.append(path)
            continue
        text = f.text()
        if main.original.get(rel) != text:
            writes[path] = text
    for path, text in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for path in removes:
        path.unlink()
        if path.parent != root and not any(path.parent.iterdir()):
            path.parent.rmdir()
    return [f"записан: {p.relative_to(root)}" for p in writes] + [f"удалён: {p.relative_to(root)}" for p in removes]


# --- ADR ---

def transferred(adr: Adr, main: list[Adr]) -> Adr | None:
    """ADR в main с тем же ID и текстом: ADR фичи уже перенесён."""
    return next((a for a in main if a.slug == adr.slug and a.content == adr.content), None)


def active(main: list[Adr], feature: list[Adr]) -> set[str]:
    """ID действующих ADR после переноса ADR фичи."""
    replaced = {s for a in feature for s in a.replaces}
    return {a.slug for a in main if a.slug not in replaced} | {a.slug for a in feature}


def check_adrs(main: list[Adr], feature: Feature) -> list[str]:
    """ADR фичи: форма и `Заменяет:` на действующие ADR."""
    out = []
    by_slug = {a.slug: a for a in main}
    for adr in feature.adrs:
        where = f"delta/_project/adr/{adr.path.name}"
        if not adr.doc.problems:  # ошибки синтаксиса — в check_form
            # ADR — как он ляжет в main, но с `Заменяет:`. Свойства изменения проверяет check_form
            doc = parse("\n".join(adr.head.with_source(feature.slug, CHANGE_PROPS)))
            out += form.check(where, doc, "adr", main_bind(f"_project/adr/{adr.path.name}"))
        if transferred(adr, main):
            continue
        for slug in adr.replaces:
            if slug not in by_slug:
                out.append(f"{where}: «{REPLACES}: {slug}» — нет действующего ADR с таким `<ID ADR>`{SEE_ADR}")
        if adr.slug in by_slug and adr.slug not in adr.replaces:
            out.append(f"{where}: `<ID ADR>` уже у действующего {by_slug[adr.slug].path.name}."
                       f" Другой `<ID ADR>` или «{REPLACES}: adr:{adr.slug}»{SEE_ADR}")
    return out


def transfer_adrs(root: Path, feature: Feature) -> list[str]:
    """Переносит ADR фичи в main с `Источник:` фичи и удаляет заменённые. ADR остаётся в delta/ фичи."""
    out = []
    folder = root / "_project" / "adr"
    for adr in feature.adrs:
        main, _ = main_adrs(root)
        path = folder / f"{adr.slug}.md"
        if transferred(adr, main) is None:
            folder.mkdir(parents=True, exist_ok=True)
            lines = adr.main_lines(feature.slug)
            path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
            out.append(f"ADR перенесён: {path.name}")
        for old in main:
            if old.slug in adr.replaces and old.path != path and old.path.exists():
                old.path.unlink()
                out.append(f"ADR заменён и удалён: {old.path.name}")
    return out
