import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_ignored_quality_report_is_force_added_for_publish(self):
        ignored_paths = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        workflow = (ROOT / ".github/workflows/update_stores.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("data-quality-report.json", ignored_paths)
        self.assertIn("git add -f data-quality-report.json", workflow)


if __name__ == "__main__":
    unittest.main()
