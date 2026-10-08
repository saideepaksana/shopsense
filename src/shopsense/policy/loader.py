from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Clause:
    id: str
    tags: tuple[str, ...]
    text: str


def load_clauses(path):
    clauses = []
    ident = tags = None
    body = []

    def finish():
        if ident:
            clauses.append(Clause(ident, tuple(tags), " ".join(body)))

    for line in Path(path).read_text().splitlines():
        if line.startswith("## "):
            finish()
            header = line[3:]
            left, right = header.split("|", 1)
            ident = left.strip()
            tags = [x.strip() for x in right.split(",")]
            body = []
        elif ident and line.strip():
            body.append(line.strip())
    finish()
    return clauses
