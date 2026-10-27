"""Примеры из formats/: каждый проходит синтаксис и схему своего формата.

Связи между примерами не проверяются: примеры — иллюстрации, а не одна система.
Для тех, кто меняет фреймворк. Скилы её не запускают.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import form, merge, schema
from .paths import locate
from .report import Report
from .schema import FORMATS
from .syntax import parse
from .workspace import load_feature


def examples(name: str) -> list[str]:
    """Тексты fence `markdown` из блока «Пример» формата: по строкам fenced тела блока."""
    doc = parse((FORMATS / name).read_text(encoding="utf-8"))
    block = next((b for b in doc.blocks if b.title == "Пример"), None)
    out: list[str] = []
    current: list[str] | None = None  # строки примера. None — вне fence `markdown`
    ticks = 0  # бэктики открытого fence, 0 — вне fence
    for b in block.body if block else []:
        line = doc.lines[b.line]
        if not b.fenced:
            continue
        if not ticks:  # FENCE-OPEN
            m = re.fullmatch(r"(`{3,})(.*)", line)
            ticks, current = len(m.group(1)), ([] if m.group(2) == "markdown" else None)
        elif re.fullmatch(r"`{%d,}" % ticks, line):  # FENCE-CLOSE
            if current is not None:
                out.append("\n".join(current))
            ticks, current = 0, None
        elif current is not None:
            current.append(line)
    return out


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def check(rel: str, text: str) -> list[str]:
    """Пример как файл по пути от specs/: синтаксис и схема его сущности."""
    loc = locate(rel)
    return form.check(f"{rel}", parse(text, loc.start), loc.entity, loc.bind)


def main() -> None:
    out = []
    try:
        for entity in sorted(set(schema.FILES)):
            schema.load(entity)
    except schema.FormatError as e:
        Report().result("форматы", [str(e)])
    feature = "new/012-unlock-link"
    out += check(f"{feature}/spec.md", examples("spec.md")[0])
    out += check(f"{feature}/plan.md", examples("plan.md")[0])
    out += check("main/auth/login-requirements.md", examples("requirements.md")[0])
    for text in examples("contracts.md"):
        iface = re.match(r"^# (\S+): контракт", text).group(1)
        out += check(f"main/_contracts/{iface}.md", text)
    out += check("main/auth/login.md", examples("domain-docs.md")[0])
    architecture, conventions = examples("project.md")
    out += check("main/_project/architecture.md", architecture)
    out += check("main/_project/conventions.md", conventions)
    out += check("main/_project/adr/postgres.md", examples("adr.md")[0])
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "specs" / feature
        write(folder, "spec.md", examples("spec.md")[0])
        write(folder, "delta/auth/login-requirements.md", examples("delta.md")[0])
        out += [f"delta.md: {p}" for p in merge.check_form(load_feature(folder))]
    Report().result("примеры formats", out)
