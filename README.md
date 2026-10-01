# Agentic Job Analytics

A small job-search analytics agent combining structured SQL retrieval with semantic retrieval over a derived vector index.

The repository is designed to stay simple locally while preserving production-relevant boundaries:

```text
SQLite
    canonical data
       │
       ├──────────────► structured SQL retrieval
       │
       └──► indexing pipeline ──► vector index ──► semantic retrieval
                                      │
                                      └──► job-level reconstruction
```

## Core principles

- SQLite is the canonical source of truth.
- SQL handles deterministic relational questions.
- The vector index handles semantic similarity over selected free-text fields.
- Semantic retrieval operates on fine-grained semantic units and reconstructs results to jobs.
- The runtime analytics agent is read-only.
- Indexing is incremental, idempotent, version-aware and deletion-aware.
- Retrieval behaviour and indexing behaviour are evaluated separately.

## Repository contracts

| File | Purpose |
|---|---|
| `AGENTS.md` | Instructions for coding agents working on this repository |
| `docs/retrieval_contract.md` | Runtime routing, retrieval and answer behaviour |
| `docs/data_semantics.md` | Meaning of tables and fields |
| `docs/indexing.md` | SQLite-to-vector indexing architecture |
| `golden_questions.yaml` | User-facing retrieval/evaluation cases |
| `indexing_cases.yaml` | Indexing acceptance cases |

## Runtime retrieval routes

Every information request is classified as:

```text
STRUCTURED
SEMANTIC
HYBRID
OUT_OF_SCOPE
```

Clarification and refusal are separate behaviours.

See `docs/retrieval_contract.md`.

## Semantic indexing

Current policy:

```text
scalar assessment field
    → one vector

list assessment field
    → one vector per meaningful list item

job_description
    → chunked vectors
```

See `docs/indexing.md`.

## Development

Python is the default language for orchestration, indexing and application logic.

SQL is the default for relational filtering, joins, aggregation and canonical record retrieval.

For non-trivial changes, the repository agent should propose an implementation plan, confirm contract-changing work with a human, write/update tests before code, then implement the smallest change satisfying the tests.

See `AGENTS.md`.
