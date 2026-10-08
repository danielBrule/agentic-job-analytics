# Evaluation fixtures

[golden_questions.yaml](../golden_questions.yaml) defines the expected behaviour. Fixtures bind those questions to fixed source data, reference results and conversation context. They do not change the questions or prove that an agent implementation passes them.

Per-question `readiness` tags in [golden_questions.yaml](../golden_questions.yaml) distinguish definition, data coverage and reference readiness. The top-level baseline date and data scope identify what those tags describe. They are planning metadata, not expected behavior or passing results; freeze dataset-specific readiness with each implemented evaluation version. The [audit](../../docs/repository_audit.md#question-readiness) links the delivery follow-ups.

## Shared offline test helpers

[tests/support](../../tests/support/__init__.py) provides the common foundation for contract tests. Run it through `./dev.ps1 test` or `./dev.ps1 check`; unittest discovery makes the `support` package available to tests. Both GitHub Actions jobs use the same entry point. No private database, credentials, model calls or external upload is required.

- [Contract loaders](../../tests/support/contracts.py) load both YAML suites by stable ID, preserving suite metadata and sparse case payloads. Reference loading validates version, IDs and exact/supporting status using the repository validator's duplicate-key-safe parser. `resolve_text_fixtures` expands named synthetic descriptions in a copy of a case. `assert_reference_rows` compares expected integer facts exactly, expected floating values with the reference absolute tolerance, NULL values and duplicate-row multiplicity. Booleans do not match numbers. Ordering is opt-in; ranking tests must check the requested metric while allowing ties.
- [SQLite builders](../../tests/support/sqlite_fixtures.py) create fresh in-memory databases with synthetic jobs, zero or one current assessment, and historical calls. The schema is an analytics-field projection, not a replica or migration of Copilot. It enforces job foreign keys and unique assessment membership; background-task tables and their constraints are not replicated. JSON arrays/objects are serialized on insertion. Raw JSON strings are also accepted for parsing-error scenarios. Omitted fields remain NULL unless a documented builder default supplies them.
- [Text fixtures](../../tests/support/text_fixtures.py) provide long descriptions with stable paragraphs and a version changing exactly one section. These are chunking inputs, not a selected chunk-size policy.
- [Service doubles](../../tests/support/doubles.py) record embedding, model and vector calls and support failures. Embeddings are stable hash vectors with no semantic meaning. Model outputs and vector hits are explicitly scripted, and script exhaustion fails rather than inventing results. Vector writes operate only on the double's in-memory records. These are test helpers, not approved production provider interfaces or an implementation of ranking, generation publication or fallback.

Synthetic data and builder code are committed; generated SQLite files are not. Each test gets isolated state and closes its connections. SQLite remains authoritative for test facts; a vector double's results are supplied test inputs, not a second business database.

For controlled indexing transitions, insert a job and assessment, then call `update("assessments", assessment_id, real_mandate=...)`. Only specified fields change: timestamps remain unchanged unless supplied, enabling timestamp-collision and metadata-only tests. Each edit commits immediately, allowing SQLite's native backup API to capture a fixed snapshot without an outstanding write transaction. Recording a failed call leaves the retained successful assessment untouched. `delete_job` physically removes a synthetic job and its dependent rows; reintroduce it with `job`. Do not treat sparse indexing YAML inputs as physical SQLite rows or add derived `source_version`/deletion columns to the source fixture.

[Harness tests](../../tests/test_contract_harness.py) exercise helper isolation, source constraints, controlled transitions, named description resolution, service failures, private-pack compatibility and public reference SQL against independently asserted synthetic facts. Existing q18/q19/q21 tests reuse these builders. They do not execute a runtime graph or indexer; loading all acceptance cases does not mark those cases as passed. Semantic labels, real-provider retrieval evaluation and LangSmith experiments remain separate implementation work.

### Reusing existing private snapshots

Private access is explicit and local. `open_private_snapshot(path)` opens an existing frozen SQLite snapshot with `mode=ro`, `immutable=1` and `query_only`; it never creates, replaces or refreshes a database. It rejects WAL, shared-memory and rollback-journal sidecars rather than reading journal content outside the snapshot hash. The selected snapshot must remain frozen while it is validated and used. Prepare a separate SQLite-native backup before using a changing source; this helper does not perform capture. Close the returned connection when finished. Opening a file alone does not validate its labels or contract compatibility.

Prefer `open_private_pack(directory, repository_root)` when using the documented fixture pack. It checks current golden/indexing versions and definition hashes, the reference-definition hash, a fixed reference date, artifact hashes and snapshot membership before opening the existing snapshot read-only. Artifact paths must stay within the pack. It rejects stale packs with an explicit refresh-required error; it does not relabel or rebuild them. Passing these checks establishes integrity/definition compatibility, not approved relevance judgments or runtime correctness. The historical pack remains unchanged and incompatible with the current contract versions.

Tests of private access use temporary synthetic files, so GitHub Actions never opens the actual private pack. Runtime integration tests will build the derived index from their selected SQLite snapshot through the actual indexer and providers when those are implemented.

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

There are SQL references for q01–q05, q21–q26 and the q29 follow-up. The metric references for q23–q26 support synthesis grading; their existence does not establish a preferred model or validate an explanation. q07, q08 and q10 have supporting raw items/dimensions. q18 supplies current-interview seeds and q19 supplies high-technical-fit NO_GO jobs with stored reasons; both remain supporting evidence because semantic comparison or reason interpretation needs reviewed labels. [Synthetic SQLite execution tests](../../tests/test_reference_queries.py) cover their exact selection, usable-assessment handling and missing evidence.

q21 follows approved task/resolved-model accounting, with execution tests including retries, mixed models, unassigned calls and incomplete usage. Historical private results still require recomputation; the approved queries do not retroactively validate them.

Call usage, missing-value handling and historical version semantics follow [data_semantics.md](../../docs/data_semantics.md#10-llm_calls-semantics). Query-specific interpretation limits are recorded alongside each reference definition.

Use the pack's fixed reference date and conversation history in every compared experiment. Follow the [model comparison workflow](../../docs/architecture.md#model-comparison-and-human-selection) for the remaining controls and experiment metadata.

## Remaining coverage and review

Real data is useful but does not contain every required case. The prepared pack has no current `GO` assessments and no recorded interview stages. Synthetic SQL tests now include all four current interview rounds and exclusion cases, but full q18 similarity evaluation still needs candidate roles and reviewed relevance/seniority labels. Add meaningful GO-seed fixtures alongside the real-data pack. An empty result alone does not validate those behaviours. The owner removed q06 on 2026-10-07, so overdue/open/closed fixtures are no longer required by the acceptance questions.

The owner approved q18 current-stage selection using `1st round` through `4th round`; rejected status does not preserve interview history. See [application status semantics](../../docs/data_semantics.md#application_status). q19 now selects current successful NO_GO assessments with `tech_bar_fit >= 8` and interprets their documented reasons. It requires no Document A input; the historical pack's exclusion of reference assets is therefore no longer a q19 coverage gap. Its technical, nontechnical, mixed and insufficient-evidence judgments still need review.

Resolve the affected [integration and evaluation definitions](../../docs/data_semantics.md#12-unresolved-integration-and-evaluation-definitions) before treating these cases as fully labelled. Do not change existing golden questions to accommodate gaps in the snapshot.

Semantic relevance and thematic grouping require reviewed judgments. An empty `judgments` array means “unreviewed”, not “no relevant jobs”. Record job IDs, evidence references, rationale and reviewer; preserve partial relevance, negative examples and insufficient evidence. Freeze approved labels before comparing models. Do not let the evaluated model define its own ground truth.

The initial private pack records golden-question version 5 and indexing-case version 4. The contracts now use versions 8 and 5: golden version 6 introduced paired snapshot publication, physical deletion and readiness metadata; version 7 removed q06 and defined q21 accounting; version 8 defines current-stage q18 and score-based q19. Do not relabel the historical pack as revalidated: verify compatibility and refresh its manifest/references during fixture implementation before using it for the new contract. Current readiness metadata includes synthetic q18/q19/q21 reference tests; it does not claim the private pack has been refreshed.

The supplied semantic review material is a starting point, not an executable evaluator or approved answer key. During implementation, add the evaluator and LangSmith dataset/experiment runner, then validate model profiles against these fixed fixtures. No model experiment or external upload has been performed while preparing this pack.

The indexing acceptance cases in [indexing_cases.yaml](../indexing_cases.yaml) remain separate. A frozen source snapshot can exercise real parsing, but update, deactivation, restoration and schema/embedding migrations also need controlled synthetic transitions.
