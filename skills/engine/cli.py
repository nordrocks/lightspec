"""Команды пакета: разбор аргументов и запуск."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import commands, numbering
from .report import WARN_LIMIT, Report
from .workspace import load_feature


def find_feature(arg: str, specs: Path | None) -> Path:
    """Папка фичи: путь к spec.md, путь к папке, `<ID фичи>` или `<номер>`."""
    path = Path(arg)
    if path.is_file():
        return path.resolve().parent
    if path.is_dir():
        return path.resolve()
    root = specs or Path("specs")
    for folder in ("new", "archive"):
        found = [d for d in sorted((root / folder).glob("*")) if d.is_dir() and (d.name == arg or d.name.startswith(arg + "-"))]
        if found:
            return found[0].resolve()
    sys.exit(f"нет фичи {arg}: ни файла, ни папки, ни фичи в {root}/new и {root}/archive")


def feature_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("feature", help="путь к spec.md или папке фичи, <ID фичи> или <номер>")
    parser.add_argument("--specs", type=Path, help="папка specs/, по умолчанию ./specs — для поиска по ID")
    parser.add_argument("--all", action="store_true", help=f"все предупреждения, а не первые {WARN_LIMIT}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="engine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("next", help="следующий свободный номер")
    p.add_argument("what", choices=["feature", "req"], help="feature — номер фичи, req — ID требования")
    p.add_argument("domain", nargs="?", help="домен — для req")
    p.add_argument("--specs", type=Path, default=Path("specs"), help="папка specs/, по умолчанию ./specs")

    feature_args(sub.add_parser("check-spec", help="условия draft → approved"))
    feature_args(sub.add_parser("check-plan", help="условия approved → planned, ничего не меняет"))
    feature_args(sub.add_parser("sync", help="условия implementing → done и вливание delta в main"))

    sub.add_parser("examples", help="примеры formats/ по своим форматам — для тех, кто меняет фреймворк")

    p = sub.add_parser("graph", help="граф в браузере — для людей: изменения фичи или без фичи весь main")
    p.add_argument("feature", nargs="?", help="путь к spec.md или папке фичи, <ID фичи> или <номер>. Нет — весь main")
    p.add_argument("--specs", type=Path, help="папка specs/, по умолчанию ./specs — для поиска по ID")
    p.add_argument("--port", type=int, default=8765, help="порт, по умолчанию 8765")
    p.add_argument("--open", action="store_true", help="открыть страницу в браузере")
    p.add_argument("--json", action="store_true", help="напечатать граф в JSON и выйти")
    p.add_argument("--background", action="store_true",
                   help="сервер проекта запущен — переключить его на фичу, нет — запустить в фоне. Команда сразу выходит")

    args = parser.parse_args()
    if args.command == "next":
        if not args.specs.is_dir():
            sys.exit(f"нет папки {args.specs}")
        if args.what == "req" and not args.domain:
            sys.exit("для req нужен домен: next req auth")
        print(numbering.next_feature(args.specs) if args.what == "feature"
              else numbering.next_requirement(args.specs, args.domain))
    elif args.command == "examples":
        from . import examples
        examples.main()
    elif args.command == "graph":
        from . import graph
        source = (graph.FeatureGraph(find_feature(args.feature, args.specs)) if args.feature
                  else graph.MainGraph((args.specs or Path("specs")).resolve()))
        graph.main(source, args.port, args.open, args.json, args.background)
    else:
        folder = find_feature(args.feature, args.specs)
        if not (folder / "spec.md").is_file():
            sys.exit(f"нет файла {folder / 'spec.md'}")
        if not (folder.parent.parent / "main").is_dir():
            sys.exit(f"нет папки {folder.parent.parent / 'main'}")
        feature, report = load_feature(folder), Report(args.all)
        if args.command == "check-spec":
            commands.check_spec(feature, report)
        else:
            commands.check_plan(feature, report, sync=args.command == "sync")
