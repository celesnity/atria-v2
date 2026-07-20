"""Contract checks for the SDK-free module-template runtime."""

from pathlib import Path
import unittest


MODULE_ROOT = Path(__file__).resolve().parents[1]


class StaticHostContractTests(unittest.TestCase):
    """Verify the runtime remains a federation-only static host."""

    def test_runtime_has_no_python_connector_or_worker(self) -> None:
        dockerfile = (MODULE_ROOT / "backend" / "Dockerfile").read_text()
        compose = (MODULE_ROOT / "docker-compose.yml").read_text()
        nginx_config = (MODULE_ROOT / "nginx.conf").read_text()

        self.assertIn("FROM nginx", dockerfile)
        self.assertNotIn("minder_python_sdk", dockerfile)
        self.assertNotIn("python:3", dockerfile)
        self.assertNotIn("module-template-worker", compose)
        self.assertIn("/dashboard/", nginx_config)
        self.assertIn("Access-Control-Allow-Origin", nginx_config)
        self.assertIn('"mode":"ui-only"', nginx_config)


if __name__ == "__main__":
    unittest.main()
