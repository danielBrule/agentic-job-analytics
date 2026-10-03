# Indexing Architecture

## Purpose

This document defines how canonical SQLite job-search data becomes a semantic vector index.

The vector index is a derived, rebuildable search structure.

It is not a second source of truth.

Acceptance definitions live in [indexing_cases.yaml](../evals/indexing_cases.yaml). The executable indexing harness remains implementation work. Cases use sparse normalized indexing inputs to isolate behaviour; they are not complete physical source rows.

---

## 1. Architecture

```text
SQLite
  │
  │ canonical jobs + assessments
  ▼
extract changed records
  │
  ▼
normalise
  │
  ├── technical_bar ──────► scalar unit
  ├── assessment bullet ─► bullet unit
  ├── list item ──────────► semantic unit
  └── job description ────► semantic chunks
  │
  ▼
compare with index state / manifest
  │
  ├── unchanged ──────────► reuse
  ├── new ────────────────► embed + insert
  ├── changed ────────────► embed replacement + deactivate previous
  └── removed/deleted ────► deactivate
  │
  ▼
vector index
```

---

## Current source selection

Extract each job with zero or one current successful assessment, as mapped in [data_semantics.md](data_semantics.md). The checked Copilot source updates the same assessment row on successful reassessment and preserves it on failure. Only `ASSESSED` rows supply assessment-derived units; job descriptions remain indexable without an assessment.

Compare all currently expected units for the affected job/field with the manifest. Reassessment may leave the same `assessment_id` while changing content. Reuse unchanged units; deactivate units that no longer belong to the current successful result. Never make multiple assessment results active for one job.

A field change for job A does not re-embed job B or unrelated fields. Changes to embedding configuration or indexing rules may intentionally affect a broader set.

## 2. Indexed fields

### Scalar semantic field

The complete populated `technical_bar` field produces one unit, even when it contains several sentences or bullet-like formatting.

### Bullet-formatted assessment text

These fields remain scalar text in SQLite but produce one unit per meaningful bullet:

```text
role_snapshot
real_mandate
decision_reason
```

Recognise `-` or `*` after optional indentation at the start of a line, followed by whitespace. Preserve line boundaries until parsing is complete. Remove the marker, then normalize each bullet's content. Do not split on internal hyphens or asterisks.

Continuation lines belong to the preceding bullet. Treat whitespace-only marker content as empty. Preserve a nonempty preamble before the first bullet as one scalar unit. If there are no recognised markers, preserve the complete field as one scalar unit. Ignore empty units and deduplicate identical normalized bullets within the same job, assessment and field.

Do not use an LLM for bullet parsing or split these short fields by arbitrary character limits. Retrieve parent context when a bullet is insufficient on its own.

### List semantic fields

Each meaningful parsed list item produces one semantic unit:

```text
strong_fit_signals
red_flags
sustainability_risks
evidence_gaps
evidence_anchors
```

Do not embed the serialized list as one vector.

Example source:

```text
["Heavy travel", "Large business-development target"]
```

becomes two semantic units.

### Evidence-anchor objects

The checked source stores `evidence_anchors` as JSON objects with `source_reference`, `evidence` and `supports`, not as strings. Each anchor still produces one unit. Render its semantic text deterministically:

```text
Evidence: <evidence>
Supports: <supports>
```

Keep `source_reference` as metadata and preserve the complete canonical object in SQLite. `evidence` is candidate-profile evidence from Document A; `supports` is its assessment interpretation. Do not relabel either as a job-description quote or embed serialized JSON. Empty/malformed required values are explicit parsing errors.

For anchor identity, include `source_reference` as well as rendered content when distinct references would otherwise collide. Exact duplicate anchors within the same job/assessment/field may be deduplicated. Metadata-only changes can reuse embeddings when rendered content is unchanged.

### Long-form field

```text
job_description
```

A job description is chunked when it is too large to be a useful single retrieval unit.

---

## 3. Why fine-grained semantic units

The indexing model optimises retrieval precision rather than minimising vector count.

Example query:

> roles with concerns around stakeholder management

A dedicated `red_flags` item such as:

```text
"Significant daily C-suite stakeholder exposure"
```

is a cleaner semantic match than a vector representing several unrelated assessment fields.

The trade-off is more vectors and therefore a need for job-level grouping during retrieval.

That trade-off is intentional.

---

## 4. Semantic-unit model

Each indexed unit should expose at least:

```text
semantic_unit_id
job_id
field_name
unit_type
content
content_hash
source_version
source_updated_at
is_active
is_deleted
deleted_at
indexed_at
embedding_model
embedding_version
index_schema_version
```

Assessment-derived units should also retain:

```text
assessment_id
```

Where useful:

```text
unit_position
source_reference
```

Allowed logical `unit_type` values:

```text
scalar
bullet
list_item
chunk
```

### Provenance naming

Keep one logical metadata vocabulary: `field_name` identifies the source field, `unit_type` identifies its representation, and `semantic_unit_id` identifies the unit. Description chunks also carry `unit_position`. These fulfil document-type and chunk-ID provenance needs without parallel aliases.

`source_updated_at` maps to `jobs.updated_at` or `assessments.updated_at`, according to the owning record. The source has no native `source_version` counter; compute an opaque deterministic source-revision token. Whole-second timestamps are not unique versions, so semantic content hashes must catch changes even when timestamps match. `deleted_at` is the canonical job deletion timestamp, including on assessment-derived units. `indexed_at` records when a unit's indexed state was last synchronized and must not be used as evidence of source freshness.

`index_schema_version` is the document/semantic-unit schema version. `embedding_model` identifies the model and `embedding_version` tracks model/configuration revisions. If a provider exposes a model revision, include it in that configuration's recorded provenance. The verified mappings and remaining deletion gap are documented in `docs/data_semantics.md`.

---

## 5. Identity

Semantic-unit identity should be deterministic where practical.

### Scalar

Conceptually:

```text
job_id + assessment_id + field_name
```

### List item

Conceptually:

```text
job_id + assessment_id + field_name + normalized_content_hash
```

The list position must not be the sole identity.

Reordering:

```text
[A, B, C]
```

to:

```text
[B, A, C]
```

must not force re-embedding of unchanged items.

### Assessment bullet

Conceptually:

```text
job_id + assessment_id + field_name + normalized_content_hash
```

Bullet position and marker style are not identity. Reordering bullets or replacing `-` with `*` must not force re-embedding. A changed bullet deactivates its previous record and creates a new active one. Nonempty preamble or unmarked fallback text uses scalar identity.

### Active and obsolete records

`is_active` indicates whether an indexed record belongs to the current semantic projection and embedding/index configuration. It is separate from `is_deleted`, which describes the parent job's source deletion state. An obsolete bullet for an undeleted job has `is_active = false` while the job remains `is_deleted = false`.

When semantic content changes, prepare the replacement and deactivate the previous vector record. Removed bullets/items, superseded scalar records and old schema/model records are deactivated rather than physically deleted during normal indexing. Keep exactly one active record per current semantic unit and configuration.

The scalar semantic-unit identity remains stable. Storage-level record IDs must distinguish its content/configuration revisions, for example using the logical unit ID, content hash and embedding/index versions. Do not overwrite the only prior record when the required outcome is deactivation; provider-specific record IDs remain an adapter concern.

Publish the replacement and retire its predecessor as one logical handover where supported. Failed embedding/upsert must not activate an incomplete replacement. Runtime freshness checks still prevent old indexed text from being presented as current evidence while synchronization is incomplete.

Inactive vectors may be retained for inspection and possible reuse. This does not guarantee historical reconstruction: the canonical source retains only the current assessment. Historical querying and cleanup/retention policy are separate future decisions. Do not automatically reactivate every inactive vector when a job is restored; activate only units matching the current source and configuration.

### Job-description chunk

Chunk identity must distinguish chunks belonging to the same job and support change detection.

Exact chunk identity is implementation-specific because chunk boundaries may change when source text changes.

Do not expose storage-engine-specific IDs as domain identifiers.

---

## 6. Normalisation

Parsing occurs before content normalisation. Preserve line boundaries while identifying bullets; normalise extracted unit content before hashing and embedding.

At minimum:

- trim leading/trailing whitespace
- normalise repeated whitespace
- ignore null values
- ignore empty/whitespace-only values
- parse serialized list fields
- index list items separately
- parse bullet-formatted fields at line-start markers and retain continuation lines
- normalise marker style out of bullet content

Normalisation should be deterministic.

A whitespace-only source change should not cause a new embedding.

Do not over-normalise semantically meaningful punctuation or wording without evidence that retrieval improves.

---

## 7. Duplicate list items and bullets

Within the same:

```text
job_id
assessment_id
field_name
```

identical normalised string-list items or bullets should not produce duplicate active semantic units. Object anchors preserve distinct source references as defined above.

Identical text across different jobs remains separate because each unit belongs to a different parent entity.

---

## 8. Job-description chunking

Job descriptions are materially longer than the assessment scalar fields and should support multiple chunks.

Prefer natural boundaries where practical:

- headings
- paragraphs
- bullet groups
- sections

Avoid blindly splitting in the middle of a meaningful unit when a nearby natural boundary exists.

The exact chunk size and overlap are implementation configuration, not a domain contract.

Tune them through retrieval evaluation rather than hard-coding them into the semantic model.

Each chunk must preserve:

```text
job_id
field_name = job_description
unit_type = chunk
unit_position
content_hash
source_version
source_updated_at
is_active
is_deleted
deleted_at
indexed_at
```

---

## 9. Incremental indexing

Indexing is incremental.

For each candidate unit:

1. normalise content
2. compute `content_hash`
3. compare with the current indexed state
4. embed only if required

### New unit

```text
embed
insert
```

### Unchanged unit

```text
reuse existing embedding
update non-semantic metadata if required
```

### Changed scalar

```text
embed replacement for changed technical_bar or unmarked fallback/preamble only
activate replacement and deactivate previous record
```

### Added, removed, changed or reordered bullet

Apply the same content-based incremental rules as list items below. Embed only new or changed bullets, deactivate removed bullets, and update positions without embedding on reorder.

### Added list item

```text
embed new item only
```

### Removed list item

```text
deactivate old item
do not re-embed remaining items
```

### Reordered list

```text
update position metadata if needed
do not re-embed
```

---

## 10. Idempotency

Running the indexer repeatedly against unchanged source data must produce:

- no duplicate active units
- no unnecessary embedding calls
- no semantic changes to the index

Idempotency is a required behaviour, not an optimisation.

---

## 11. Versioning

Track three distinct version concepts.

### `source_version`

Opaque derived revision token identifying the source state used for this unit. The checked upstream has no native version counter; the token must not be mistaken for a source column.

Used to identify whether source state changed.

A source-version change does not automatically require re-embedding if the semantic content hash is unchanged.

### `embedding_version`

Version of embedding configuration.

May encode changes such as:

- embedding model
- dimensionality
- preprocessing that affects embeddings

Changing this version can require re-embedding otherwise unchanged units.

### `index_schema_version`

Version of the semantic-unit/index contract.

Use for controlled migrations when unit structure or indexing semantics change.

Do not overload one version field to represent all three concepts.

An existing index built with one unit per assessment scalar is incompatible with bullet-level units. When migrating such an index, increment `index_schema_version` and rebuild or migrate affected fields. Deactivate old whole-field units when replacing them with bullets; do not leave both representations active. For a new index, initialise the schema version for the implemented contract. The version in `evals/indexing_cases.yaml` tracks acceptance definitions separately from the runtime index schema version.

---

## 12. Deletion

Soft deletion must propagate to semantic retrieval.

If:

```text
is_deleted = true
```

on the canonical job, all semantic units for that job must be unavailable to default search.

Propagate both `is_deleted` and `deleted_at` from the canonical job to every unit. Active/restored units have a null timestamp; deleted units retain the source deletion timestamp. Inconsistent source values are an explicit error and exclude the job from normal retrieval. See `docs/data_semantics.md`.

Default vector search applies:

```text
is_active = true
is_deleted = false
deleted_at IS NULL
```

Normal indexing deactivates records and retains their vectors; physical removal is a separate future cleanup decision. Correctness must not depend on physical deletion.

If an unchanged deleted job is restored, its current units may be reactivated and their embeddings reused. Superseded units must remain inactive.

The checked Copilot source does not yet implement soft deletion. For confirmed missing jobs, deactivate all units without inventing `deleted_at`; see the integration gap in `docs/data_semantics.md`. Complete source reconciliation must detect physical deletion as well as new/changed records. Failed or partial reads must not deactivate supposedly missing jobs.

---

## 13. Index metadata vs canonical data

The vector store may duplicate limited metadata needed for:

- filtering
- reconstruction
- version checks
- deletion checks

Examples:

```text
job_id
assessment_id
field_name
unit_type
is_active
is_deleted
deleted_at
source_version
source_updated_at
```

Canonical business attributes still belong to SQLite.

For example, use SQLite as the authoritative value for:

- company
- title
- current application status
- scores
- dates

---

## 14. Retrieval implications

Fine-grained indexing means semantic results must be reconstructed to jobs.

Example:

```text
job_42 / red_flags / hit
job_42 / sustainability_risks / hit
job_17 / real_mandate / hit
```

represents two jobs, not three.

Indexing must preserve identifiers and provenance that support job-level grouping and canonical reconstruction. Runtime ranking, context expansion and synthesis are defined in [retrieval_contract.md](retrieval_contract.md#11-semantic-scope-and-job-level-ranking).

---

## 15. Field-aware search

Store `field_name` as filterable metadata so retrieval can select semantic dimensions without requiring a separate physical index for each field. Runtime field-selection hints and their limits are defined in [retrieval_contract.md](retrieval_contract.md#9-field-aware-semantic-retrieval).

---

## 16. Rebuildability

The vector index must be rebuildable entirely from:

```text
SQLite
+
indexing configuration
+
embedding configuration
```

No unique business information may exist only in the vector store.

A full rebuild should produce behaviourally equivalent semantic units for the same source/configuration.

---

## 17. Scaling

The semantic model should not change merely because vector count grows.

Capacity depends on embedding dimensions, metadata filters, backend, hardware and workload. Measure latency, memory, indexing throughput and cost rather than assuming a vector-count threshold guarantees a particular deployment size.

Before coarsening semantic units solely to reduce vector count, consider:

- metadata filtering
- ANN tuning
- job-level grouping
- reranking
- partitioning
- batch embedding/indexing

Evaluate granularity against all equally important [engineering criteria](../AGENTS.md#1-engineering-principles). Existing unit contracts remain requirements; a material conflict or proposed contract change goes to the human with evidence.

---

## 18. Evaluation boundary

[Indexing cases](../evals/indexing_cases.yaml) define transformation and index-lifecycle acceptance. [Golden questions](../evals/golden_questions.yaml) define user-facing retrieval acceptance; internal indexing changes alone do not change them. See [architecture.md](architecture.md#evaluation-and-observability) for metrics and [evaluation fixtures](../evals/fixtures/README.md) for real-data coverage and controlled synthetic transitions.
