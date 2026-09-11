import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock


# DE and UK use similarly named shared modules, so load this module explicitly.
PATH = Path(__file__).resolve().parents[1] / "countries/de/_shared/de_scrape.py"
SPEC = importlib.util.spec_from_file_location("de_location_logging", PATH)


class LocationLoggingTests(unittest.TestCase):
    def test_location_values_are_not_logged_with_or_without_confirmation(self):
        import sys
        module = importlib.util.module_from_spec(SPEC)
        sys.modules[SPEC.name] = module
        SPEC.loader.exec_module(module)
        for confirmed in (True, False):
            with self.subTest(confirmed=confirmed):
                page = MagicMock()
                box = MagicMock()
                button = MagicMock()
                box.count.return_value = 1
                box.is_visible.return_value = True
                button.count.return_value = int(confirmed)
                button.is_visible.return_value = confirmed
                page.locator.side_effect = lambda selector: MagicMock(first=box if selector.startswith("input") else button)
                output = io.StringIO()
                with redirect_stdout(output):
                    module.maybe_set_de_zip(page, zip_code="PRIVATE-POSTCODE")
                box.fill.assert_called_with("PRIVATE-POSTCODE")
                self.assertNotIn("PRIVATE-POSTCODE", output.getvalue())
                self.assertIn("Store location", output.getvalue())


if __name__ == "__main__":
    unittest.main()
