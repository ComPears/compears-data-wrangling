import ssl
import unittest
from pathlib import Path
from unittest.mock import patch

import certifi
from scripts.verify_secure_runtime import node_is_patched
from tls_context import scraper_ssl_context

ROOT = Path(__file__).resolve().parents[1]


class RuntimeSecurityTests(unittest.TestCase):
    def test_node_security_floor(self):
        for version in ("v22.23.4", "v22.24.0", "v24.22.1", "v26.12.1"):
            self.assertTrue(node_is_patched(version))
        for version in ("v20.20.0", "v22.23.3", "v24.22.0", "v26.12.0", "v25.9.0"):
            self.assertFalse(node_is_patched(version))
        with self.assertRaises(ValueError):
            node_is_patched("v22.23.4-rc.1")

    def test_tls_uses_only_explicit_certifi_bundle_and_keeps_verification(self):
        scraper_ssl_context.cache_clear()
        with patch("tls_context.ssl.create_default_context", wraps=ssl.create_default_context) as factory:
            context = scraper_ssl_context()
            factory.assert_called_once_with(cafile=certifi.where())
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        subjects = [str(cert["subject"]) for cert in context.get_ca_certs()]
        self.assertFalse(any("emSign ECC Root CA - G3" in subject for subject in subjects))

    def test_all_python_workflows_use_shared_secure_setup(self):
        for name in ("ci.yml", "verify_plus.yaml", "verify_tesco.yaml", "update_stores.yaml"):
            workflow = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("uses: ./.github/actions/setup-secure-runtime", workflow)
            self.assertNotIn("uses: actions/setup-python", workflow)
            self.assertNotIn("pip install -r requirements.txt", workflow)
            if "pip install" in workflow:
                self.assertLess(workflow.index("uses: ./.github/actions/setup-secure-runtime"), workflow.index("pip install"))
        action = (ROOT / ".github/actions/setup-secure-runtime/action.yml").read_text()
        self.assertIn("node-version: '22.23.4'", action)
        self.assertIn("python-version: '3.12.15'", action)
        self.assertIn("PLAYWRIGHT_NODEJS_PATH", action)
        self.assertIn("bootstrap-python.sh", action)
        self.assertIn("verify_secure_runtime.py", action)
        self.assertIn("emSign_ECC_Root_CA_-_G3.crt", action)
        self.assertLess(action.index("update-ca-certificates"), action.index("uses: actions/setup-node"))

    def test_bootstrap_is_integrity_pinned_before_dependency_install(self):
        script = (ROOT / "scripts/bootstrap-python.sh").read_text()
        self.assertIn("sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70", script)
        self.assertLess(script.index("pip-26.2.2"), script.index("requirements.txt"))
        self.assertIn("PIP_USE_DEPRECATED=legacy-certs", script)
        self.assertIn('env -u PIP_USE_DEPRECATED "$PYTHON" -m pip install', script)


if __name__ == "__main__":
    unittest.main()
