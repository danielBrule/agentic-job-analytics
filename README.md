# Agentic Job Analytics

A conversational, read-only analytics agent over job opportunities, assessments and LLM operation records.

The repository currently contains project contracts, evaluation references and development checks. Runtime implementation is planned after this specification phase.

This project has two equally important objectives:

1. Build a credible, production-minded agentic analytics system.
2. Gain hands-on experience with modern agentic AI engineering, with visible state transitions and measurable design trade-offs.

LangGraph provides orchestration. LangSmith provides tracing, datasets and evaluation experiments from the start. Small provider adapters keep external services replaceable while preserving direct exposure to these learning technologies.

## Data and retrieval

Copilot SQLite is the canonical source of truth. Analytics uses a published SQLite snapshot paired with its derived vector generation; its capture time is visible. SQL handles exact facts, filters, joins, rankings and aggregations. A derived, rebuildable vector index supports conceptual retrieval.

The agent composes structured query, semantic retrieval and synthesis capabilities independently, sequentially or in parallel. Semantic units are consolidated by job ID and enriched with SQLite context from the same published snapshot before answering. Assessment-dependent analytics uses zero or one current successful assessment per job.

Indexing is incremental, idempotent, version-aware and deletion-aware. Obsolete units are excluded from normal search; physically deleted jobs are removed from the next published generation. Bullet-formatted assessment text, parsed list items and job-description chunks retain source provenance.

## Contracts

| File | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Coding-agent working instructions |
| [docs/architecture.md](docs/architecture.md) | Learning objectives, service boundaries, model strategies and scope |
| [docs/retrieval_contract.md](docs/retrieval_contract.md) | Capability composition, retrieval and answer behaviour |
| [docs/data_semantics.md](docs/data_semantics.md) | Business meaning of entities and fields |
| [docs/indexing.md](docs/indexing.md) | Relational-to-vector indexing design |
| [evals/golden_questions.yaml](evals/golden_questions.yaml) | User-facing acceptance cases |
| [evals/indexing_cases.yaml](evals/indexing_cases.yaml) | Indexing acceptance cases |
| [evals/fixtures/README.md](evals/fixtures/README.md) | Evaluation snapshots, reference facts and review coverage |

## Development

Python handles orchestration, transformation and application logic; SQL handles deterministic relational operations. Tests and acceptance cases precede behavioural implementation.

Use `./dev.ps1 setup` once, then `./dev.ps1 check` before proposing changes. See [docs/development.md](docs/development.md) for commands and the feature → `dev` → `main` workflow, [AGENTS.md](AGENTS.md) for coding-agent instructions and [docs/architecture.md](docs/architecture.md) for the initial scope.
