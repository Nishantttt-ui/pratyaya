"""Parses the regulatory corpus into retrievable chunks.

Chunking strategy
-----------------
Each numbered provision (a ``##`` heading) becomes exactly one chunk. This is a
deliberate choice over fixed-size or sliding-window chunking: a regulatory
provision is already the unit a lawyer or auditor cites, so splitting on it
means a retrieved chunk maps one-to-one onto a citation the reader can verify.
Fixed-size windows would cut provisions in half and produce citations that
point at fragments.

Every chunk carries its instrument, citation string and stable provision id
(for example ``FPC-01``), so a generated explanation can name its source
precisely rather than gesturing at a document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"^##\s+(\S+)\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class PolicyChunk:
    """One regulatory provision, ready to embed and cite."""

    chunk_id: str
    heading: str
    text: str
    instrument: str
    citation: str
    authority: str
    source_file: str

    def embedding_text(self) -> str:
        """The text actually embedded.

        The instrument name and heading are prepended to the body so that a
        query like "reasons for rejection" can match on the heading even when
        the body phrases it differently.
        """
        return f"{self.instrument} — {self.heading}\n\n{self.text}"

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "heading": self.heading,
            "text": self.text,
            "instrument": self.instrument,
            "citation": self.citation,
            "authority": self.authority,
            "source_file": self.source_file,
        }


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, raw[match.end():]


def parse_file(path: Path) -> list[PolicyChunk]:
    """Parse one policy markdown file into its provisions."""
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    if not meta.get("instrument"):
        return []  # the corpus README carries no frontmatter and is not indexed

    matches = list(_HEADING.finditer(body))
    chunks: list[PolicyChunk] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        if not text:
            continue
        chunks.append(
            PolicyChunk(
                chunk_id=match.group(1).strip(),
                heading=match.group(2).strip(),
                text=text,
                instrument=meta.get("instrument", "unknown"),
                citation=meta.get("citation", meta.get("instrument", "unknown")),
                authority=meta.get("authority", "unknown"),
                source_file=path.name,
            )
        )
    return chunks


def load_corpus(directory: str | Path = "data/policy") -> list[PolicyChunk]:
    """Load every provision in the corpus, sorted by provision id."""
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"Policy corpus not found at {root.resolve()}")
    chunks: list[PolicyChunk] = []
    for path in sorted(root.glob("*.md")):
        chunks.extend(parse_file(path))
    if not chunks:
        raise ValueError(f"No provisions parsed from {root.resolve()}")
    return sorted(chunks, key=lambda c: c.chunk_id)
