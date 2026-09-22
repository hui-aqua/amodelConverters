"""Unit tests for spreader heave RAO GUI controls and settings persistence."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import tempfile
import unittest

from PySide6.QtWidgets import QApplication

from sim2blender.gui.app import MainWindow

APP = QApplication.instance() or QApplication(sys.argv)


class SpreaderHeaveGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Sim2Blender_HeaveTest_")
        self.settings_path = Path(self.temp_dir.name) / "test_settings.ini"
        self.window = MainWindow(settings_path=self.settings_path)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp_dir.cleanup()

    def test_heave_rao_widget_defaults(self):
        """Verify the spreader Heave RAO spinbox exists with 0.50 default."""
        self.assertTrue(hasattr(self.window, "spreader_heave_rao"))
        self.assertAlmostEqual(self.window.spreader_heave_rao.value(), 0.50, places=2)
        self.assertEqual(self.window.spreader_heave_rao.minimum(), 0.0)
        self.assertEqual(self.window.spreader_heave_rao.maximum(), 2.0)
        self.assertEqual(self.window.spreader_heave_rao.decimals(), 2)

    def test_settings_save_and_load(self):
        """Custom Heave RAO should persist across application sessions."""
        self.window.spreader_heave_rao.setValue(0.75)
        self.window._save_current_settings()

        new_window = MainWindow(settings_path=self.settings_path)
        try:
            self.assertAlmostEqual(new_window.spreader_heave_rao.value(), 0.75, places=2)
        finally:
            new_window.close()
            new_window.deleteLater()
            APP.processEvents()


if __name__ == "__main__":
    unittest.main()
