"""Exercise shared contract fixtures without models, services or private data."""

from pathlib import Path
from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import unittest

from support.contracts import load_suite, load_references, resolve_text_fixtures, assert_reference_rows
from support.sqlite_fixtures import SyntheticDatabase, open_private_snapshot, open_private_pack
from support.doubles import EmbeddingDouble, ModelDouble, VectorDouble


ROOT = Path(__file__).resolve().parents[1]


class ContractLoaderTest(unittest.TestCase):
    def test_current_suites_keep_ids_metadata_and_sparse_inputs(self) -> None:
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        indexing = load_suite(ROOT / "evals/indexing_cases.yaml", "cases")
        self.assertEqual(len(golden.by_id), 29)
        self.assertNotIn("q06", golden.by_id)
        self.assertEqual(len(indexing.by_id), 55)
        self.assertEqual(golden.metadata["version"], 8)
        self.assertEqual(indexing.metadata["indexing_policy"]["fixture_conventions"]["representation"],
                         "normalized_index_input")
        self.assertEqual(golden.by_id["q29"]["expected_behavior"], "contextual_follow_up")
        references = load_references(ROOT / "evals/fixtures/reference_queries.json", golden)
        self.assertEqual(references["q18"]["status"], "supporting_evidence_only")
        self.assertEqual(references["q21"]["status"], "exact_sql_reference")

    def test_invalid_documents_fail_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.yaml"
            for content in ("version: 1\nversion: 2\ncases: []", "version: 1\ncases: [{id: x}, {id: x}]",
                            "version: 1\ncases: [{}]", "[]", "version: true\ncases: [{id: x}]"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_suite(path, "cases")

    def test_named_descriptions_resolve_without_mutating_cases(self) -> None:
        suite = load_suite(ROOT / "evals/indexing_cases.yaml", "cases")
        case = suite.by_id["long_job_description"]
        resolved = resolve_text_fixtures(case)
        self.assertIn("job_description", resolved["source"])
        self.assertNotIn("job_description", case["source"])
        for case in suite.by_id.values():
            resolve_text_fixtures(case)
        with self.assertRaisesRegex(ValueError, "Unknown text fixture"):
            resolve_text_fixtures({"job_description_fixture": "missing"})

    def test_reference_versions_ids_and_statuses_are_checked(self) -> None:
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.json"
            for version, identifier, status in ((7, "q01", "exact_sql_reference"),
                                                (8, "q06", "exact_sql_reference"), (8, "q01", "passed")):
                path.write_text(json.dumps({"golden_questions_version": version, "references": [
                    {"id": identifier, "status": status, "sql": "SELECT 1"}]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_references(path, golden)

    def test_fact_comparison_respects_tolerance_nulls_duplicates_and_order(self) -> None:
        assert_reference_rows([{"id": 2, "mean": None}, {"id": 1, "mean": 8.0000001}],
                              [{"id": 1, "mean": 8.0}, {"id": 2, "mean": None}])
        for actual, expected in (([{"count": 2}], [{"count": 3}]),
                                 ([{"mean": 8.01}], [{"mean": 8.0}]),
                                 ([{"mean": 0}], [{"mean": None}]),
                                 ([{"id": 1}], [{"id": 1}, {"id": 1}])):
            with self.assertRaises(AssertionError):
                assert_reference_rows(actual, expected)
        with self.assertRaises(AssertionError):
            assert_reference_rows([{"id": 2}, {"id": 1}], [{"id": 1}, {"id": 2}], ordered=True)

    def test_integer_facts_are_exact_and_booleans_are_not_numbers(self) -> None:
        for actual, expected in ((1.0000001, 1), (True, 1), (1, True), (True, 1.0)):
            with self.subTest(actual=actual, expected=expected):
                with self.assertRaises(AssertionError):
                    assert_reference_rows([{"value": actual}], [{"value": expected}])
        assert_reference_rows([{"value": 1.0}], [{"value": 1}])


class SQLiteFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = SyntheticDatabase()
        self.addCleanup(self.fixture.close)
        self.db = self.fixture.connection

    def test_source_projection_constraints_and_isolation(self) -> None:
        self.fixture.job(1)
        self.fixture.assessment(101, 1, evidence_anchors=[{
            "source_reference": "SYNTHETIC-01", "evidence": "Built tools", "supports": "Delivery fit"}])
        self.assertEqual(self.db.execute("SELECT json_extract(evidence_anchors, '$[0].evidence') FROM assessments").fetchone()[0], "Built tools")
        with self.assertRaises(sqlite3.IntegrityError):
            self.fixture.assessment(102, 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.fixture.assessment(103, 99)
        with SyntheticDatabase() as other:
            self.assertEqual(other.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        self.assertFalse(columns & {"source_version", "is_deleted", "deleted_at"})

    def test_transitions_are_committed_and_can_be_captured_with_sqlite_backup(self) -> None:
        self.fixture.job(1)
        self.assertFalse(self.db.in_transaction)
        self.fixture.assessment(101, 1)
        self.fixture.call(1, job_id=1)
        self.fixture.update("jobs", 1, application_status="Applied")
        self.assertFalse(self.db.in_transaction)
        with closing(sqlite3.connect(":memory:")) as snapshot:
            self.db.backup(snapshot)
            self.assertEqual(snapshot.execute("SELECT application_status FROM jobs").fetchone()[0], "Applied")
            self.fixture.delete_job(1)
            self.assertFalse(self.db.in_transaction)
            self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)

    def test_transitions_preserve_assessment_identity_and_failed_attempt(self) -> None:
        self.fixture.job(1)
        self.fixture.assessment(101, 1, real_mandate="Own prototypes")
        before = dict(self.db.execute("SELECT * FROM assessments").fetchone())
        self.fixture.call(1, job_id=1, task_id=10, status="FAILED", total_tokens=None)
        self.assertEqual(dict(self.db.execute("SELECT * FROM assessments").fetchone()), before)
        self.fixture.update("assessments", 101, real_mandate="Own production")
        after = dict(self.db.execute("SELECT * FROM assessments").fetchone())
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["updated_at"], before["updated_at"])
        self.assertEqual(after["real_mandate"], "Own production")
        self.fixture.delete_job(1)
        for table in ("jobs", "assessments", "llm_calls"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.fixture.job(1, job_description="Reintroduced role")
        self.assertEqual(self.db.execute("SELECT job_description FROM jobs").fetchone()[0], "Reintroduced role")

    def test_reference_facts_cover_job_only_assessed_and_historical_calls(self) -> None:
        self.fixture.job(1, location="FR", date_added="2026-01-10", application_status="1st round")
        self.fixture.job(2, location="UK", date_added="2026-01-11")
        self.fixture.assessment(101, 1, decision="GO", fit_score=8, priority_score=9,
                                primary_role_family="Synthetic delivery")
        self.fixture.call(1, job_id=1, task_id=10, total_tokens=20, version_metadata={"prompt_version": "old"})
        self.fixture.call(2, job_id=1, task_id=10, total_tokens=30, retry_number=1,
                          status="FAILED", started_at="2026-02-01 12:00:00", version_metadata={"prompt_version": "new"})
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        references = load_references(ROOT / "evals/fixtures/reference_queries.json", golden)
        self.db.execute("PRAGMA query_only = ON")
        for reference in references.values():
            self.db.execute(reference["sql"]).fetchall()
        rows = [dict(row) for row in self.db.execute(references["q01"]["sql"])]
        self.assertEqual(rows, [{"month": "2026-01", "location": "FR", "job_count": 1},
                                {"month": "2026-01", "location": "UK", "job_count": 1}])
        self.assertEqual(self.db.execute(references["q21"]["sql"]).fetchone()["average_tokens_complete_task_groups"], 50)
        self.assertEqual([row["prompt_version"] for row in self.db.execute(references["q25"]["sql"])], ["new", "old"])
        with self.assertRaises(sqlite3.OperationalError):
            self.db.execute("DELETE FROM jobs")

    def test_private_snapshot_is_existing_read_only_and_never_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                open_private_snapshot(missing)
            self.assertFalse(missing.exists())
            path = Path(directory) / "snapshot.db"
            with closing(sqlite3.connect(path)) as writer:
                with writer:
                    writer.execute("CREATE TABLE jobs (id INTEGER)")
                    writer.execute("INSERT INTO jobs VALUES (1)")
            before = path.read_bytes()
            with closing(open_private_snapshot(path)) as reader:
                self.assertEqual(reader.execute("SELECT id FROM jobs").fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("INSERT INTO jobs VALUES (2)")
                reader.execute("PRAGMA query_only = OFF")
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("DELETE FROM jobs")
            self.assertEqual(path.read_bytes(), before)

    def test_private_snapshot_rejects_wal_or_journal_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.db"
            with closing(sqlite3.connect(path)) as writer:
                writer.execute("CREATE TABLE jobs (id INTEGER)")
                writer.commit()
                writer.execute("PRAGMA journal_mode = WAL")
                with writer:
                    writer.execute("INSERT INTO jobs VALUES (1)")
                self.assertTrue(Path(str(path) + "-wal").exists())
                with self.assertRaisesRegex(ValueError, "frozen"):
                    with closing(open_private_snapshot(path)):
                        pass
            for suffix in ("-journal", "-shm"):
                sidecar = Path(str(path) + suffix)
                sidecar.write_bytes(b"synthetic sidecar")
                try:
                    with self.assertRaisesRegex(ValueError, "frozen"):
                        with closing(open_private_snapshot(path)):
                            pass
                finally:
                    sidecar.unlink()

    def test_private_pack_requires_current_contracts_and_matching_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory)
            database = pack / "evaluation.db"
            with closing(sqlite3.connect(database)) as writer:
                writer.execute("CREATE TABLE jobs (id INTEGER)")
            contracts = {}
            for name, relative in (("golden_questions", "evals/golden_questions.yaml"),
                                    ("indexing_cases", "evals/indexing_cases.yaml")):
                contracts[name + "_version"] = 8 if name == "golden_questions" else 5
                contracts[name + "_sha256"] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            contracts["reference_definition_sha256"] = hashlib.sha256(
                (ROOT / "evals/fixtures/reference_queries.json").read_bytes()).hexdigest()
            manifest = {"contracts": contracts, "reference_date": "2026-10-07",
                        "snapshot": {"path": "evaluation.db", "sha256": hashlib.sha256(database.read_bytes()).hexdigest()},
                        "artifacts": [{"name": "evaluation.db", "sha256": hashlib.sha256(database.read_bytes()).hexdigest()}]}
            def write_manifest() -> None:
                (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            write_manifest()
            with closing(open_private_pack(pack, ROOT)) as reader:
                self.assertEqual(reader.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
            contracts["golden_questions_version"] = 5
            write_manifest()
            with self.assertRaisesRegex(ValueError, "contract"):
                open_private_pack(pack, ROOT)
            contracts["golden_questions_version"] = 8
            manifest["artifacts"][0]["sha256"] = "0" * 64
            write_manifest()
            with self.assertRaisesRegex(ValueError, "hash"):
                open_private_pack(pack, ROOT)
            manifest["artifacts"][0]["name"] = "../outside.db"
            write_manifest()
            with self.assertRaisesRegex(ValueError, "outside"):
                open_private_pack(pack, ROOT)

    def test_reference_aggregations_boundaries_ties_and_follow_up(self) -> None:
        for identifier, country in ((1, "FR"), (2, "UK"), (3, "FR"), (4, "CH")):
            self.fixture.job(identifier, location=country, user_decision="DO_NOT_PURSUE")
        self.fixture.assessment(101, 1, primary_role_family="A", fit_score=8, priority_score=9,
                                red_flags=["Travel", "Travel"], sustainability_risks=["Weekly travel"],
                                material_mandate_dimensions=[{"id": "delivery", "description": "Build systems",
                                                            "importance": 8, "evidence_strength": "DIRECT"}])
        self.fixture.assessment(102, 2, primary_role_family="B", fit_score=10, priority_score=9,
                                tech_bar_fit=7, red_flags=["Travel"])
        self.fixture.assessment(103, 3, status="FAILED", fit_score=0, priority_score=0)
        self.fixture.call(1, job_id=1, total_tokens=20, duration_seconds=2)
        self.fixture.call(2, job_id=2, total_tokens=None, duration_seconds=4,
                          retry_number=1, status="FAILED", failure_category="timeout")
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        references = load_references(ROOT / "evals/fixtures/reference_queries.json", golden)
        def rows(question: str) -> list[dict]:
            return [dict(row) for row in self.db.execute(references[question]["sql"])]
        self.assertEqual([row["average_fit_score"] for row in rows("q02")], [8, 10])
        self.assertEqual([row["average_priority_score"] for row in rows("q03")], [9, 9])
        self.assertEqual([row["job_id"] for row in rows("q04")], [1])
        self.assertEqual([row["job_id"] for row in rows("q05")], [1, 2])
        self.assertEqual(rows("q07"), [{"exact_item": "Travel", "job_count": 2}])
        self.assertEqual(rows("q08"), [{"exact_item": "Weekly travel", "job_count": 2}])
        self.assertEqual(rows("q10")[0]["dimension_id"], "delivery")
        self.assertEqual(rows("q22")[0]["total_reported_tokens"], 20)
        self.assertEqual(rows("q22")[0]["total_duration_seconds"], 6)
        self.assertEqual(rows("q23")[0]["success_rate"], 0.5)
        self.assertEqual(rows("q23")[0]["missing_usage_calls"], 1)
        failures = next(row for row in rows("q24") if row["status"] == "FAILED")
        self.assertEqual((failures["retried_call_count"], failures["failure_category"]), (1, "timeout"))
        self.assertEqual({row["primary_role_family"]: row["total_reported_tokens"] for row in rows("q26")},
                         {"A": 20, "B": None})
        # q29 inherits q01's month grouping and adds FR; no new question meaning.
        assert_reference_rows(rows("q29"), [row for row in rows("q01") if row["location"] == "FR"])


class ServiceDoubleTest(unittest.TestCase):
    def test_embedding_is_reproducible_and_records_failures(self) -> None:
        first, second = EmbeddingDouble(), EmbeddingDouble()
        self.assertEqual(first.embed(["same"]), second.embed(["same"]))
        self.assertNotEqual(first.embed(["same"]), first.embed(["different"]))
        failed = EmbeddingDouble(error=RuntimeError("embedding unavailable"))
        with self.assertRaisesRegex(RuntimeError, "embedding unavailable"):
            failed.embed(["input"])
        self.assertEqual(failed.calls, [["input"]])

    def test_model_scripts_outputs_errors_and_exhaustion(self) -> None:
        model = ModelDouble([{"plan": ["structured_query"]}, RuntimeError("invalid output")])
        request = {"task": "planner", "prompt": "synthetic question"}
        self.assertEqual(model.invoke(request), {"plan": ["structured_query"]})
        request["task"] = "changed"
        self.assertEqual(model.calls[0]["task"], "planner")
        with self.assertRaisesRegex(RuntimeError, "invalid output"):
            model.invoke({"task": "planner"})
        with self.assertRaisesRegex(RuntimeError, "exhausted"):
            model.invoke({})

    def test_vector_double_records_operations_without_inventing_ranking(self) -> None:
        vector = VectorDouble(search_results=[[{"job_id": 1, "score": 0.8}]])
        vector.upsert([{"semantic_unit_id": "one", "job_id": 1}])
        self.assertEqual(vector.search([0.1], field_name="real_mandate"), [{"job_id": 1, "score": 0.8}])
        vector.delete(["one"])
        self.assertEqual(vector.records, {})
        self.assertEqual([call["operation"] for call in vector.calls], ["upsert", "search", "delete"])
        with self.assertRaisesRegex(RuntimeError, "exhausted"):
            vector.search([0.1])
        vector.failures["upsert"] = RuntimeError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            vector.upsert([{"semantic_unit_id": "two"}])
        self.assertEqual(vector.records, {})
