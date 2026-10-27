"""Свойства: имена и свойства со ссылками. syntax.md, «Свойства»."""
from __future__ import annotations

from .ident import KINDS, is_ident, split_list

SOURCE = "Источник"
CHANGE = "Изменение"
REASON = "Причина"
CHANGE_PROPS = (CHANGE, SOURCE, REASON)
NONE = "None"
ACTIONS = ("ADDED", "MODIFIED", "REMOVED")
STATUSES = ("draft", "approved", "planned", "implementing", "done")  # rules.md, «Статусы спеки»

# Свойства-перечни и их значения: «Реестр». Значения `Тип:` — из таблицы «Элемент» формата.
ENUMS = {CHANGE: ACTIONS, "Статус": STATUSES}

# Свойства со ссылками и виды ссылок в них: «Реестр».
REF_PROPS = {
    SOURCE: ("feature",), "Основа": ("feature",),
    "Контракты": ("contract",),
    "Вход": ("contract",), "Выход": ("contract",), "Ошибки": ("contract",), "Данные": ("contract",),
    "Заменяет": ("adr",), "Реализует": ("req", "contract"), "Документация": ("doc",),
}

# Все имена «Реестра»: другое имя в «Структуре» формата — ошибка формата.
NAMES = {*REF_PROPS, *ENUMS, REASON, "Проверка", "Тип"}

SEE_SYNTAX = " → syntax.md"
SEE_PROPS = " → syntax.md, «Свойства»"


def value_errors(where: str, key: str, value: str, values: tuple[str, ...] | None = None) -> list[str]:
    """Значение свойства по типу из «Реестра». values — перечень, который задаёт формат."""
    if key in REF_PROPS:
        return ref_errors(where, key, value)
    allowed = values or ENUMS.get(key)
    if allowed and value not in allowed:
        return [f"{where}: «{key}: {value}» — не из {', '.join(allowed)}{SEE_PROPS}"]
    return []


def ref_errors(where: str, key: str, value: str) -> list[str]:
    """Значение свойства со ссылками: только ссылки его видов, идентификаторы по правилу."""
    kinds = REF_PROPS[key]
    out = []
    for item in split_list(value):
        kind, sep, ident = item.partition(":")
        if not sep or kind not in kinds:
            out.append(f"{where}: «{key}: {item}» — нужна ссылка {' или '.join(k + ':' for k in kinds)}{SEE_PROPS}")
        elif not is_ident(KINDS[kind], ident):
            out.append(f"{where}: «{key}: {item}» — идентификатор не по правилу{SEE_SYNTAX}")
    return out
