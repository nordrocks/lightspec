"""Вход: `python3 <папка скилов>/engine <команда> …` или `python3 -m engine …` из папки скилов."""
import sys
from pathlib import Path

if not __package__:
    # Запуск папкой: в sys.path — сама папка пакета. Её место занимает папка скилов, чтобы импорт шёл как engine.*.
    sys.path[0] = str(Path(__file__).resolve().parent.parent)

from engine.cli import main  # noqa: E402

main()
