"""Corpus parsing and retrieval quality."""

from __future__ import annotations

import pytest


def test_every_chunk_carries_a_citation(corpus):
    for chunk in corpus:
        assert chunk.chunk_id
        assert chunk.citation and chunk.citation != "unknown"
        assert chunk.instrument and chunk.instrument != "unknown"
        assert chunk.text.strip()


def test_chunk_ids_are_unique(corpus):
    ids = [c.chunk_id for c in corpus]
    assert len(ids) == len(set(ids))


def test_corpus_readme_is_not_indexed(corpus):
    """The provenance README has no frontmatter and must not become a chunk."""
    assert all(c.source_file != "README.md" for c in corpus)


def test_all_five_instruments_are_represented(corpus):
    assert len({c.instrument for c in corpus}) == 5


def test_embedding_text_includes_instrument_and_heading(corpus):
    chunk = corpus[0]
    text = chunk.embedding_text()
    assert chunk.instrument in text
    assert chunk.heading in text


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("why was my loan application rejected", "FPC-01"),
        ("I have no credit history, is that held against me", "CIC-04"),
        ("can I withdraw permission to use my personal data", "DPDP-05"),
        ("does the app need access to my contacts and photos", "DL-03"),
    ],
)
def test_retrieval_surfaces_the_governing_provision(vector_store, query, expected_id):
    results = vector_store.search(query, top_k=3)
    assert expected_id in [r.chunk.chunk_id for r in results]


def test_results_are_ordered_by_descending_score(vector_store):
    scores = [r.score for r in vector_store.search("consent for data sharing", top_k=5)]
    assert scores == sorted(scores, reverse=True)


def test_top_k_is_respected(vector_store):
    assert len(vector_store.search("loan rejection", top_k=2)) == 2


def test_citations_expose_what_the_reader_needs(vector_store):
    citation = vector_store.search("reasons for rejection", top_k=1)[0].to_citation()
    assert {"chunk_id", "heading", "instrument", "citation", "text", "score"} <= set(citation)
