"""Переходы статусов: проверки условий из rules.md, «Условия переходов», и вливание.

Порядок: форма spec, plan и delta → main до и после delta → связи. Форма с нарушениями — связи
не проверяются: delta нельзя наложить на main без ложных нарушений. Нарушения, которые есть в main
и без delta, — предупреждения: переход они не блокируют.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import form, links, merge
from .ident import prop_idents
from .report import Report
from .workspace import HEADER, Feature, Main, feature_names, main_adrs

QUESTIONS = "Открытые вопросы"
SPEC_ENTITIES = {"requirements", "contracts"}
ALL_ENTITIES = {"requirements", "contracts", "domain-docs", "architecture", "conventions", "project-doc"}


def questions(feature: Feature, plan: bool = False) -> list[str]:
    """Пункты списка в блоке «Открытые вопросы» spec или plan."""
    src = feature.plan if plan else feature.spec
    block = next((b for b in src.doc.blocks if b.title == QUESTIONS), None) if src else None
    if block is None:
        return []
    return [f"открытый вопрос {'plan' if plan else 'spec'}: {line[2:].strip()}"
            for line in src.doc.body_text(block) if line.startswith("- ")]


def spec_form(feature: Feature) -> list[str]:
    """Открытые вопросы, форма spec и delta."""
    spec = feature.spec
    return questions(feature) + form.check("spec.md", spec.doc, "spec", spec.loc.bind) + merge.check_form(feature)


def plan_form(feature: Feature) -> list[str]:
    """Форма plan, `Реализует:` и `Документация:` задач против delta, Открытые вопросы plan."""
    if feature.plan is None:
        return [f"нет plan.md{form.SEE_PLAN}"]
    out = form.check("plan.md", feature.plan.doc, "plan", feature.plan.loc.bind)
    changed = {c.name for c in feature.owned("spec") if c.name != HEADER}
    done = {i for t in feature.tasks for i in prop_idents(t.prop("Реализует"))}
    out += [f"plan: часть {n} из delta/ не в «Реализует:» ни одной задачи{form.SEE_PLAN}" for n in sorted(changed - done)]
    out += [f"plan: «Реализует: {n}» — такой части нет в delta/ требований и контрактов{form.SEE_PLAN}"
            for n in sorted(done - changed)]
    docs = {c.file.removesuffix(".md") for c in feature.changes if c.entity in links.DOCS}
    described = {i for t in feature.tasks for i in prop_idents(t.prop("Документация"))}
    out += [f"plan: файл delta/{n}.md не в «Документации:» ни одной задачи{form.SEE_PLAN}" for n in sorted(docs - described)]
    out += [f"plan: «Документация: doc:{n}» — такого файла нет в delta/ документации{form.SEE_PLAN}"
            for n in sorted(described - docs)]
    return out + questions(feature, plan=True)


def split(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """Нарушения после delta: новые и те, что уже были в main."""
    old = set(before)
    return [p for p in after if p not in old], [p for p in after if p in old]


def check_spec(feature: Feature, report: Report) -> None:
    """draft → approved."""
    problems = spec_form(feature)
    if feature.status == "done":
        problems.insert(0, "spec в done не меняется → новая spec со ссылкой на эту")
    if problems:
        report.result("форма spec (целостность не проверялась)", problems)
    root = feature.specs / "main"
    features = feature_names(feature.specs)
    adrs, _ = main_adrs(root)
    slugs = merge.active(adrs, feature.adrs)

    before_main = Main(root)
    before_state = links.build(before_main)
    before = before_main.problems(SPEC_ENTITIES) + links.integrity(before_state)
    before += links.text_problems(before_state, {a.slug for a in adrs}, features)
    after_main = Main(root)
    merge.apply(after_main, feature.owned("spec"), feature.slug)
    after = links.build(after_main)
    current = after_main.problems(SPEC_ENTITIES) + links.integrity(after) + links.text_problems(after, slugs, features)
    new, old = split(before, current)
    problems = new + links.delta_refs(after, feature) + links.doc_problems(feature.spec, after, slugs, features)
    report.changes("spec", feature.owned("spec"))
    report.result("spec", problems, old)


def sync_status(feature: Feature) -> list[str]:
    """Статус и папка фичи перед вливанием, отметки задач."""
    out = []
    if feature.folder.parent.name != "new":
        out.append("папка фичи не в specs/new/")
    elif (feature.specs / "archive" / feature.slug).exists():
        out.append(f"archive/{feature.slug} уже есть")
    # done в new/ — вливание прервалось после «Статус: done», до переноса папки
    if feature.status != "implementing" and not (feature.status == "done" and feature.folder.parent.name == "new"):
        out.append(f"spec в {feature.status}: вливать можно только из implementing")
    for task in feature.tasks:
        m = form.TASK.match(task.title)
        if m and m.group(1) != "x":
            out.append(f"задача {m.group(2)} не отмечена → sdd-apply")
    return out


def check_plan(feature: Feature, report: Report, sync: bool = False) -> None:
    """approved → planned: только проверки. sync — implementing → done: проверки, затем вливание."""
    title = "вливание отменено, ничего не менялось" if sync else "проверка перед вливанием"
    if sync:
        problems = sync_status(feature)
    elif feature.status not in ("approved", "planned", "implementing"):
        problems = [f"spec в {feature.status}: проверка нужна в approved, planned или implementing"]
    else:
        problems = []
    root = feature.specs / "main"
    before_main = Main(root)
    adrs, bad_names = main_adrs(root)
    problems += spec_form(feature) + plan_form(feature)
    problems += merge.conflicts(before_main, feature.blocks, feature.slug) + bad_names
    problems += merge.check_adrs(adrs, feature)
    if problems:
        report.result(title, problems)

    features = feature_names(feature.specs)
    old_slugs = {a.slug for a in adrs}
    slugs = merge.active(adrs, feature.adrs)
    before_state = links.build(before_main)
    baseline = before_main.problems(ALL_ENTITIES) + links.integrity(before_state)
    baseline += links.docs(before_state) + links.text_problems(before_state, old_slugs, features)
    after_main = Main(root)
    merge.apply(after_main, feature.blocks, feature.slug)
    after = links.build(after_main)
    current = after_main.problems(ALL_ENTITIES) + links.integrity(after)
    current += links.docs(after) + links.text_problems(after, slugs, features)
    new, old = split(baseline, current)
    docs, docs_warnings = links.docs_delta(before_state, feature.blocks)
    problems = new + links.delta_refs(after, feature) + docs
    for src in (feature.spec, feature.plan):
        problems += links.doc_problems(src, after, slugs, features)
    report.notice("документация", docs_warnings)
    if not sync:
        report.changes("plan", feature.owned("plan"))
        report.result(title, problems, old)
        return
    if problems:
        report.result(title, problems, old)

    report.old("вливание", old)
    log = merge.write(after_main) + merge.transfer_adrs(root, feature)
    set_status(feature.spec.path, "done")
    archive = feature.specs / "archive" / feature.slug
    archive.parent.mkdir(exist_ok=True)
    feature.folder.rename(archive)
    log += ["Статус: done", f"фича перенесена: archive/{feature.slug}"]
    for line in log:
        print(line)
    print("вливание: OK")


def set_status(path: Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"(?m)^Статус: .*$", f"Статус: {status}", text, count=1), encoding="utf-8")
