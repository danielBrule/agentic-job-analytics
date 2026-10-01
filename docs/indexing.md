# Indexing Architecture

## Purpose

This document defines how canonical SQLite job-search data becomes a semantic vector index.

The vector index is a derived, rebuildable search structure.

It is not a second source of truth.

Executable acceptance cases live in:

```text
indexing_cases.yaml
```

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
  ├── scalar field ───────► semantic unit
  ├── list item ──────────► semantic unit
  └── job description ────► semantic chunks
  │
  ▼
compare with index state / manifest
  │
  ├── unchanged ──────────► reuse
  ├── new ────────────────► embed + insert
  ├── changed ────────────► embed + update
  └── removed/deleted ────► deactivate/remove
  │
  ▼
vector index
```

---

## 2. Indexed fields

### Scalar semantic fields

Each populated field produces one semantic unit:

```text
role_snapshot
real_mandate
technical_bar
decision_reason
```

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
is_deleted
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
```

Allowed logical `unit_type` values:

```text
scalar
list_item
chunk
```

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

### Job-description chunk

Chunk identity must distinguish chunks belonging to the same job and support change detection.

Exact chunk identity is implementation-specific because chunk boundaries may change when source text changes.

Do not expose storage-engine-specific IDs as domain identifiers.

---

## 6. Normalisation

Normalisation occurs before hashing and embedding.

At minimum:

- trim leading/trailing whitespace
- normalise repeated whitespace
- ignore null values
- ignore empty/whitespace-only values
- parse serialized list fields
- index list items separately

Normalisation should be deterministic.

A whitespace-only source change should not cause a new embedding.

Do not over-normalise semantically meaningful punctuation or wording without evidence that retrieval improves.

---

## 7. Duplicate list items

Within the same:

```text
job_id
assessment_id
field_name
```

identical normalised list items should not produce duplicate active semantic units.

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
is_deleted
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
embed changed scalar only
```

### Added list item

```text
embed new item only
```

### Removed list item

```text
deactivate/remove old item
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

Version of the canonical source record.

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

---

## 12. Deletion

Soft deletion must propagate to semantic retrieval.

If:

```text
is_deleted = true
```

on the canonical job, all semantic units for that job must be unavailable to default search.

Default vector search applies:

```text
is_deleted = false
```

Physical vector removal can be deferred.

Correctness must not depend on immediate physical deletion.

If an unchanged deleted job is restored, its embeddings may be reused.

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
is_deleted
source_version
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

Runtime retrieval must:

1. retrieve semantic units
2. group/deduplicate by `job_id`
3. rank at job level
4. retrieve canonical context from SQLite
5. synthesise the answer

See `docs/retrieval_contract.md`.

---

## 15. Field-aware search

Store `field_name` as filterable metadata.

This enables queries to target appropriate semantic dimensions without creating separate physical indexes for every field.

Examples:

```text
risks
→ red_flags, sustainability_risks, evidence_gaps

role nature
→ job_description, role_snapshot, real_mandate

fit evidence
→ strong_fit_signals, technical_bar, evidence_anchors
```

Field filtering is optional; it must not prevent broader retrieval when the user concept legitimately spans multiple fields.

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

Expected progression:

```text
< 100k vectors
    straightforward local/small deployment

100k–1M
    still routine

1M–10M
    ANN/index configuration and metadata filtering matter more

10M+
    partitioning, operational cost and indexing throughput become first-class concerns
```

Before coarsening semantic units solely to reduce vector count, consider:

- metadata filtering
- ANN tuning
- job-level grouping
- reranking
- partitioning
- batch embedding/indexing

Retrieval quality remains the primary reason for choosing semantic-unit granularity.

---

## 18. Evaluation boundary

`indexing_cases.yaml` evaluates indexing correctness.

Examples:

- list splitting
- scalar handling
- no-op reindex
- item addition/removal
- reordering
- deletion
- version migration
- parent reconstruction

`golden_questions.yaml` evaluates user-facing retrieval capability.

Do not change golden questions merely because the internal indexing implementation changes.
