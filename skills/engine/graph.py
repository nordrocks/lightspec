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
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def context_node(nid: str, mains: list[Main], root: Path) -> dict:
    """Узел, на который ссылаются изменения, но который фича не меняет."""
    if nid.startswith("doc:") and "#" not in nid:
        file = nid[4:] + ".md"
        return make_node(nid, main_entity(file) or "domain-docs", file, None, None, label=file, missing=True)
    if nid.startswith("adr:"):
        adr = next((a for a in main_adrs(root)[0] if a.slug == nid[4:]), None)
        if adr:
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

    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], bool] = {}
    for c in feature.changes:
        nid = node_id(c.entity, c.name, c.file)
        frag, lines, delta = c.frag, c.clean, True
        if c.action == REMOVED and c.name != HEADER:
            found = find_block(before, nid)
            if found:
                frag, lines, delta = found[2], found[3], False
        owner = "spec" if c.entity in ("requirements", "contracts") else "plan"
        nodes[nid] = make_node(nid, c.entity, c.file, c.action, frag, lines, delta,
                               source=c.source, reason=c.prop(REASON), owner=owner)
        for edge in edges_of(nid, c.entity, c.name, frag):
            edges[edge] = c.action == REMOVED

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
        for item in split_list(t.prop("Реализует")):
            edges[(nid, ref_id(item), "implements")] = False
        for ident in prop_idents(t.prop("Документация")):
            file = ident + ".md"
            targets = [i for i, n in nodes.items() if n.get("file") == file and n.get("action")] or ["doc:" + ident]
            for target in targets:
                edges[(nid, target, "documents")] = False

    for src, dst, _ in list(edges):
        for nid in (src, dst):
            if nid not in nodes:
                nodes[nid] = context_node(nid, [after, before], root)

    head = feature.spec.doc.header
    return {
        "mode": "feature",
        "feature": {"slug": feature.slug, "title": head.title if head else None, "status": feature.status,
                    "path": str(feature.spec.path)},
        "nodes": list(nodes.values()),
        "edges": [{"from": s, "to": d, "kind": k, "removed": r} for (s, d, k), r in edges.items()],
    }


def build_main_graph(specs: Path) -> dict:
    """Все блоки main и ADR со связями. Шапки файлов не показываются: связей у них нет."""
    root = specs / "main"
    main = Main(root)
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], bool] = {}
    for rel, f in main.files.items():
        for b in f.blocks:
            nid = node_id(f.entity, b.name, rel)
            nodes[nid] = make_node(nid, f.entity, rel, None, b.frag, b.lines)
            for edge in edges_of(nid, f.entity, b.name, b.frag):
                edges[edge] = False
    for adr in main_adrs(root)[0]:
        rel = f"_project/adr/{adr.path.name}"
        nid = node_id("adr", HEADER, rel)
        nodes[nid] = make_node(nid, "adr", rel, None, adr.head)
    for src, dst, _ in list(edges):
        for nid in (src, dst):
            if nid not in nodes:
                nodes[nid] = context_node(nid, [main], root)
    features, feature_edges = feature_nodes(specs, nodes)
    nodes.update(features)
    edges.update(feature_edges)
    return {
        "mode": "main",
        "feature": {"slug": "main", "title": "main: вся система", "status": None, "path": str(root)},
        "nodes": list(nodes.values()),
        "edges": [{"from": s, "to": d, "kind": k, "removed": r} for (s, d, k), r in edges.items()],
    }


def feature_nodes(specs: Path, blocks: dict[str, dict]) -> tuple[dict[str, dict], dict[tuple[str, str, str], bool]]:
    """Фичи из new/ и archive/ и их связи с блоками main по delta/.

    Закрытая фича: «владелец» — она в `Источник:` блока, её версия сейчас в main. «меняла раньше» — версия уже
    другой фичи, связь пунктиром. Фича в работе: «меняет» или «удалит» блок main при sync.
    Блок, которого в main уже нет, — узел `removed_block` с текстом последней версии из delta. К нему — «удалила»
    от фичи, которая его удалила, и «меняла, позже удалён» от остальных. ADR удаляется заменой: `Заменяет:` у
    нового ADR — «заменила» от закрытой фичи, «заменит» от фичи в работе.
    Узел-заглушка «нет в main» (на блок ссылаются, а его нет) — тоже не блок main: если блок есть в delta
    какой-то фичи, заглушка становится узлом удалённого блока, видимым всегда.
    Все части delta, которых в main нет, — ещё и в `gone` фичи: для панели.
    """
    features = [load_feature(path.parent) for folder in ("new", "archive") for path in sorted((specs / folder).glob("*/spec.md"))]
    removed_by = {node_id(c.entity, c.name, c.file): f.slug for f in features for c in f.changes if c.action == "REMOVED"}
    replaced = {"adr:" + old: (f.slug, a.slug) for f in features for a in f.adrs for old in a.replaces if old != a.slug}
    for target, (slug, _) in replaced.items():
        removed_by.setdefault(target, slug)
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], bool] = {}
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
                    continue  # ещё не в main: добавит при sync
                edges[(nid, target, "removed" if who == feature.slug else "gone")] = True
                if c.action != "REMOVED" or target not in versions:
                    versions[target] = (feature.slug, c)
            elif folder == "new":
                edges[(nid, target, "removes" if c.action == "REMOVED" else "changes")] = c.action == "REMOVED"
            elif source_id(block["props"].get(SOURCE)) == feature.slug:
                edges[(nid, target, "owns")] = False
            else:
                edges[(nid, target, "changed")] = True  # пунктир: в main уже версия другой фичи
        for a in feature.adrs:
            for old in a.replaces:
                target = "adr:" + old
                if old == a.slug:
                    continue
                if folder == "new" and target in blocks and not blocks[target].get("missing"):
                    edges[(nid, target, "will_replace")] = True
                elif folder == "archive":
                    edges[(nid, target, "replaced")] = True
                    versions.setdefault(target, None)
        for base in prop_idents(head.prop("Основа") if head else None):
            edges[(nid, "feature:" + base, "based")] = False
        nodes[nid] = {
            "id": nid, "label": head.title if head else feature.slug, "kind": "feature", "action": None,
            "status": feature.status, "column": "features", "group": folder, "domain": folder,
            "file": f"{folder}/{feature.slug}/spec.md", "props": {p.name: p.value for p in head.props} if head else {},
            "gone": gone, "text": "\n".join(feature.spec.doc.lines).strip(),
        }
    for gid, version in versions.items():
        if version is None:
            continue  # заменённый ADR, которого нет в delta ни одной фичи: остаётся заглушкой
        slug, c = version
        nodes[gid] = make_node(gid, c.entity, c.file, None, c.frag, c.clean, True, removed_block=True, version=slug,
                               by=removed_by.get(gid), replaced_with=replaced.get(gid, (None, None))[1],
                               referenced=bool(blocks.get(gid, {}).get("missing")))
    return nodes, {e: r for e, r in edges.items() if e[1] in blocks or e[1] in nodes}


class FeatureGraph:
    """Граф изменений фичи."""

    def __init__(self, folder: Path):
        self.folder = folder

    def build(self) -> dict:
        return build_graph(self.folder)

    def dirs(self) -> list[Path]:
        folder = locate(self.folder)
        return [folder, folder.parent.parent / "main"]


class MainGraph:
    """Граф всего main."""

    def __init__(self, specs: Path):
        self.specs = specs

    def build(self) -> dict:
        return build_main_graph(self.specs)

    def dirs(self) -> list[Path]:
        return [self.specs / "main"]


def signature(source: FeatureGraph | MainGraph) -> str:
    """Отпечаток файлов графа: меняется при любой правке."""
    h = hashlib.sha1()
    for base in source.dirs():
        for p in sorted(base.rglob("*.md")) if base.is_dir() else []:
            st = p.stat()
            h.update(f"{p}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    h.update(PAGE.read_bytes())
    return h.hexdigest()[:12]


def safe_graph(source: FeatureGraph | MainGraph) -> dict:
    """Граф или ошибка разбора: файл могут сохранить на середине правки."""
    try:
        graph = source.build()
    except Exception as exc:  # noqa: BLE001 — страница показывает ошибку и держит прошлый граф
        graph = {"error": f"{type(exc).__name__}: {exc}"}
    graph["version"] = signature(source)
    graph["page"] = hashlib.sha1(PAGE.read_bytes()).hexdigest()[:12]
    return graph


# --- сервер ---

class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = self.path.split("?")[0]
        source = self.server.source
        if route == "/":
            self.reply(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif route == "/version":
            self.reply(signature(source).encode(), "text/plain; charset=utf-8")
        elif route == "/graph.json":
            self.reply(json.dumps(safe_graph(source), ensure_ascii=False).encode(), "application/json")
        else:
            self.send_error(404)

    def reply(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def main(source: FeatureGraph | MainGraph, port: int, open_page: bool, as_json: bool) -> None:
    main_dir = source.dirs()[-1]
    if not main_dir.is_dir():
        sys.exit(f"нет папки {main_dir}")
    if as_json:
        print(json.dumps(safe_graph(source), ensure_ascii=False, indent=2))
        return
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.source = source
    url = f"http://127.0.0.1:{port}/"
    what = "граф main" if isinstance(source, MainGraph) else "граф изменений"
    print(f"{what}: {url}  (Ctrl+C — остановить)", flush=True)
    if open_page:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
