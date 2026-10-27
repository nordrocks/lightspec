"""Пути: путь файла от specs/ → сущность (rules.md, «Сущности») и стартовый символ (README.md пакета, «Пути»)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .ident import IDENTS

FILE = "file"
DELTA_FILE = "delta-file"

# Путь от main/ → сущность. Первая подошедшая строка: `<поддомен>` не кончается на `-requirements`.
# Группа g<n> — идентификатор из _GROUPS: в имени группы regex не может быть пробела.
_MAIN = [
    (rf"(?P<g0>{IDENTS['домен']})/(?P<g1>{IDENTS['поддомен']})-requirements\.md", "requirements"),
    (rf"(?P<g0>{IDENTS['домен']})/(?P<g1>{IDENTS['поддомен']})\.md", "domain-docs"),
    (rf"_contracts/(?P<g2>{IDENTS['интерфейс']})\.md", "contracts"),
    (r"_project/architecture\.md", "architecture"),
    (r"_project/conventions\.md", "conventions"),
    (rf"_project/adr/(?P<g3>{IDENTS['ID ADR']})\.md", "adr"),
    (rf"_project/(?P<g4>{IDENTS['тема']})\.md", "project-doc"),
]
_GROUPS = {"g0": "домен", "g1": "поддомен", "g2": "интерфейс", "g3": "ID ADR", "g4": "тема"}
_FEATURE = re.compile(rf"(?:new|archive)/({IDENTS['ID фичи']})/(.+)")


@dataclass(frozen=True)
class Location:
    rel: str                     # путь от specs/
    entity: str
    start: str                   # стартовый символ: file или delta-file
    main_rel: str | None = None  # путь от main/: у файлов main и delta
    feature: str | None = None   # ID фичи: у файлов фичи

    @property
    def bind(self) -> dict[str, str]:
        """Идентификаторы из пути: с ними сверяются заголовки."""
        if self.main_rel is not None:
            return main_bind(self.main_rel)
        return {"ID фичи": self.feature} if self.feature else {}


def main_entity(main_rel: str) -> str | None:
    """Сущность файла по пути от main/."""
    return next((entity for rx, entity in _MAIN if re.fullmatch(rx, main_rel)), None)


def main_bind(main_rel: str) -> dict[str, str]:
    """Идентификаторы пути от main/. `<префикс>` — `<домен>` заглавными."""
    for rx, _ in _MAIN:
        m = re.fullmatch(rx, main_rel)
        if m:
            bind = {_GROUPS[k]: v for k, v in m.groupdict().items()}
            if "домен" in bind:
                bind["префикс"] = bind["домен"].upper()
            return bind
    return {}


def locate(rel: str) -> Location | None:
    """Путь от specs/ → место файла. None — путь не по правилам."""
    if rel.startswith("main/"):
        entity = main_entity(rel[5:])
        return Location(rel, entity, FILE, rel[5:]) if entity else None
    m = _FEATURE.fullmatch(rel)
    if not m:
        return None
    feature, rest = m.groups()
    if rest in ("spec.md", "plan.md"):
        return Location(rel, rest[:-3], FILE, feature=feature)
    if rest.startswith("delta/"):
        entity = main_entity(rest[6:])
        if entity:
            return Location(rel, entity, FILE if entity == "adr" else DELTA_FILE, rest[6:], feature)
    return None
