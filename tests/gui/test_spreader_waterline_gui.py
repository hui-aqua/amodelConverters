"""Unit tests for spreader waterline GUI controls and settings persistence."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import tempfile
import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from sim2blender.gui.app import MainWindow
from sim2blender.core.paths import PROJECT_ROOT

APP = QApplication.instance() or QApplication(sys.argv)


class SpreaderWaterlineGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Sim2Blender_Test_")
        self.settings_path = Path(self.temp_dir.name) / "test_settings.ini"
        self.window = MainWindow(settings_path=self.settings_path)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp_dir.cleanup()

    def test_spreader_z_offset_widget_defaults(self):
        """Verify the spreader Z lift spinbox exists with 0.52m default."""
        self.assertTrue(hasattr(self.window, "spreader_z_offset"))
        self.assertEqual(self.window.spreader_z_offset.suffix(), " m")
        self.assertAlmostEqual(self.window.spreader_z_offset.value(), 0.52, places=3)
        self.assertEqual(self.window.spreader_z_offset.decimals(), 3)

    def test_preset_changes_waterline_offset(self):
        """Selecting different presets should update the waterline offset from config.json."""
        combo = self.window.spreader_preset_combo
        default_idx = -1
        wb_idx = -1
        for i in range(combo.count()):
            text = combo.itemText(i)
            if "Default" in text:
                default_idx = i
            elif "WB" in text:
                wb_idx = i

        self.assertNotEqual(default_idx, -1)
        self.assertNotEqual(wb_idx, -1)

        # Switch to WB preset
        combo.setCurrentIndex(wb_idx)
        self.assertAlmostEqual(self.window.spreader_z_offset.value(), 0.0, places=3)

        # Switch back to Default preset
        combo.setCurrentIndex(default_idx)
        self.assertAlmostEqual(self.window.spreader_z_offset.value(), 0.52, places=3)

    def test_settings_save_and_load(self):
        """Custom spreader waterline offset should persist across application sessions."""
        self.window.spreader_z_offset.setValue(0.735)
        self.window._save_current_settings()

        # Create new window loading from the same settings file
        new_window = MainWindow(settings_path=self.settings_path)
        try:
            self.assertAlmostEqual(new_window.spreader_z_offset.value(), 0.735, places=3)
        finally:
            new_window.close()
            new_window.deleteLater()
            APP.processEvents()

    def test_visualize_button_exists(self):
        """Verify the 'Visualize in Blender' button is wired up."""
        self.assertTrue(hasattr(self.window, "btn_visualize_waterline"))
        self.assertIn("Visualize in Blender", self.window.btn_visualize_waterline.text())


if __name__ == "__main__":
    unittest.main()
