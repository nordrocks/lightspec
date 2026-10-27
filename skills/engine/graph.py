"""Граф в браузере с живым обновлением: изменения фичи или весь main. Устройство графа — GRAPH.md.

Фича: шаг 1 — домены и блоки, которые она добавляет, меняет и удаляет. Шаг 2 — связи изменений с задачами
plan, элементами контрактов, требованиями и ADR.
Весь main: шаг 1 — домены и их блоки, шаг 2 — фичи из new/ и archive/ и связи всех блоков.
Фича связана с блоками main по своей delta/: «владелец» — её версия в main, «меняла раньше» — уже нет.
Страница перечитывает файлы, когда они меняются. Команда ничего не пишет.
Для людей. Скилы её не запускают.
"""
from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from pathlib import Path

from . import form, links, merge
from .ident import is_ident, prop_idents, split_list
from .paths import main_entity
from .props import CHANGE_PROPS, REASON, SOURCE
from .refs import part_text_refs
from .workspace import HEADER, Fragment, Main, load_feature, main_adrs, source_id

PAGE = Path(__file__).with_name("graph.html")
REMOVED = "REMOVED"
COLUMNS = {"requirements": "req", "contracts": "contracts", "domain-docs": "docs",
           "architecture": "docs", "conventions": "docs", "project-doc": "docs", "adr": "docs"}
PROJECT = "_project"


def group_of(kind: str, file: str) -> str:
    """Группа в столбце: интерфейс контрактов, домен требований, поддомен `<домен>/<поддомен>` или _project."""
    if kind == "contracts":
        return Path(file).stem
    if kind == "requirements":
        return file.split("/")[0]
    if kind == "domain-docs":
        return file.removesuffix(".md")
    return PROJECT


# --- узлы ---

def domain_of(kind: str, file: str) -> str:
    """Домен для шага 1: папка домена, интерфейс контрактов или _project."""
    return "_contracts/" + Path(file).stem if kind == "contracts" else file.split("/")[0]


def node_id(kind: str, name: str, file: str) -> str:
    """id узла — в записи ссылки, поэтому ссылки из свойств совпадают с id без перевода."""
    if kind == "adr":
        return "adr:" + Path(file).stem
    if name == HEADER:
        return "head:" + file
    return {"requirements": "req:", "contracts": "contract:"}.get(kind, "doc:" + file + "#") + name


def ref_id(item: str) -> str:
    """Ссылка из свойства в id узла. Ссылка без вида — по виду идентификатора."""
    if ":" in item.split(".")[0]:
        return item
    return ("req:" if is_ident("ID требования", item) else "contract:") + item


def make_node(nid: str, kind: str, file: str, action: str | None, frag: Fragment | None,
              lines: list[str] | None = None, delta: bool = False, **extra) -> dict:
    """Узел графа. lines — текст части, по умолчанию строки фрагмента. delta — без свойств изменения."""
    lines = lines if lines is not None else (frag.lines if frag else [])
    hidden = CHANGE_PROPS if delta else ()
    props = {p.name: p.value for p in frag.part.props if p.name not in hidden} if frag else {}
    if nid.startswith("head:"):
        label = f"шапка {Path(file).name}"
    else:
        label = frag.part.title if frag else nid
    return {
        "id": nid, "label": label, "kind": kind, "action": action, "file": file,
        "domain": domain_of(kind, file), "column": COLUMNS.get(kind, "docs"),
        "group": group_of(kind, file), "type": props.get("Тип"), "props": props,
        "text": "\n".join(lines).strip(), **extra,
    }


def edges_of(nid: str, kind: str, name: str, frag: Fragment | None) -> list[tuple[str, str, str]]:
    """Связи из части: (от, к, вид связи)."""
    if frag is None or name == HEADER and kind != "adr":
        return []
    part = frag.part
    if kind == "requirements":
        return [(nid, "contract:" + c, "contract") for sc in links.scenarios(part) for c in sc.contracts]
    if kind == "contracts":
        return [(nid, "contract:" + r, "uses") for r in links.element(frag.doc, name, part).refs]
    if kind == "adr":
        return [(nid, ref_id(r), "replaces") for r in split_list(part.prop("Заменяет"))]
    out = [(nid, ref_id(r), "explains") for r in split_list(part.prop("Контракты"))]
    return out + [(nid, f"adr:{r.ident}", "adr") for r in part_text_refs(frag.doc, part) if r.kind == "adr"]


def find_block(main: Main, nid: str) -> tuple[str, str, Fragment, list[str]] | None:
    """Блок main по id: (сущность, файл, фрагмент, строки в main)."""
    scheme, _, name = nid.partition(":")
    anchor = {"req": "requirements", "contract": "contracts"}.get(scheme)
    for f in main.files.values():
        if f.entity == anchor and (block := f.find(name)):
            return anchor, f.rel, block.frag, block.lines
    return None


def context_node(nid: str, mains: list[Main], adrs: dict) -> dict:
    """Узел, на который ссылаются изменения, но который фича не меняет. adrs — действующие ADR по id узла."""
    if nid.startswith("doc:") and "#" not in nid:
        file = nid[4:] + ".md"
        return make_node(nid, main_entity(file) or "domain-docs", file, None, None, label=file, missing=True)
    if nid in adrs:
        adr = adrs[nid]
        return make_node(nid, "adr", f"_project/adr/{adr.path.name}", None, adr.head)
    for main in mains:
        found = find_block(main, nid)
        if found:
            return make_node(nid, found[0], found[1], None, found[2], found[3])
    kind = {"req": "requirements", "contract": "contracts", "adr": "adr"}.get(nid.partition(":")[0], "domain-docs")
    if kind == "adr":
        file = "_project/adr/?.md"
    elif kind == "contracts":
        file = "_contracts/" + nid[9:].split(".")[0] + ".md"
    else:
        file = "?/?"
    return make_node(nid, kind, file, None, None, label=nid.partition(":")[2], missing=True)


# --- граф ---

def locate(folder: Path) -> Path:
    """Папка фичи. После sync фича уже в archive/."""
    if folder.is_dir():
        return folder
    moved = folder.parent.parent / "archive" / folder.name
    return moved if moved.is_dir() else folder


def build_graph(folder: Path) -> dict:
    folder = locate(folder)
    if not (folder / "spec.md").is_file():
        return {"error": f"нет файла {folder / 'spec.md'}"}
    feature = load_feature(folder)
    root = feature.specs / "main"
    before = Main(root)
    after = Main(root)
    merge.apply(after, feature.blocks, feature.slug)
    adrs = active_adrs(root)

    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()
    loaded: list = []

    def history_of() -> list:
        """Все фичи — один раз и только если понадобились."""
        if not loaded:
            loaded.extend(all_features(feature.specs))
        return loaded

    for c in feature.changes:
        nid = node_id(c.entity, c.name, c.file)
        # Текст — всегда дельта. Связи REMOVED-части — от блока в main: в delta у неё только заголовок.
        linked = c.frag
        if c.action == REMOVED and c.name != HEADER:
            found = find_block(before, nid)
            linked = found[2] if found else c.frag
        owner = "spec" if c.entity in ("requirements", "contracts") else "plan"
        nodes[nid] = make_node(nid, c.entity, c.file, c.action, c.frag, c.clean, True,
                               source=c.source, reason=c.prop(REASON), owner=owner)
        if c.action == REMOVED and c.entity == "contracts":
            # В delta у REMOVED нет `Тип:` — берём из блока в main или из последней версии в delta других фич.
            nodes[nid]["type"] = linked.prop("Тип") or removed_type(feature.specs, nid)
        if c.action in ("MODIFIED", REMOVED):
            nodes[nid]["old"] = replaced_text(c, nid, before, history_of)
        edges.update(edges_of(nid, c.entity, c.name, linked))

    if folder.parent.name == "archive":
        mark_later(nodes, feature, before, adrs)

    doc = feature.plan.doc if feature.plan else None
    for t in feature.tasks:
        m = form.TASK.match(t.title)
        nid = f"task:{int(m.group(2)) if m else t.title}"
        props = {p.name: p.value for p in t.props}
        body = [doc.lines[b.line] for b in t.body]
        nodes[nid] = {
            "id": nid, "label": t.title.partition("Задача ")[2] or t.title, "kind": "task", "action": None,
            "done": bool(m) and m.group(1) == "x", "column": "plan", "group": "Задачи", "domain": "plan",
            "file": "plan.md", "props": props,
            "files": [line[2:].strip() for line in doc.body_text(t) if line.startswith("- ")],
            "text": "\n".join([f"### {t.title}"] + [f"{k}: {v}" for k, v in props.items()] + body).strip(),
        }
        edges.update((nid, ref_id(item), "implements") for item in split_list(t.prop("Реализует")))
        for ident in prop_idents(t.prop("Документация")):
            file = ident + ".md"
            targets = [i for i, n in nodes.items() if n.get("file") == file and n.get("action")] or ["doc:" + ident]
            edges.update((nid, target, "documents") for target in targets)

    for nid in {end for edge in edges for end in edge[:2]} - nodes.keys():
        nodes[nid] = context_node(nid, [after, before], adrs)

    head = feature.spec.doc.header
    spec_id = "spec:" + feature.slug
    nodes = {spec_id: {
        "id": spec_id, "label": head.title if head else feature.slug, "kind": "spec", "action": None,
        "status": feature.status, "column": "plan", "group": "spec", "file": "spec.md",
        "text": "\n".join(feature.spec.doc.lines).strip(),
        "plan": "\n".join(feature.plan.doc.lines).strip() if feature.plan else None,
    }, **nodes}
    return graph_json("feature", {"slug": feature.slug, "title": head.title if head else None,
                                  "status": feature.status, "path": str(feature.spec.path)}, nodes, edges)


def graph_json(mode: str, feature: dict, nodes: dict[str, dict], edges: set[tuple[str, str, str]]) -> dict:
    return {"mode": mode, "feature": feature, "nodes": list(nodes.values()),
            "edges": [{"from": s, "to": d, "kind": k} for s, d, k in sorted(edges)]}


def active_adrs(root: Path) -> dict:
    """Действующие ADR main по id узла: `adr:<ID ADR>`."""
    return {"adr:" + a.slug: a for a in main_adrs(root)[0]}


def build_main_graph(specs: Path) -> dict:
    """Все блоки main и ADR со связями. Шапки файлов не показываются: связей у них нет."""
    root = specs / "main"
    main = Main(root)
    adrs = active_adrs(root)
    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()
    for rel, f in main.files.items():
        for b in f.blocks:
            nid = node_id(f.entity, b.name, rel)
            nodes[nid] = make_node(nid, f.entity, rel, None, b.frag, b.lines)
            edges.update(edges_of(nid, f.entity, b.name, b.frag))
    for nid, adr in adrs.items():
        nodes[nid] = make_node(nid, "adr", f"_project/adr/{adr.path.name}", None, adr.head)
    for nid in {end for edge in edges for end in edge[:2]} - nodes.keys():
        nodes[nid] = context_node(nid, [main], adrs)
    features, feature_edges = feature_nodes(all_features(specs), nodes)
    nodes.update(features)
    return graph_json("main", {"slug": "main", "title": "main: вся система", "status": None, "path": str(root)},
                      nodes, edges | feature_edges)


def mark_later(nodes: dict[str, dict], feature, current: Main, adrs: dict) -> None:
    """Закрытая фича: её ADDED и MODIFIED части, которых в main уже нет или там версия другой фичи.

    `later_removed` — кто удалил или заменил, `later_changed` — чья версия сейчас в main.
    """
    removed_by, replaced = history(all_features(feature.specs))
    active = {nid: source_id(a.head.prop(SOURCE)) for nid, a in adrs.items()}
    for c in feature.changes:
        if c.action == REMOVED or (c.name == HEADER and c.entity != "adr"):
            continue
        nid = node_id(c.entity, c.name, c.file)
        if c.entity == "adr":
            owner, present = active.get(nid), nid in active
        else:
            found = current.locate(c.entity, c.name, c.file)
            owner, present = (found[1].source if found else None), bool(found)
        if not present:
            nodes[nid]["later_removed"] = removed_by.get(nid) or "?"
            nodes[nid]["replaced_with"] = replaced.get(nid, (None, None))[1]
        elif owner and owner != feature.slug:
            nodes[nid]["later_changed"] = owner


def replaced_text(c, nid: str, current: Main, history) -> str | None:
    """Версия, которую часть заменяет или удаляет: её указывает `Источник:` части delta.

    Блок в main ещё с этим `Источником:` — текст из main. Иначе — часть delta той фичи. Не нашлось — None.
    """
    if c.name == HEADER:
        f = current.files.get(c.file)
        if f and f.header_source == c.source:
            return "\n".join(f.header).strip()
    else:
        found = current.locate(c.entity, c.name, c.file)
        if found and found[1].source == c.source:
            return "\n".join(found[1].lines).strip()
    owner = next((f for f in history() if f.slug == c.source), None)
    for old in owner.changes if owner else []:
        if old.action != REMOVED and old.entity == c.entity and old.name == c.name:
            return "\n".join(old.main_lines(owner.slug)).strip()
    return None


def removed_type(specs: Path, nid: str) -> str | None:
    """`Тип:` удалённого элемента контракта: из последней части delta с ним, кроме REMOVED."""
    found = None
    for f in all_features(specs):
        for c in f.changes:
            if c.action != REMOVED and c.entity == "contracts" and node_id(c.entity, c.name, c.file) == nid:
                found = c.prop("Тип") or found
    return found


def all_features(specs: Path) -> list:
    return [load_feature(p.parent) for folder in ("new", "archive") for p in sorted((specs / folder).glob("*/spec.md"))]


def history(features: list) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """Кто удалил блок (id узла → фича) и кто заменил ADR (adr:<старый> → (фича, новый ADR))."""
    removed_by = {node_id(c.entity, c.name, c.file): f.slug for f in features for c in f.changes if c.action == "REMOVED"}
    replaced = {"adr:" + old: (f.slug, a.slug) for f in features for a in f.adrs for old in a.replaces if old != a.slug}
    for target, (slug, _) in replaced.items():
        removed_by.setdefault(target, slug)
    return removed_by, replaced


def feature_nodes(features: list, blocks: dict[str, dict]) -> tuple[dict[str, dict], set[tuple[str, str, str]]]:
    """Фичи из new/ и archive/ и их связи с блоками main по delta/.

    Закрытая фича: «владелец» — она в `Источник:` блока, её версия сейчас в main. «меняла раньше» — версия уже
    другой фичи, связь пунктиром. Фича в работе: «меняет» или «удалит» блок main при sync, «добавит» — узел
    `pending` для её ADDED-части: его в main ещё нет.
    Блок, которого в main уже нет, — узел `removed_block` с текстом последней версии из delta. К нему — «удалила»
    от фичи, которая его удалила, и «меняла, позже удалён» от остальных. ADR удаляется заменой: `Заменяет:` у
    нового ADR — «заменила» от закрытой фичи, «заменит» от фичи в работе.
    Узел-заглушка «нет в main» (на блок ссылаются, а его нет) — тоже не блок main: если блок есть в delta
    какой-то фичи, заглушка становится узлом удалённого блока, видимым всегда.
    Все части delta, которых в main нет, — ещё и в `gone` фичи: для панели спеки в режиме фичи.
    Текста spec и plan у узла фичи нет: нажатие на фичу открывает её режим, там они приходят со спекой.
    """
    removed_by, replaced = history(features)
    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()
    versions: dict[str, tuple[str, object]] = {}  # удалённый блок → (фича, часть delta) с последним текстом
    for feature in features:
        head = feature.spec.doc.header
        folder = feature.folder.parent.name
        nid = "feature:" + feature.slug
        gone = []
        for c in feature.changes:
            if c.name == HEADER and c.entity != "adr":
                continue
            target = node_id(c.entity, c.name, c.file)
            block = blocks.get(target)
            if block is None or block.get("missing"):
                who = removed_by.get(target)
                gone.append({"name": c.part.title if c.name == HEADER else c.name, "file": c.file, "action": c.action, "open": folder == "new",
                             "by": None if who == feature.slug else who, "with": replaced.get(target, (None, None))[1]})
                if folder == "new" and c.action == "ADDED":
                    pid = "new:" + target  # ещё не в main: добавит при sync
                    edges.add((nid, pid, "adds"))
                    nodes[pid] = make_node(pid, c.entity, c.file, None, c.frag, c.clean, True, pending=True,
                                           by=feature.slug)
                    continue
                edges.add((nid, target, "removed" if who == feature.slug else "gone"))
                if c.action != "REMOVED" or target not in versions:
                    versions[target] = (feature.slug, c)
            elif folder == "new":
                edges.add((nid, target, "removes" if c.action == "REMOVED" else "changes"))
            elif source_id(block["props"].get(SOURCE)) == feature.slug:
                edges.add((nid, target, "owns"))
            else:
                edges.add((nid, target, "changed"))  # в main уже версия другой фичи
        for a in feature.adrs:
            for old in a.replaces:
                target = "adr:" + old
                if old == a.slug:
                    continue
                if folder == "new" and target in blocks and not blocks[target].get("missing"):
                    edges.add((nid, target, "will_replace"))
                elif folder == "archive":
                    edges.add((nid, target, "replaced"))
                    versions.setdefault(target, None)
        edges.update((nid, "feature:" + base, "based") for base in prop_idents(head.prop("Основа") if head else None))
        nodes[nid] = {
            "id": nid, "label": head.title if head else feature.slug, "kind": "feature", "action": None,
            "status": feature.status, "column": "features", "group": folder,
            "file": f"{folder}/{feature.slug}/spec.md", "gone": gone,
        }
    for gid, version in versions.items():
        if version is None:
            continue  # заменённый ADR, которого нет в delta ни одной фичи: остаётся заглушкой
        slug, c = version
        nodes[gid] = make_node(gid, c.entity, c.file, None, c.frag, c.clean, True, removed_block=True, version=slug,
                               by=removed_by.get(gid), replaced_with=replaced.get(gid, (None, None))[1],
                               referenced=bool(blocks.get(gid, {}).get("missing")))
    return nodes, {e for e in edges if e[1] in blocks or e[1] in nodes}


class FeatureGraph:
    """Граф изменений фичи."""

    def __init__(self, folder: Path):
        self.folder = folder

    def build(self) -> dict:
        return build_graph(self.folder)

    @property
    def specs(self) -> Path:
        return locate(self.folder).parent.parent


class MainGraph:
    """Граф всего main."""

    def __init__(self, specs: Path):
        self.specs = specs

    def build(self) -> dict:
        return build_main_graph(self.specs)


def page_hash() -> str:
    return hashlib.sha1(PAGE.read_bytes()).hexdigest()[:12]


def signature(source: FeatureGraph | MainGraph) -> str:
    """Отпечаток specs/ и страницы: меняется при любой правке. История фич зависит от всех фич, поэтому — весь specs/."""
    h = hashlib.sha1(page_hash().encode())
    for p in sorted(source.specs.rglob("*.md")):
        st = p.stat()
        h.update(f"{p}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    return h.hexdigest()[:12]


def safe_graph(source: FeatureGraph | MainGraph) -> dict:
    """Граф или ошибка разбора: файл могут сохранить на середине правки."""
    try:
        graph = source.build()
    except Exception as exc:  # noqa: BLE001 — страница показывает ошибку и держит прошлый граф
        graph = {"error": f"{type(exc).__name__}: {exc}"}
    graph["version"] = signature(source)
    graph["page"] = page_hash()
    return graph


# --- сервер ---

def focused(source: FeatureGraph | MainGraph, query: str) -> FeatureGraph | MainGraph:
    """`?feature=<ID фичи>` в режиме main — граф изменений этой фичи: её delta, plan и связанные блоки."""
    slug = parse_qs(query).get("feature", [""])[0]
    if not slug or not isinstance(source, MainGraph):
        return source
    for folder in ("new", "archive"):
        path = source.specs / folder / slug
        if (path / "spec.md").is_file():
            return FeatureGraph(path)
    return source


PORTS = range(8765, 8785)  # порты серверов графа: у каждого проекта свой


class Handler(BaseHTTPRequestHandler):
    """Страница, граф и активная фича.

    `/ping` — чей это сервер: папка specs/, активная фича, сколько секунд страница не спрашивала сервер.
    `/activate?feature=<ID фичи>` — сделать фичу активной. Без фичи — общий режим.
    `/state` — отпечаток графа и активная фича со счётчиком переключений: по нему страница переходит на фичу.
    """

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        server = self.server
        source = focused(server.source, query)
        if route == "/":
            self.reply(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif route == "/ping":
            self.reply_json({"specs": str(server.source.specs), "active": server.active,
                             "idle": time.time() - server.seen})
        elif route == "/activate":
            server.active = parse_qs(query).get("feature", [None])[0]
            server.switches += 1
            self.reply_json({"active": server.active})
        elif route == "/version":  # старые открытые страницы: по нему они перезагружаются в новую версию
            self.reply(signature(source).encode(), "text/plain; charset=utf-8")
        elif route == "/state":
            server.seen = time.time()
            self.reply_json({"version": signature(source), "active": server.active, "switches": server.switches})
        elif route == "/graph.json":
            self.reply(json.dumps(safe_graph(source), ensure_ascii=False).encode(), "application/json")
        else:
            self.send_error(404)

    def reply_json(self, data: dict) -> None:
        self.reply(json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def reply(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def ask(port: int, path: str) -> dict | None:
    """Запрос к серверу графа на порту. None — там нет сервера графа."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=0.5) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


def running(specs: Path) -> int | None:
    """Порт уже запущенного сервера графа этого проекта."""
    for port in PORTS:
        info = ask(port, "/ping")
        if info and Path(info["specs"]) == specs:
            return port
    return None


def free_port() -> int:
    """Первый свободный порт из PORTS."""
    for port in PORTS:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit(f"нет свободного порта в {PORTS.start}–{PORTS.stop - 1}")


def page_url(port: int, slug: str | None) -> str:
    return f"http://127.0.0.1:{port}/" + (f"?feature={slug}" if slug else "")


def background(source: FeatureGraph | MainGraph, open_page: bool) -> None:
    """Сервер этого проекта уже запущен — переключить его на фичу. Нет — запустить отдельным процессом.

    Страница, которую давно никто не смотрит, открывается в браузере заново.
    """
    specs = source.specs.resolve()
    slug = locate(source.folder).name if isinstance(source, FeatureGraph) else None
    port = running(specs)
    if port:
        ask(port, "/activate" + (f"?feature={slug}" if slug else ""))
        idle = (ask(port, "/ping") or {}).get("idle", 0)
        print(f"граф уже запущен: {page_url(port, slug)} — {'фича ' + slug if slug else 'общий режим'}")
        if open_page or idle > 5:
            webbrowser.open(page_url(port, slug))
        return
    port = free_port()
    log = Path(tempfile.gettempdir()) / f"sdd-graph-{port}.log"
    cmd = [sys.executable, str(Path(__file__).resolve().parent), "graph", *([slug] if slug else []),
           "--specs", str(specs), "--port", str(port)]
    with open(log, "w") as out:
        subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(30):
        if ask(port, "/ping"):
            break
        time.sleep(0.1)
    else:
        sys.exit(f"сервер графа не запустился, лог: {log}")
    print(f"граф запущен: {page_url(port, slug)}")
    webbrowser.open(page_url(port, slug))


def main(source: FeatureGraph | MainGraph, port: int, open_page: bool, as_json: bool, detach: bool = False) -> None:
    """Граф фичи — частный случай общего: сервер общего режима, страница сразу на фиче.

    detach — не держать сервер в этом процессе: переключить запущенный или запустить фоновый.
    """
    main_dir = source.specs / "main"
    if not main_dir.is_dir():
        sys.exit(f"нет папки {main_dir}")
    if as_json:
        print(json.dumps(safe_graph(source), ensure_ascii=False, indent=2))
        return
    if detach:
        background(source, open_page)
        return
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    slug = locate(source.folder).name if isinstance(source, FeatureGraph) else None
    server.source = MainGraph(source.specs.resolve())
    server.active, server.switches, server.seen = slug, 0, time.time()
    url = page_url(port, slug)
    print(f"граф: {url}  (Ctrl+C — остановить)", flush=True)
    if open_page:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
