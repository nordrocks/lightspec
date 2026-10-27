"""Идентификаторы и ссылки: syntax.md, «Идентификаторы», «Виды ссылок» и «Поиск ссылок»."""
from __future__ import annotations

import re
from dataclasses import dataclass

KEY = r"[a-z0-9]+(?:-[a-z0-9]+)*"
NUMBER = r"[0-9]{3,}"
PREFIX = r"[A-Z0-9]+(?:-[A-Z0-9]+)*"

IDENTS = {
    "ID фичи": rf"{NUMBER}-{KEY}",
    "ID требования": rf"{PREFIX}-{NUMBER}",
    "ID элемента": rf"{KEY}\.{KEY}",
    "ID ADR": KEY,
    "ID документа": rf"(?:{KEY}/{KEY}|_project/{KEY})",
    "интерфейс": KEY,
    "домен": KEY,
    "поддомен": KEY,
    "тема": KEY,
    "префикс": PREFIX,
    "ключ": KEY,
    "номер": NUMBER,
}

# Вид ссылки → идентификатор узла.
KINDS = {
    "feature": "ID фичи",
    "req": "ID требования",
    "contract": "ID элемента",
    "adr": "ID ADR",
    "doc": "ID документа",
}


# Составной идентификатор → его части по правилу из «Идентификаторов».
_PARTS = {
    "ID фичи": (rf"({NUMBER})-({KEY})", ("номер", "ключ")),
    "ID требования": (rf"({PREFIX})-({NUMBER})", ("префикс", "номер")),
    "ID элемента": (rf"({KEY})\.({KEY})", ("интерфейс", "ключ")),
}


def is_ident(ident: str, value: str) -> bool:
    return re.fullmatch(IDENTS[ident], value) is not None


def components(ident: str, value: str) -> dict[str, str]:
    """Значение идентификатора и его части: `AUTH-007` → {ID требования: AUTH-007, префикс: AUTH, номер: 007}."""
    out = {ident: value}
    if ident in _PARTS:
        rx, names = _PARTS[ident]
        m = re.fullmatch(rx, value)
        if m:
            out.update(zip(names, m.groups()))
    return out


@dataclass(frozen=True)
class Ref:
    kind: str
    ident: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.ident}"


# Перед видом — не буква, цифра, `_`, `-`, `.`, `/`, `:`. Идентификатор — самый длинный по правилу.
_TEXT_REFS = {
    kind: re.compile(r"(?<![\w:/.-])" + kind + r":(" + IDENTS[ident] + r")")
    for kind, ident in KINDS.items()
}


def find_refs(text: str) -> list[Ref]:
    """Ссылки в строке текста по порядку."""
    found = [(m.start(), Ref(kind, m.group(1))) for kind, rx in _TEXT_REFS.items() for m in rx.finditer(text)]
    return [ref for _, ref in sorted(found, key=lambda x: x[0])]


def split_list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def prop_idents(value: str | None) -> list[str]:
    """Идентификаторы из свойства со ссылками: `req:AUTH-003, req:AUTH-007` → AUTH-003, AUTH-007."""
    out = []
    for item in split_list(value):
        kind, sep, ident = item.partition(":")
        out.append(ident if sep and kind in KINDS else item)
    return out
