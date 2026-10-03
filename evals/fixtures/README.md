# Evaluation fixtures

[golden_questions.yaml](../golden_questions.yaml) defines the expected behaviour. Fixtures bind those questions to fixed source data, reference results and conversation context. They do not change the questions or prove that an agent implementation passes them.

## Real-data fixture packs

A private fixture pack has been prepared from the local Copilot database at `C:/git/job-application-copilot/data/database/job_application_copilot.db`. Packs live under `data/evals/copilot-<source-hash-prefix>/`, outside the committed evaluation definitions. The repository's `data/` ignore rule excludes the real data and results. Follow [SECURITY.md](../../SECURITY.md) when using or sharing them.

The pack contains:

| Artifact | Purpose |
|---|---|
| `manifest.json` | Source and snapshot hashes, physical schema coverage, fixed reference date, artifact hashes and readiness of each golden question |
| `evaluation.db` | Frozen SQLite rows for jobs, assessments, LLM calls and the background-task tables required by their foreign keys |
| `validation_report.json` | Snapshot integrity, reference-query checks and validation limits |
| `reference_results.json` | Executed reference SQL and expected rows, tied to the snapshot and golden-question hashes |
| `behavior_references.json` | Refusal/clarification expectations and a fixed q01 → q29 conversation |
| `review_jobs.jsonl` | Job descriptions and current successful assessment evidence for local review; unsuccessful assessment content is excluded |
| `semantic_review.json` | Unreviewed relevance judgments and structured seed sets for semantic questions |

The snapshot preserves source identifiers and source table definitions. It excludes unrelated CV documents, reference assets and prompt contents. Assessment-dependent references use only `status = 'ASSESSED'`; job descriptions remain available for jobs without a usable assessment. The snapshot schema is copied for evaluation, not a new canonical source schema.

The source database was accessed through filesystem reads. An intermediate private byte copy was made while no SQLite WAL or rollback journal was present, with stable file metadata and matching source hashes verified. SQLite integrity, foreign keys and exact copied rows were then checked. For future refreshes, use a SQLite-native backup when the source may be changing or has a WAL/journal. Never copy only the main database file from an active WAL database.

## Reference facts and grading

[reference_queries.json](reference_queries.json) contains SQLite reference queries and their status:

- `exact_sql_reference`: deterministic expected facts are available. Compare results, source identifiers and requested ranking, rather than SQL text or answer wording.
- `supporting_evidence_only`: the query supplies exact inputs or diagnostics; it does not establish the complete expected qualitative answer.

There are SQL references for q01–q05, q22–q26 and the q29 follow-up. The metric references for q23–q26 support synthesis grading; their existence does not establish a preferred model or validate an explanation. q07, q08 and q10 have supporting raw items/dimensions. q21 has a proposed per-task/per-requested-model calculation, explicitly awaiting a definition of “per assessment”.

Include reported token usage from failed calls. Keep unreported usage distinct from zero, expose coverage and do not add cache counts again to total tokens. A requested model is not proof of the resolved model. q25 uses prompt versions recorded on individual calls; q26 attributes calls to the current successful assessment's role family and does not claim historical family tracking.

Use the pack's fixed reference date and conversation history in every compared experiment. Keep data, derived index, embedding configuration, prompts and evaluators fixed when comparing generative models, as required by [architecture.md](../../docs/architecture.md).

## Remaining coverage and review

Real data is useful but does not contain every required case. The prepared pack has no next-action dates, no current `GO` assessments and no recorded interview stages. Add small synthetic fixtures for meaningful overdue/open/closed, GO-seed and interview-seed tests, alongside the real-data pack. An empty result alone does not validate those behaviours.

Resolve closure and interview-stage vocabulary, the candidate technical-profile source for q19 and the assessment-run unit/model attribution for q21 before treating these cases as fully labelled. Do not change existing golden questions to accommodate gaps in the snapshot.

Semantic relevance and thematic grouping require reviewed judgments. An empty `judgments` array means “unreviewed”, not “no relevant jobs”. Record job IDs, evidence references, rationale and reviewer; preserve partial relevance, negative examples and insufficient evidence. Freeze approved labels before comparing models. Do not let the evaluated model define its own ground truth.

The supplied semantic review material is a starting point, not an executable evaluator or approved answer key. During implementation, add the evaluator and LangSmith dataset/experiment runner, then validate model profiles against these fixed fixtures. No model experiment or external upload has been performed while preparing this pack.

The indexing acceptance cases in [indexing_cases.yaml](../indexing_cases.yaml) remain separate. A frozen source snapshot can exercise real parsing, but update, deactivation, restoration and schema/embedding migrations also need controlled synthetic transitions.
