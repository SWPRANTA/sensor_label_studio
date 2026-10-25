"""Focused regression checks for stale plotting imports; no datasets modified."""
import sys, unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plotting_loader import load_plotting, _REQUIRED


def source(color):
    lines = [name + " = None" for name in _REQUIRED if name != "LABEL_COLORS"]
    lines.append("LABEL_COLORS = {'Pothole': '" + color + "'}")
    return ("\n".join(lines) + "\n").encode()


class PlottingLoaderTests(unittest.TestCase):
    def test_ignores_old_plotting_module(self):
        old = ModuleType("plotting")
        old.GROUPS = []
        with patch.dict(sys.modules, {"plotting": old}):
            module = load_plotting(Path(__file__).resolve().parents[1])
            self.assertIn("Pothole", module.LABEL_COLORS)
            self.assertTrue(callable(module.label_intervals))
            self.assertIs(sys.modules["plotting"], old)

    def test_reuses_unchanged_source(self):
        with patch("plotting_loader.Path.read_bytes", return_value=source("#111111")):
            first = load_plotting(Path(__file__).resolve().parents[1])
            second = load_plotting(Path(__file__).resolve().parents[1])
            self.assertIs(first, second)

    def test_changed_source_refreshes_without_restarting(self):
        root = Path(__file__).resolve().parents[1]
        sentinel = ModuleType("csv_document")
        with patch.dict(sys.modules, {"csv_document": sentinel}):
            with patch("plotting_loader.Path.read_bytes", return_value=source("#222222")):
                first = load_plotting(root)
            with patch("plotting_loader.Path.read_bytes", return_value=source("#333333")):
                second = load_plotting(root)
            self.assertIsNot(first, second)
            self.assertEqual(second.LABEL_COLORS["Pothole"], "#333333")
            self.assertIs(sys.modules["csv_document"], sentinel)

    def test_actual_incomplete_file_reports_specific_error(self):
        with patch("plotting_loader.Path.read_bytes", return_value=b"GROUPS = []\n"):
            with self.assertRaisesRegex(ImportError, "missing:.*LABEL_COLORS"):
                load_plotting(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
