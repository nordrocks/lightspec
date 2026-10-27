"""Синтаксис: токены → дерево. README.md пакета, «Грамматика» и «Ошибки разбора».

Грамматика LL(1): правило выбирается по следующему токену. Разбор — рекурсивный спуск, метод на нетерминал.
После ошибки разбор пропускает токены до следующего заголовка. В выводе — все ошибки файла.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lexer import BLANK, EOF, FENCE_CLOSE, FENCE_OPEN, H1, H2, H3, LINE, PROP, Problem, Token, lex
from .paths import DELTA_FILE, FILE


@dataclass
class Prop:
    name: str
    value: str
    line: int


@dataclass
class BodyLine:
    line: int
    fenced: bool  # строка fenced: FENCE-OPEN, LINE внутри, FENCE-CLOSE


@dataclass
class Part:
    """Шапка (level 1), блок (2) или раздел (3)."""
    level: int
    title: str
    line: int     # строка заголовка
    end: int = 0  # строка после части
    props: list[Prop] = field(default_factory=list)
    body: list[BodyLine] = field(default_factory=list)
    sections: list[Part] = field(default_factory=list)

    def prop(self, name: str) -> str | None:
        """Значение первого свойства с этим именем."""
        return next((p.value for p in self.props if p.name == name), None)


@dataclass
class Document:
    lines: list[str]
    header: Part | None
    blocks: list[Part]
    problems: list[Problem]

    @property
    def parts(self) -> list[Part]:
        return ([self.header] if self.header else []) + self.blocks

    def body_text(self, part: Part) -> list[str]:
        """Строки тела вне fence."""
        return [self.lines[b.line] for b in part.body if not b.fenced]

    def where(self, line: int) -> str:
        """Часть, в которой строка: «шапка», «<блок>» или «<блок>, «<раздел>»»."""
        label = "до шапки"
        for part in self.parts:
            if line >= part.line:
                label = "шапка" if part.level == 1 else part.title
                for s in part.sections:
                    if line >= s.line:
                        label = f"{part.title}, «{s.title}»"
        return label


class _Parser:
    def __init__(self, tokens: list[Token], problems: list[Problem]):
        self.tokens = tokens
        self.i = 0
        self.problems = problems

    @property
    def peek(self) -> Token:
        return self.tokens[self.i]

    def at(self, *kinds: str) -> bool:
        return self.peek.kind in kinds

    def take(self) -> Token:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def fail(self, message: str) -> None:
        """Ошибка на текущем токене: он и токены до следующего заголовка пропускаются."""
        self.problems.append(Problem(self.peek.line, message))
        if not self.at(EOF):
            self.take()
        while not self.at(H1, H2, H3, EOF):
            self.take()

    # file = { BLANK } header { block } EOF
    def file(self) -> tuple[Part | None, list[Part]]:
        if not self.blanks():
            return None, []
        header = None
        if self.at(H1):
            header = self.header()
        else:
            self.fail("нет шапки `#`")
        return header, self.blocks()

    # delta-file = { BLANK } ( header | block ) { block } EOF
    def delta_file(self) -> tuple[Part | None, list[Part]]:
        if not self.blanks():
            return None, []
        header = None
        if self.at(H1):
            header = self.header()
        elif not self.at(H2):
            self.fail("файл начинается не с `#` или `##`")
        return header, self.blocks()

    def blanks(self) -> bool:
        """{ BLANK } в начале файла. False — файл пуст."""
        while self.at(BLANK):
            self.take()
        if self.at(EOF):
            self.problems.append(Problem(self.peek.line, "файл пуст"))
            return False
        return True

    # { block } EOF
    def blocks(self) -> list[Part]:
        blocks = []
        while not self.at(EOF):
            if self.at(H2):
                blocks.append(self.block())
            elif self.at(H1):
                self.fail("`#` — только первым заголовком файла")
            else:
                self.fail("раздел вне блока")
        return blocks

    # header = H1 props [ BLANK body ]
    def header(self) -> Part:
        part = self.heading(1)
        self.props(part)
        self.tail(part)
        part.end = self.peek.line
        return part

    # block = H2 props [ BLANK body ] { section }
    def block(self) -> Part:
        part = self.heading(2)
        self.props(part)
        self.tail(part)
        while self.at(H3):
            part.sections.append(self.section())
        part.end = self.peek.line
        return part

    # section = H3 props [ BLANK body ]
    def section(self) -> Part:
        part = self.heading(3)
        self.props(part)
        self.tail(part)
        part.end = self.peek.line
        return part

    def heading(self, level: int) -> Part:
        token = self.take()
        return Part(level, token.value, token.line)

    # props = { PROP }
    def props(self, part: Part) -> None:
        while self.at(PROP):
            t = self.take()
            part.props.append(Prop(t.value, t.extra, t.line))

    # [ BLANK body ]
    def tail(self, part: Part) -> None:
        if self.at(BLANK):
            self.body(part)
        elif self.at(LINE, FENCE_OPEN):
            self.fail("под заголовком не свойство — отдели текст пустой строкой")

    # body = { BLANK | LINE | PROP | fenced }
    def body(self, part: Part) -> None:
        while self.at(BLANK, LINE, PROP, FENCE_OPEN):
            if self.at(FENCE_OPEN):
                self.fenced(part)
            else:
                part.body.append(BodyLine(self.take().line, False))

    # fenced = FENCE-OPEN { LINE } FENCE-CLOSE
    def fenced(self, part: Part) -> None:
        opening = self.take()
        part.body.append(BodyLine(opening.line, True))
        while self.at(LINE):
            part.body.append(BodyLine(self.take().line, True))
        if self.at(FENCE_CLOSE):
            part.body.append(BodyLine(self.take().line, True))
        else:
            self.problems.append(Problem(opening.line, "fence не закрыт"))


def parse(text: str, start: str = FILE) -> Document:
    """Текст файла → дерево по стартовому символу из «Путей»."""
    lines = text.splitlines()
    tokens, problems = lex(lines)
    parser = _Parser(tokens, problems)
    header, blocks = parser.delta_file() if start == DELTA_FILE else parser.file()
    problems.sort(key=lambda p: p.line)
    return Document(lines, header, blocks, problems)
