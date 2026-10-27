"""Связи: ссылки ведут на узлы, «Обязательные связи» в rules.md.

Работает на main — исходном или с наложенной delta. Сообщения без номеров строк: по ним сравниваются
нарушения до и после delta.
"""
from __future__ import annotations

from dataclasses import dataclass

from .form import SEE_ADR
from .ident import Ref, is_ident, prop_idents
from .refs import part_text_refs, text_refs
from .syntax import Document, Part
from .workspace import HEADER, Change, Feature, Main, SourceFile

MODEL = "модель"
ELEMENT_REFS = ("Вход", "Выход", "Ошибки", "Данные")  # свойства элемента со ссылками на модели
# Элементы контракта, на которые должен ссылаться сценарий, и элементы, которые должны использоваться.
NEEDS_SCENARIO = {"операция", "событие", "протокол"}
DOCS = ("domain-docs", "architecture", "conventions", "project-doc")  # узлы ссылки doc:
NEEDS_USE = {MODEL}
SEE_LINKS = " → rules.md, «Обязательные связи»"
SEE_OWNERS = " → rules.md, «Владельцы знаний»"


@dataclass
class Scenario:
    name: str
    contracts: list[str]


@dataclass
class Requirement:
    id: str
    file: str
    scenarios: list[Scenario]


@dataclass
class Element:
    name: str
    kind: str
    uses: dict[str, list[str]]  # свойство из ELEMENT_REFS → модели
    refs: list[str]  # элементы из свойств ELEMENT_REFS и ссылок contract: в тексте, кроме себя


@dataclass
class Topic:
    file: str
    name: str
    contracts: list[str]


@dataclass
class State:
    requirements: dict[str, Requirement]
    elements: dict[str, Element]
    topics: list[Topic]
    docs: set[str]  # ID документа: файлы документации main
    text_refs: list[tuple[str, Ref]]  # ссылки в тексте main, кроме ссылок между элементами контракта


def scenarios(part: Part) -> list[Scenario]:
    return [Scenario(s.title.partition(":")[2].strip(), prop_idents(s.prop("Контракты")))
            for s in part.sections if s.title.startswith("Сценарий:")]


def element(doc: Document, name: str, part: Part) -> Element:
    refs = [r for key in ELEMENT_REFS for r in prop_idents(part.prop(key))]
    refs += [r.ident for r in part_text_refs(doc, part) if r.kind == "contract"]
    uses = {key: prop_idents(part.prop(key)) for key in ELEMENT_REFS}
    return Element(name, part.prop("Тип") or "", uses, [r for r in refs if r != name])


def build(main: Main) -> State:
    state = State({}, {}, [], set(), [])
    for rel, f in main.files.items():
        if f.entity in DOCS and not f.empty:
            state.docs.add(rel.removesuffix(".md"))
        doc = f.doc()
        state.text_refs += [(rel, r) for r in text_refs(doc) if not (f.entity == "contracts" and r.kind == "contract")]
        for block, part in zip(f.blocks, doc.blocks):
            if f.entity == "requirements":
                state.requirements[block.name] = Requirement(block.name, rel, scenarios(part))
            elif f.entity == "contracts":
                state.elements[block.name] = element(doc, block.name, part)
            elif f.entity == "domain-docs":
                state.topics.append(Topic(rel, block.name, prop_idents(part.prop("Контракты"))))
    return state


def missing_element(name: str, state: State) -> str | None:
    return None if name in state.elements else f"нет элемента {name}"


def integrity(state: State) -> list[str]:
    """Ссылки между requirements и contracts в main."""
    out = []
    in_scenarios: set[str] = set()
    for req in state.requirements.values():
        for sc in req.scenarios:
            for ref in sc.contracts:
                in_scenarios.add(ref)
                err = missing_element(ref, state)
                if err:
                    out.append(f"{req.id}, сценарий «{sc.name}»: висячая ссылка — {err}")
    used: set[str] = set()
    for e in state.elements.values():
        for ref in e.refs:
            used.add(ref)
            err = missing_element(ref, state)
            if err:
                out.append(f"`{e.name}`: висячая ссылка — {err}")
    for e in state.elements.values():
        for key, names in e.uses.items():
            for name in names:
                other = state.elements.get(name)
                if other and other.kind != MODEL:
                    out.append(f"`{e.name}`: «{key}:» {name} — {other.kind}, а нужна {MODEL} → formats/contracts.md")
        if e.kind in NEEDS_SCENARIO and e.name not in in_scenarios:
            out.append(f"`{e.name}`: ни один сценарий не ссылается на него в «Контракты:»{SEE_LINKS}")
        if e.kind in NEEDS_USE and e.name not in used:
            out.append(f"`{e.name}`: на {e.kind} не ссылается ни один элемент{SEE_LINKS}")
    return out


def check_ref(ref: Ref, state: State, adrs: set[str] | None = None, features: set[str] | None = None) -> str | None:
    """Ссылка ведёт на узел. adrs или features None — эти ссылки не проверяются."""
    if ref.kind == "contract":
        err = missing_element(ref.ident, state)
    elif ref.kind == "req":
        err = None if ref.ident in state.requirements else f"нет требования {ref.ident}"
    elif ref.kind == "adr":
        err = None if adrs is None or ref.ident in adrs else f"нет действующего ADR {ref.ident}{SEE_ADR}"
    elif ref.kind == "doc":
        err = None if ref.ident in state.docs else f"нет документации {ref.ident}.md"
    else:
        err = None if features is None or ref.ident in features else f"нет фичи {ref.ident}"
    return err and f"висячая ссылка — {err}"


def text_problems(state: State, adrs: set[str] | None = None, features: set[str] | None = None) -> list[str]:
    """Ссылки в тексте main, кроме ссылок между элементами контракта."""
    out = []
    for rel, ref in state.text_refs:
        if rel.startswith("_contracts/") and ref.kind != "contract":
            out.append(f"{rel}: {ref} — из контрактов ссылки только внутрь _contracts/{SEE_OWNERS}")
            continue
        err = check_ref(ref, state, adrs, features)
        if err:
            out.append(f"{rel}: {err}")
    return out


def docs(state: State) -> list[str]:
    """Документация на main: `Контракты:` блоков ведут на элементы. Ссылки в тексте — в text_problems."""
    out = []
    for topic in state.topics:
        for ref in topic.contracts:
            err = missing_element(ref, state)
            if err:
                out.append(f"{topic.file}, блок «{topic.name}»: висячая ссылка — {err}")
    return out


def delta_refs(state: State, feature: Feature) -> list[str]:
    """Новый или изменённый элемент, кроме модели, есть в «Контракты:» сценария из delta."""
    changes = [c for c in feature.owned("spec") if c.action != "REMOVED" and c.name != HEADER]
    changed = {c.name for c in changes if c.entity == "contracts"}
    in_delta = {ref for c in changes if c.entity == "requirements" for sc in scenarios(c.part) for ref in sc.contracts}
    out = []
    for name in sorted(changed):
        e = state.elements.get(name)
        if e and e.kind not in NEEDS_USE and name not in in_delta:
            out.append(f"`{name}`: изменён в delta, но нет в «Контракты:» сценариев требований из delta{SEE_LINKS}")
    return out


def docs_delta(before: State, changes: list[Change]) -> tuple[list[str], list[str]]:
    """Документация в delta: блоки с изменённым элементом контракта и поддомены с изменёнными требованиями.

    Возвращает нарушения и предупреждения.
    """
    changed = {c.name for c in changes
               if c.entity == "contracts" and c.name != HEADER and c.action in ("MODIFIED", "REMOVED")}
    touched = {(c.file, c.name) for c in changes if c.entity == "domain-docs" and c.action in ("MODIFIED", "REMOVED")}
    out = [f"{t.file}, блок «{t.name}»: элемент {ref} изменён в delta — нужен MODIFIED или REMOVED блока{SEE_LINKS}"
           for t in before.topics for ref in t.contracts if ref in changed and (t.file, t.name) not in touched]
    files = {c.file for c in changes if c.entity == "domain-docs"}
    warnings = sorted({
        f"{c.file}: требования изменены, а {doc} в delta нет — проверь, не устарела ли документация{SEE_LINKS}"
        for c in changes
        if c.entity == "requirements" and (doc := c.file.removesuffix("-requirements.md") + ".md") not in files
    })
    return out, warnings


def doc_problems(src: SourceFile, state: State, adrs: set[str], features: set[str]) -> list[str]:
    """Ссылки в тексте spec или plan и фичи из «Основа:»."""
    name = src.path.stem
    out = [f"{name}: {err}" for r in text_refs(src.doc) if (err := check_ref(r, state, adrs, features))]
    based = prop_idents(src.doc.header.prop("Основа")) if src.doc.header else []
    return out + [f"{name}: «Основа:» — нет фичи {f}" for f in based if is_ident("ID фичи", f) and f not in features]
