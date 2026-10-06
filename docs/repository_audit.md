# Initial repository audit

## Scope and future use

Baseline date: 2026-10-06. Inspected implementation: commit `333cb9f`, before this documentation change. Work item: [#10 — JAA-001](https://github.com/danielBrule/agentic-job-analytics/issues/10).

This is the first ticket on a new, single-person project. Daniel Brule owns all decisions and delivery. Copilot has been used for CV generation; these analytics capabilities have not yet been exercised by the user. Questions are acceptance targets, not evidence of existing functionality or first-release commitments.

This file records a starting baseline. [AGENTS.md](../AGENTS.md) links it for future foundation and evaluation work. GitHub Issues tracks delivery; the [architecture](architecture.md), [data semantics](data_semantics.md), [retrieval contract](retrieval_contract.md) and [indexing contract](indexing.md) remain authoritative. Resolve decisions there and in the linked issues rather than maintaining this file as a second backlog. Changes to this baseline should correct evidence or clarify its original scope, not silently present later progress as initial status.

## Evidence and implementation gaps

| Area | Observed baseline | Follow-up |
|---|---|---|
| Development tooling | `dev.ps1`, public repository validator, pinned PyYAML development dependency and 18 regression tests are implemented | Extend shared checks as runtime code arrives; [#62](https://github.com/danielBrule/agentic-job-analytics/issues/62) |
| CI | Tracked workflow calls the shared entry point on Windows and Linux; this audit does not verify remote runs or branch protection | [Development workflow](development.md#branches-and-ci) |
| Source mapping | Mapping is documented against an upstream commit; live schema metadata and frozen snapshot schema were inspected read-only | Maintain compatibility through [#11](https://github.com/danielBrule/agentic-job-analytics/issues/11) |
| Acceptance definitions | 30 golden questions (version 5) and 50 indexing cases (version 4) are present | They are definitions, not executed runtime tests; [#13](https://github.com/danielBrule/agentic-job-analytics/issues/13), [#50](https://github.com/danielBrule/agentic-job-analytics/issues/50) |
| Evaluation references | Public reference SQL and an ignored private fixture pack exist; qualitative judgments are unreviewed | [#21](https://github.com/danielBrule/agentic-job-analytics/issues/21), [#46](https://github.com/danielBrule/agentic-job-analytics/issues/46) |
| Runtime and safety | No runtime package, relational adapter, SQL safety boundary, semantic retrieval or synthesis implementation | [#18](https://github.com/danielBrule/agentic-job-analytics/issues/18), [#19](https://github.com/danielBrule/agentic-job-analytics/issues/19), [#36](https://github.com/danielBrule/agentic-job-analytics/issues/36), [#56](https://github.com/danielBrule/agentic-job-analytics/issues/56) |
| Indexing | No parser, unit model, embedding/vector adapter, manifest, synchronization or rebuild implementation | [Semantic Index epic #4](https://github.com/danielBrule/agentic-job-analytics/issues/4) |
| LangGraph and context | No graph, conversation scope, checkpointing or bounded model-context implementation | [#30](https://github.com/danielBrule/agentic-job-analytics/issues/30), [#31](https://github.com/danielBrule/agentic-job-analytics/issues/31), [#34](https://github.com/danielBrule/agentic-job-analytics/issues/34), [#35](https://github.com/danielBrule/agentic-job-analytics/issues/35) |
| Application and UI | No application service, launch entry point or chat UI | [#17](https://github.com/danielBrule/agentic-job-analytics/issues/17), [#38](https://github.com/danielBrule/agentic-job-analytics/issues/38), [#39](https://github.com/danielBrule/agentic-job-analytics/issues/39) |
| Models and experiments | Profiles and comparisons are specified; no model adapters, tracing, executable evaluators or comparison runner exist | [#28](https://github.com/danielBrule/agentic-job-analytics/issues/28), [#32](https://github.com/danielBrule/agentic-job-analytics/issues/32), [#59](https://github.com/danielBrule/agentic-job-analytics/issues/59), [#61](https://github.com/danielBrule/agentic-job-analytics/issues/61) |
| Learning walkthrough | Concepts are documented; no runnable guided exercises exist | [#40](https://github.com/danielBrule/agentic-job-analytics/issues/40) |

The live schema inspection read table/column/index metadata only, using SQLite `mode=ro` and `query_only`. It confirmed physical `jobs.id`, `assessments.id`, unique `assessments.job_id`, separate human/model decision columns and documented freshness columns. No `source_version`, `is_deleted` or `deleted_at` columns were found. JSON column declarations do not prove the shape of every stored value; this audit did not read private business rows or independently reverify upstream application behaviour.

The private fixture manifest, historical validation report and semantic-review readiness metadata were inspected. Their previous integrity, provenance and query-replay results were not independently rerun. The fixture guide's reported coverage gaps remain the basis for the tags below. No private job text, identifiers, answers or credentials are reproduced here. Follow [SECURITY.md](../SECURITY.md) for subsequent inspection and exports.

## Definition follow-ups

All decisions below are owned by Daniel Brule under [#12 — JAA-003](https://github.com/danielBrule/agentic-job-analytics/issues/12). Existing tickets already cover the gaps; no duplicate issues are required for this audit.

| Definition | Next decision | Resolve before |
|---|---|---|
| Snapshot lifecycle | Approved paired snapshots and physical deletion; choose generation storage, capture cadence and cleanup implementation | Lifecycle implementation [#52](https://github.com/danielBrule/agentic-job-analytics/issues/52); update affected contracts and acceptance cases explicitly if changed |
| Application closure | Define open/closed mapping from the actual process vocabulary; missing closure reason is insufficient | q06 fixtures and structured coverage [#46](https://github.com/danielBrule/agentic-job-analytics/issues/46), [#47](https://github.com/danielBrule/agentic-job-analytics/issues/47) |
| Interview history | Establish whether interview history is recorded anywhere, then choose a supported source or explicitly defer the capability | q18 fixtures and acceptance coverage [#46](https://github.com/danielBrule/agentic-job-analytics/issues/46), [#54](https://github.com/danielBrule/agentic-job-analytics/issues/54) |
| Candidate technical profile | Identify the canonical profile and version; assess whether Copilot's existing profile is suitable | q19 fixtures and acceptance coverage [#46](https://github.com/danielBrule/agentic-job-analytics/issues/46), [#54](https://github.com/danielBrule/agentic-job-analytics/issues/54) |
| Tokens per assessment | Choose task, attempt or invocation; define model attribution, retry inclusion and unknown usage handling | q21 references and grading [#46](https://github.com/danielBrule/agentic-job-analytics/issues/46), [#59](https://github.com/danielBrule/agentic-job-analytics/issues/59) |

### Approved snapshot and deletion direction

During #10, the user approved serving an older but consistent analytics SQLite/vector pair. Ingestion copies the required SQL tables, changes only affected vector units, reuses unchanged embeddings and publishes both artifacts together after validation. Each request uses one generation throughout; failures preserve the previous pair. Copilot remains canonical and is never modified by analytics ingestion or runtime tools.

Physical deletion removes all corresponding job vectors from the candidate generation. Reassessment replaces changed units and excludes superseded evidence; retaining older vector revisions is optional. Closed/rejected jobs that still exist are not deleted. Configuration changes and non-semantic metadata synchronization can require index work even when semantic content is unchanged. Capture age is visible. The previous pair can retain deleted jobs until publication and retirement.

This approved direction supersedes the original target soft-deletion and mandatory obsolete-vector-retention requirements. It is recorded in [indexing](indexing.md#snapshot-ingestion-and-publication), [retrieval](retrieval_contract.md#14-deleted-and-stale-data) and [data semantics](data_semantics.md#is_deleted-and-deleted_at). Golden definitions now use version 6 and indexing definitions version 5; initial evidence in the table above remains tied to the inspected commit. Runtime ingestion and lifecycle tests remain unimplemented.

[#12](https://github.com/danielBrule/agentic-job-analytics/issues/12) still owns the other four source/evaluation definitions and remaining lifecycle implementation choices. The existing wording of [#52](https://github.com/danielBrule/agentic-job-analytics/issues/52) mentions both soft-deletion fields; align that issue with the approved contract before implementing it. No GitHub issue body has been edited by this repository change.

## Question readiness

The single maintained set of initial readiness tags is now in [golden_questions.yaml](../evals/golden_questions.yaml), under each question's `readiness` mapping. The top-level `readiness_baseline` records date and fixture scope. Definition, data coverage and reference readiness are distinct from expected behavior and implementation status; none means an agent passed. All runtime capabilities and evaluators are missing at this baseline.

[#21](https://github.com/danielBrule/agentic-job-analytics/issues/21) prepares first-flow fixtures and failing tests; [#46](https://github.com/danielBrule/agentic-job-analytics/issues/46) completes reviewed labels and coverage. Both are owned by Daniel Brule. Reassess readiness against each dataset's fixed source, date, history and labels; [#59](https://github.com/danielBrule/agentic-job-analytics/issues/59) records dataset-specific readiness in evaluation artifacts. Pending cases must remain visible and cannot count as passing.

## Contract tensions and validation limits

- The provisional q21 reference groups nullable `task_id` values by requested model. Unrelated calls with no task ID can be combined, contrary to the data-semantics warning. It is supporting evidence only; #12 must settle accounting before the query is promoted or corrected through test-first work.
- The source lacks soft-deletion fields and a native revision counter. Initial physical-deletion support no longer requires the former; derived revision tokens address the latter. Never query absent columns or migrate the canonical database.
- The documented branch flow uses `dev`, but no `dev` branch was found locally or through the GitHub connector during review. This ticket's branch starts from `main`; branch setup remains an operational follow-up under [development instructions](development.md#branches-and-ci).
- Additional upstream fields are outside the analytics mapping. Their meanings must be verified before use; column presence does not establish semantics.

Baseline `dev.ps1 check` passed: 18 regression tests, four public YAML/JSON files, 70 local Markdown links, acceptance/reference consistency and local/staged whitespace. PowerShell required a process-local execution-policy override. These checks exercise repository tooling, not runtime safeguards, reference SQL correctness, indexing acceptance, application journeys or model experiments. The final documentation-change validation result should be recorded with the review/PR; no PR or issue closure is implied by this audit file.

The approved contract/readiness changes added two validator regression tests, first observed failing before implementation. The updated shared check passed with 20 tests. The five added indexing cases are acceptance definitions for future runtime work, not executed ingestion tests. The historical private fixture pack remains unchanged and requires compatibility review before evaluation under the revised versions.
