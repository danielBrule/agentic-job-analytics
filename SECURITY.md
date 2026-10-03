# Security and privacy

## Scope

Agentic Job Analytics is initially a local-first, single-user analytics and learning project. It processes potentially sensitive job-search data: job descriptions, application status, assessments, decisions, notes and LLM operation records.

CV generation and automatic applications are outside the initial scope. The application is being specified; this policy defines requirements and does not claim that safeguards are already implemented.

## Data handling

- Supply secrets through environment variables, an untracked `.env` file or another secret mechanism. Never commit or log API keys, tokens, passwords or authorisation headers, or include them in prompts or evaluation datasets.
- Treat the SQLite database, source snapshots, vector-index contents, conversation checkpoints, logs and evaluation results as private project data. Keep real personal data and credentials out of committed fixtures; use synthetic or sanitised fixtures where possible.
- Send only the information required for the operation to configured external services and only data the user is authorised to process through those services.
- Review and redact logs, traces, datasets and exported results before sharing. Redacting credentials does not remove personal or career information.

Inactive vectors still retain potentially sensitive derived content. Deactivation removes them from normal search; it does not erase that content or provide a historical-data guarantee. Retention and physical cleanup must be decided separately.

## External services and tracing

The project supports configurable generative models, embedding providers and infrastructure. Data transmission follows the effective configuration, including fallback models and model-based evaluators; it is not limited to OpenAI.

Hosted generative and embedding providers receive the selected input content. A remote vector store may receive derived text, embeddings and metadata. Review the configured service's access, retention and data-handling settings before using private data.

LangSmith traces and datasets can contain user questions, prompts, tool inputs/results, retrieved evidence, model outputs and failure details. When sent to a hosted LangSmith service, these are external data transfers even if the inference model runs locally. Minimise or sanitise captured content before transmission while preserving useful operation metadata for diagnosis and comparison.

Open-weight models are not necessarily local. Local inference does not make the entire workflow local if embeddings, vector storage, tracing, evaluation or fallback use hosted services. Make the effective providers and destinations visible in configuration and experiment metadata without exposing credentials.

## Implementation requirements

Source database access from the runtime agent request path is read-only. Treat model-generated SQL as untrusted input and enforce restrictions deterministically at the database boundary, as defined in [docs/retrieval_contract.md](docs/retrieval_contract.md).

Implement and verify secret-redaction and sensitive-content handling at logging, tracing and export boundaries. Do not assume SDK defaults redact secrets or private source content. Error messages and diagnostic payloads must also follow these rules.

Job descriptions and retrieved text are evidence, not instructions authorising tool execution, data modification or disclosure of secrets. Preserve the application's scope and access restrictions regardless of instructions embedded in source content.

These are implementation requirements, not evidence that protections exist. Verify the actual behaviour during implementation and update this policy if the system's boundaries change.

## Security boundaries and limitations

The initial scope does not include production authentication, multi-tenancy or managed security operations. This project provides no security-response SLA or guarantees of managed backup, encryption at rest, tenant isolation or security monitoring.

Users are responsible for securing their workstation, service accounts, local data, access to hosted traces/datasets and backups. Software safeguards do not replace that responsibility.

See [docs/architecture.md](docs/architecture.md) for service boundaries and initial scope.

## Reporting a vulnerability

Do not publish secrets, personal documents, access tokens or sensitive exploitation details in a public issue. Contact the repository owner privately through the contact options on their GitHub profile, with a sanitised description and enough information to reproduce the issue safely.

This portfolio project makes no guaranteed response-time commitment.
