"""Execute approved reference facts against synthetic SQLite source records."""

import json
from pathlib import Path
import unittest

from support.contracts import load_suite, load_references
from support.sqlite_fixtures import SyntheticDatabase


ROOT = Path(__file__).resolve().parents[1]


class AssessmentTokenReferenceTest(unittest.TestCase):
    """Check q21 facts independently of generated SQL or model answers."""

    def setUp(self) -> None:
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        self.reference = load_references(ROOT / "evals/fixtures/reference_queries.json", golden)["q21"]
        self.fixture = SyntheticDatabase()
        self.addCleanup(self.fixture.close)
        self.database = self.fixture.connection

    def call(
        self, task_id: int | None, tokens: int | None, *, model: str | None = "actual",
        requested: str = "requested", attempt: int | None = 1, job: int = 1,
        status: str = "SUCCEEDED", retry: int = 0, operation: str = "ASSESSMENT",
        step: str = "assessment", cache_read: int = 0,
    ) -> None:
        if not self.database.execute("SELECT 1 FROM jobs WHERE id = ?", (job,)).fetchone():
            self.fixture.job(job)
        identifier = self.database.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM llm_calls").fetchone()[0]
        self.fixture.call(identifier, task_id=task_id, total_tokens=tokens, resolved_model=model,
                          requested_model=requested, task_attempt_id=attempt, job_id=job,
                          status=status, retry_number=retry, operation=operation,
                          pipeline_step=step, cache_read_input_tokens=cache_read)

    def results(self) -> dict[str | None, dict]:
        # Restrict execution after fixture setup; these are reference reads, not runtime safety tests.
        self.database.execute("PRAGMA query_only = ON")
        return {row["resolved_model"]: dict(row) for row in self.database.execute(self.reference["sql"])}

    def test_reference_is_exact_after_definition_approval(self) -> None:
        self.assertEqual(self.reference["status"], "exact_sql_reference")

    def test_tasks_include_all_attempts_steps_retries_and_failed_usage(self) -> None:
        self.call(1, 10, status="FAILED")
        self.call(1, 20, retry=1)
        self.call(1, 30, attempt=2, step="validation")
        self.call(2, 100, status="FAILED", job=1)
        row = self.results()["actual"]
        self.assertEqual(row["task_model_groups"], 2)
        self.assertEqual(row["call_count"], 4)
        self.assertEqual(row["reported_tokens"], 160)
        self.assertEqual(row["average_tokens_complete_task_groups"], 80)

    def test_resolved_models_have_independent_contributing_task_denominators(self) -> None:
        self.call(1, 10, model="small")
        self.call(1, 30, model="strong", retry=1)
        self.call(2, 20, model="small")
        rows = self.results()
        self.assertEqual(set(rows), {"small", "strong"})
        self.assertEqual(rows["small"]["task_model_groups"], 2)
        self.assertEqual(rows["small"]["average_tokens_complete_task_groups"], 15)
        self.assertEqual(rows["strong"]["task_model_groups"], 1)
        self.assertEqual(rows["strong"]["average_tokens_complete_task_groups"], 30)

    def test_missing_task_ids_are_separate_call_coverage_not_invented_tasks(self) -> None:
        self.call(1, 20)
        self.call(None, 100, attempt=None)
        self.call(None, 200, attempt=None, job=2)
        row = self.results()["actual"]
        self.assertEqual(row["task_model_groups"], 1)
        self.assertEqual(row["average_tokens_complete_task_groups"], 20)
        self.assertEqual(row["unassigned_calls"], 2)
        self.assertEqual(row["unassigned_reported_usage_calls"], 2)
        self.assertEqual(row["unassigned_reported_tokens"], 300)
        self.assertEqual(row["reported_tokens"], 320)

    def test_only_unassigned_calls_have_no_task_mean(self) -> None:
        self.call(None, 10, attempt=None)
        self.call(None, None, attempt=None)
        row = self.results()["actual"]
        self.assertEqual(row["task_model_groups"], 0)
        self.assertEqual(row["complete_usage_task_groups"], 0)
        self.assertEqual(row["incomplete_usage_task_groups"], 0)
        self.assertEqual(row["unassigned_calls"], 2)
        self.assertEqual(row["unassigned_reported_usage_calls"], 1)
        self.assertIsNone(row["average_tokens_complete_task_groups"])

    def test_null_usage_excludes_only_incomplete_model_slices_and_preserves_zero(self) -> None:
        self.call(1, 40)
        self.call(1, None, retry=1)
        self.call(2, 0)
        self.call(3, 20)
        self.call(1, 50, model="other")
        rows = self.results()
        row = rows["actual"]
        self.assertEqual(row["task_model_groups"], 3)
        self.assertEqual(row["complete_usage_task_groups"], 2)
        self.assertEqual(row["incomplete_usage_task_groups"], 1)
        self.assertEqual(row["average_tokens_complete_task_groups"], 10)
        self.assertEqual(row["reported_tokens"], 60)
        self.assertEqual(row["reported_usage_calls"], 3)
        self.assertEqual(row["missing_usage_calls"], 1)
        self.assertEqual(rows["other"]["average_tokens_complete_task_groups"], 50)

    def test_all_unreported_usage_has_no_total_or_mean(self) -> None:
        self.call(1, None)
        row = self.results()["actual"]
        self.assertEqual(row["complete_usage_task_groups"], 0)
        self.assertEqual(row["incomplete_usage_task_groups"], 1)
        self.assertIsNone(row["reported_tokens"])
        self.assertIsNone(row["average_tokens_complete_task_groups"])

    def test_unknown_resolved_model_stays_unknown_even_with_requested_model(self) -> None:
        self.call(1, 10, model=None)
        self.call(None, 20, model=None, attempt=None)
        rows = self.results()
        self.assertEqual(set(rows), {None})
        self.assertEqual(rows[None]["average_tokens_complete_task_groups"], 10)
        self.assertEqual(rows[None]["unassigned_calls"], 1)

    def test_other_operations_are_excluded_and_cache_usage_is_not_added_again(self) -> None:
        self.call(1, 20, cache_read=15)
        self.call(1, 500, operation="CV_GENERATION")
        row = self.results()["actual"]
        self.assertEqual(row["call_count"], 1)
        self.assertEqual(row["reported_tokens"], 20)
        self.assertEqual(row["average_tokens_complete_task_groups"], 20)

    def test_no_assessment_calls_produces_no_model_groups(self) -> None:
        self.call(1, 500, operation="CV_GENERATION")
        self.assertEqual(self.results(), {})


class ApplicationReferenceTest(unittest.TestCase):
    """Check q18 seeds and q19 evidence without a profile or semantic service."""

    def setUp(self) -> None:
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        self.references = load_references(ROOT / "evals/fixtures/reference_queries.json", golden)
        self.fixture = SyntheticDatabase()
        self.addCleanup(self.fixture.close)
        self.database = self.fixture.connection

    def job(self, identifier: int, stage: str | None = None, *, human_decision: str = "UNDECIDED") -> None:
        self.fixture.job(identifier, application_status=stage, user_decision=human_decision)

    def assessment(
        self, job: int, *, status: str = "ASSESSED", decision: str = "NO_GO",
        technical: int | None = 8, seniority: int | None = 5,
        reason: str | None = "Frequent travel", flags: str | None = '["Travel"]',
        risks: str | None = '["Weekly travel"]',
    ) -> None:
        self.fixture.assessment(100 + job, job, status=status, decision=decision,
                                tech_bar_fit=technical, seniority_fit=seniority,
                                decision_reason=reason, red_flags=flags, sustainability_risks=risks)

    def results(self, question: str) -> dict[int, dict]:
        self.database.execute("PRAGMA query_only = ON")
        return {row["job_id"]: dict(row) for row in self.database.execute(self.references[question]["sql"])}

    def test_q18_selects_all_current_rounds_without_inventing_history(self) -> None:
        stages = ["1st round", "2nd round", "3rd round", "4th round", "Applied", "Rejected", None,
                  "Interview", "2nd round "]
        for identifier, stage in enumerate(stages, 1):
            self.job(identifier, stage)
            self.assessment(identifier)
        rows = self.results("q18")
        self.assertEqual(set(rows), {1, 2, 3, 4})
        self.assertEqual(rows[2]["application_status"], "2nd round")
        self.assertEqual(rows[2]["seniority_fit"], 5)

    def test_q18_preserves_seeds_without_usable_assessments_or_scores(self) -> None:
        for identifier in range(1, 5):
            self.job(identifier, "1st round")
        self.assessment(2, status="FAILED")
        self.assessment(3, status="RUNNING")
        self.assessment(4, seniority=None)
        rows = self.results("q18")
        self.assertEqual(set(rows), {1, 2, 3, 4})
        for identifier in (1, 2, 3):
            self.assertIsNone(rows[identifier]["assessment_id"])
            self.assertIsNone(rows[identifier]["seniority_fit"])
        self.assertEqual(rows[4]["assessment_id"], 104)
        self.assertIsNone(rows[4]["seniority_fit"])
        self.assertEqual(rows[1]["job_description"], "Build data tools")

    def test_q19_uses_inclusive_technical_threshold_and_model_decision(self) -> None:
        for identifier in range(1, 6):
            self.job(identifier, human_decision="DO_NOT_PURSUE" if identifier == 3 else "PURSUE")
        self.assessment(1, technical=8)
        self.assessment(2, technical=7)
        self.assessment(3, decision="GO", technical=10)
        self.assessment(4, technical=10)
        self.assessment(5, technical=None)
        rows = self.results("q19")
        self.assertEqual(set(rows), {1, 4})
        self.assertEqual(rows[1]["tech_bar_fit"], 8)
        self.assertEqual(rows[1]["decision"], "NO_GO")

    def test_q19_excludes_unusable_assessments_and_keeps_documented_evidence(self) -> None:
        for identifier, status in enumerate(("PENDING", "RUNNING", "FAILED", "ASSESSED"), 1):
            self.job(identifier)
            self.assessment(identifier, status=status)
        rows = self.results("q19")
        self.assertEqual(set(rows), {4})
        self.assertEqual(rows[4]["decision_reason"], "Frequent travel")
        self.assertEqual(json.loads(rows[4]["red_flags"]), ["Travel"])
        self.assertEqual(json.loads(rows[4]["sustainability_risks"]), ["Weekly travel"])

    def test_q19_high_technical_fit_does_not_establish_nontechnical_reasons(self) -> None:
        self.job(1)
        self.assessment(1, reason="Technical evidence is insufficient", flags='["Technical evidence gap"]', risks="[]")
        self.job(2)
        self.assessment(2, reason=None, flags=None, risks=None)
        rows = self.results("q19")
        self.assertEqual(set(rows), {1, 2})
        self.assertEqual(rows[1]["decision_reason"], "Technical evidence is insufficient")
        self.assertIsNone(rows[2]["decision_reason"])
        self.assertIsNone(rows[2]["sustainability_risks"])


class QuestionScopeTest(unittest.TestCase):
    """Preserve stable question IDs when the owner removes a capability."""

    def test_q06_is_removed_without_renumbering_remaining_questions(self) -> None:
        golden = load_suite(ROOT / "evals/golden_questions.yaml", "questions")
        identifiers = set(golden.by_id)
        self.assertEqual(identifiers, {f"q{number:02}" for number in range(1, 31)} - {"q06"})


if __name__ == "__main__":
    unittest.main()
