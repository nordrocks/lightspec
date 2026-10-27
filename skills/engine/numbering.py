"""Следующий свободный номер фичи или требования домена.

Номера не переиспользуются: учитываются main, spec и delta/ всех фич в new/ и archive/.
"""
from __future__ import annotations

import re
from pathlib import Path

from .ident import NUMBER


def next_feature(specs: Path) -> str:
    numbers = [
        int(m.group(1))
        for folder in ("new", "archive") if (specs / folder).is_dir()
        for path in (specs / folder).iterdir()
        if path.is_dir() and (m := re.match(rf"^({NUMBER})-", path.name))
    ]
    return f"{max(numbers, default=0) + 1:03d}"


def next_requirement(specs: Path, domain: str) -> str:
    prefix = domain.upper()
    pattern = re.compile(r"(?<![A-Z0-9-])" + re.escape(prefix) + rf"-({NUMBER})\b")
    files = [*(specs / "main" / domain).glob("*.md")]
    for folder in ("new", "archive"):
        files += [*specs.glob(f"{folder}/*/spec.md"), *specs.glob(f"{folder}/*/delta/**/*.md")]
    numbers = [int(n) for f in files for n in pattern.findall(f.read_text(encoding="utf-8"))]
    return f"{prefix}-{max(numbers, default=0) + 1:03d}"
