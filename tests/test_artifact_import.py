import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.paths import all_catalog_paths, catalog_rel_path
from scripts.import_catalog_artifacts import copy_catalog_artifacts
from scripts.replay_publish_pipeline import copy_catalog_artifacts as replay_import


class ArtifactImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.artifacts = root / "artifacts"
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.stores = all_catalog_paths()
        for country, store, _ in self.stores:
            artifact = self.artifacts / f"catalog-{country}-{store}"
            catalog = artifact / catalog_rel_path(country, store)
            status = artifact / "reports/scrape-status" / f"{country}-{store}.json"
            catalog.parent.mkdir(parents=True)
            status.parent.mkdir(parents=True)
            catalog.write_text(json.dumps([{"name": store}]))
            status.write_text(json.dumps({"country": country, "store": store}))
        country, store, _ = self.stores[0]
        self.artifact = self.artifacts / f"catalog-{country}-{store}"
        self.relative = Path(catalog_rel_path(country, store))

    def test_complete_batch_and_replay_share_importer(self):
        self.assertIs(replay_import, copy_catalog_artifacts)
        self.assertEqual(copy_catalog_artifacts(self.artifacts, self.workspace), len(self.stores))
        for country, store, _ in self.stores:
            self.assertTrue((self.workspace / catalog_rel_path(country, store)).is_file())
            self.assertTrue((self.workspace / "reports/scrape-status" / f"{country}-{store}.json").is_file())

    def test_executable_payload_rejected_without_partial_import(self):
        injected = self.artifact / "scripts/validate_products.py"
        injected.parent.mkdir()
        injected.write_text("raise SystemExit('injected')")
        with self.assertRaisesRegex(ValueError, "Unexpected artifact entry"):
            copy_catalog_artifacts(self.artifacts, self.workspace)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_missing_late_artifact_does_not_partially_import(self):
        country, store, _ = self.stores[-1]
        (self.artifacts / f"catalog-{country}-{store}" / catalog_rel_path(country, store)).unlink()
        with self.assertRaisesRegex(ValueError, "Missing artifact file"):
            copy_catalog_artifacts(self.artifacts, self.workspace)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_invalid_json_and_shapes_are_rejected(self):
        source = self.artifact / self.relative
        for payload in ['not JSON', '{}', 'null']:
            source.write_text(payload)
            with self.assertRaises(ValueError):
                copy_catalog_artifacts(self.artifacts, self.workspace)
            self.assertEqual(list(self.workspace.iterdir()), [])

    def test_source_symlink_rejected(self):
        source = self.artifact / self.relative
        source.unlink()
        source.symlink_to(self.artifact / "reports")
        with self.assertRaisesRegex(ValueError, "Unexpected artifact entry"):
            copy_catalog_artifacts(self.artifacts, self.workspace)

    def test_destination_symlink_rejected(self):
        outside = self.workspace.parent / "outside"
        outside.mkdir()
        (self.workspace / "countries").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            copy_catalog_artifacts(self.artifacts, self.workspace)
        self.assertEqual(list(outside.iterdir()), [])

    def test_oversized_payload_rejected(self):
        with patch('scripts.import_catalog_artifacts.MAX_FILE_BYTES', 1):
            with self.assertRaisesRegex(ValueError, "Oversized"):
                copy_catalog_artifacts(self.artifacts, self.workspace)


if __name__ == "__main__":
    unittest.main()
