"""Вывод команд: нарушения блокируют переход, предупреждения — нет.

Проверка пройдена — код выхода 0 и последняя строка кончается на `OK`.
"""
from __future__ import annotations

import sys

WARN_LIMIT = 10


class Report:
    def __init__(self, show_all: bool = False):
        self.show_all = show_all

    def items(self, title: str, items: list[str], limit: bool = True) -> None:
        print(title)
        shown = items if self.show_all or not limit else items[:WARN_LIMIT]
        for item in shown:
            print(f"- {item}")
        if len(shown) < len(items):
            print(f"- … ещё {len(items) - len(shown)}, все — с --all")

    def old(self, name: str, warnings: list[str]) -> None:
        """Нарушения, которые уже есть в main без delta."""
        if warnings:
            self.items(f"{name}: уже есть в main без delta — {len(warnings)}. Переход не блокируют,"
                       " исправляются delta этой или отдельной spec", warnings)

    def notice(self, name: str, items: list[str]) -> None:
        """Предупреждения, которые агент решает с пользователем."""
        if items:
            self.items(f"{name}: предупреждения — {len(items)}. Переход не блокируют, реши с пользователем",
                       items, limit=False)

    def changes(self, name: str, changes: list) -> None:
        """Части delta документа — для «Итога» скила."""
        print(f"Части delta/ {name}:")
        if not changes:
            print("- нет")
        for c in changes:
            print(f"- {c.action or ''} {c.file} — {c.name}")

    def result(self, name: str, violations: list[str], warnings: list[str] = ()) -> None:
        """Итог проверки. Нарушения — выход с кодом 1."""
        self.old(name, list(warnings))
        if violations:
            self.items(f"{name}: нарушений — {len(violations)}", violations, limit=False)
            sys.exit(1)
        print(f"{name}: OK")
