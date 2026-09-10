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

    def test_bot_sensitive_uk_stores_use_headed_chrome_under_xvfb(self):
        workflow = (ROOT / ".github/workflows/update_stores.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("matrix.store == 'tesco' || matrix.store == 'sainsburys'", workflow)
        self.assertIn("PLAYWRIGHT_HEADED:", workflow)
        self.assertIn("runner=(xvfb-run -a)", workflow)


if __name__ == "__main__":
    unittest.main()
