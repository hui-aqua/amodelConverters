"""Unit tests for fish tail motion GUI controls, QSettings persistence, and schooling dict configuration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import tempfile
import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from sim2blender.gui.app import MainWindow

APP = QApplication.instance() or QApplication(sys.argv)


class FishTailGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Sim2Blender_FishTest_")
        self.settings_path = Path(self.temp_dir.name) / "test_settings.ini"
        self.window = MainWindow(settings_path=self.settings_path)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp_dir.cleanup()

    def test_tail_motion_widgets_exist_with_defaults(self):
        """Verify tail motion checkbox, amplitude and frequency spinboxes exist with defaults."""
        self.assertTrue(hasattr(self.window, "fish_tail_motion"))
        self.assertTrue(hasattr(self.window, "fish_tail_amplitude"))
        self.assertTrue(hasattr(self.window, "fish_tail_frequency"))

        self.assertTrue(self.window.fish_tail_motion.isChecked())
        self.assertAlmostEqual(self.window.fish_tail_amplitude.value(), 0.065, places=3)
        self.assertEqual(self.window.fish_tail_amplitude.suffix(), " m")
        self.assertAlmostEqual(self.window.fish_tail_frequency.value(), 2.2, places=2)
        self.assertEqual(self.window.fish_tail_frequency.suffix(), " Hz")

    def test_settings_save_and_load(self):
        """Verify tail motion parameters persist in QSettings across sessions."""
        self.window.fish_tail_motion.setChecked(False)
        self.window.fish_tail_amplitude.setValue(0.09)
        self.window.fish_tail_frequency.setValue(3.1)
        self.window._save_current_settings()

        # Open a new window reading the saved settings file
        window2 = MainWindow(settings_path=self.settings_path)
        try:
            self.assertFalse(window2.fish_tail_motion.isChecked())
            self.assertAlmostEqual(window2.fish_tail_amplitude.value(), 0.09, places=3)
            self.assertAlmostEqual(window2.fish_tail_frequency.value(), 3.1, places=2)
        finally:
            window2.close()
            window2.deleteLater()
            APP.processEvents()


if __name__ == "__main__":
    unittest.main()
