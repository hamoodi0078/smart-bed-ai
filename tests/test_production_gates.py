"""Production fail-fast gates (audit §6: validate_production_secrets never blocked)."""

from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch


class EnforceProductionSecretsTests(unittest.TestCase):
    def test_dev_returns_warnings_without_raising(self):
        settings_module = importlib.import_module("config.settings")

        with patch.dict(os.environ, {"DANAH_ENV": "development"}, clear=False):
            with patch.object(
                settings_module, "validate_production_secrets", return_value=["X missing"]
            ):
                self.assertEqual(settings_module.enforce_production_secrets(), ["X missing"])

    def test_production_raises_on_warnings(self):
        settings_module = importlib.import_module("config.settings")

        with patch.dict(os.environ, {"DANAH_ENV": "production"}, clear=False):
            with patch.object(
                settings_module, "validate_production_secrets", return_value=["X missing"]
            ):
                with self.assertRaises(RuntimeError):
                    settings_module.enforce_production_secrets()

    def test_production_clean_boot_returns_empty(self):
        settings_module = importlib.import_module("config.settings")

        with patch.dict(os.environ, {"DANAH_ENV": "production"}, clear=False):
            with patch.object(settings_module, "validate_production_secrets", return_value=[]):
                self.assertEqual(settings_module.enforce_production_secrets(), [])


if __name__ == "__main__":
    unittest.main()
