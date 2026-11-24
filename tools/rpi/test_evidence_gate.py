"""Tests for RPI evidence gate; standard library only."""
import unittest
from evidence_gate import validate

def valid_record():
    return {
        "workflow": "RPI", "project": "demo", "change_id": "T-1",
        "title": "Sample change", "depth": "quick", "status": "plan",
        "risk_level": "low",
        "research": {"findings": ["Inspected route"], "assumptions": [],
                     "unknowns": [], "evidence": ["app.py route inspected"]},
        "plan": {"scope": ["Change one handler"], "out_of_scope": [],
                 "acceptance_criteria": ["Response is 200"], "risks": ["Regression"],
                 "test_strategy": ["Unit test"], "rollback": "Revert commit",
                 "approval": "not_required"},
        "implementation": {"changed_files": [], "tests": [], "review": "",
                         "deployment": "not_requested",
                         "post_deploy_verification": []}
    }

class EvidenceGateTests(unittest.TestCase):
    def test_valid_research_and_plan_record(self):
        self.assertEqual(validate(valid_record()), [])

    def test_missing_research_evidence_fails(self):
        record = valid_record()
        record["research"]["evidence"] = []
        self.assertTrue(any("research.evidence" in e for e in validate(record)))

    def test_missing_acceptance_criteria_fails(self):
        record = valid_record()
        record["plan"]["acceptance_criteria"] = []
        self.assertTrue(any("acceptance_criteria" in e for e in validate(record)))

    def test_implement_status_requires_files_tests_and_review(self):
        record = valid_record()
        record["status"] = "implement"
        errors = validate(record)
        self.assertTrue(any("changed_files" in e for e in errors))
        self.assertTrue(any("tests" in e for e in errors))
        self.assertTrue(any("review" in e for e in errors))

    def test_complete_success_requires_verification(self):
        record = valid_record()
        record["status"] = "complete"
        record["implementation"].update({
            "changed_files": ["app.py"], "tests": ["unit tests passed"],
            "review": "diff reviewed", "deployment": "succeeded",
            "post_deploy_verification": []
        })
        self.assertTrue(any("post-deploy verification" in e for e in validate(record)))

if __name__ == "__main__":
    unittest.main()
