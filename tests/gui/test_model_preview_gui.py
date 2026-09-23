"""Unit tests for GUI Model & Color Check button and preview integration."""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from sim2blender.gui.app import MainWindow


APP = QApplication.instance() or QApplication([])


def until(predicate, timeout=10):
    import time
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for Qt operation")
        QTest.qWait(20)


class TestModelPreviewGui(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Sim2Blender_Preview_GUI_")
        self.folder = Path(self.temp_dir.name)
        self.window = MainWindow(self.folder / "settings.ini")

    def tearDown(self):
        if self.window.running:
            self.window.cancel()
        until(lambda: not self.window.workers)
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.temp_dir.cleanup()

    def test_check_models_button_exists_and_styled(self):
        """Verify the Check Models button exists with correct text, name, and tooltip."""
        btn = self.window.check_models_button
        self.assertIsNotNone(btn)
        self.assertIn("Check Model in Blender", btn.text())
        self.assertEqual(btn.objectName(), "CheckModels")
        self.assertIn("preview", btn.toolTip().lower())

    def test_button_state_updates_with_model(self):
        """Verify check_models_button enables when a model is selected."""
        model_path = Path(__file__).resolve().parents[2] / "examples" / "models" / "winch_cage.amodel"
        self.window.model.setText(str(model_path))
        self.window.update_check_models_button_state()
        self.assertTrue(self.window.check_models_button.isEnabled())

    def test_feeding_camera_body_gui_controls(self):
        """Verify feeding camera body housing GUI controls and extra OBJ removal."""
        self.assertTrue(hasattr(self.window, "feedcam_show_body"))
        self.assertTrue(self.window.feedcam_show_body.isChecked())
        self.assertTrue(hasattr(self.window, "feedcam_model_edit"))
        self.assertIn("camera.obj", self.window.feedcam_model_edit.text())
        self.assertEqual(self.window.get_extra_obj_models(), [])

        # Toggling feedcam_show_body updates model line edit
        self.window.feedcam_show_body.setChecked(False)
        self.assertFalse(self.window.feedcam_model_edit.isEnabled())
        self.window.feedcam_show_body.setChecked(True)
        self.assertTrue(self.window.feedcam_model_edit.isEnabled())

    @patch("PySide6.QtCore.QProcess.startDetached")
    def test_check_models_preview_launches_detached_blender(self, mock_start):
        """Verify check_models_preview writes config and launches detached Blender."""
        mock_start.return_value = (True, 12345)

        model_path = Path(__file__).resolve().parents[2] / "examples" / "models" / "winch_cage.amodel"
        self.window.model.setText(str(model_path))
        self.window.blender.setText("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")

        # Mock blender executable validation
        with patch("pathlib.Path.is_file", return_value=True):
            self.window.check_models_preview()

        # Check that startDetached was called
        self.assertTrue(mock_start.called)
        call_args = mock_start.call_args[0]
        args_list = call_args[1]

        # Verify blender_model_preview.py and --config are in arguments
        self.assertTrue(any("blender_model_preview.py" in str(arg) for arg in args_list))
        self.assertIn("--config", args_list)

        # Check log output
        log_text = self.window.log.toPlainText()
        self.assertIn("3D MODEL PRE-BUILD CHECK & PREVIEW", log_text)
        self.assertIn("winch_cage.amodel", log_text)

    def test_app_icon_configured(self):
        """Verify the window and application icon is configured from AKVAgroup fish icon asset."""
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertFalse(APP.windowIcon().isNull())

    def test_start_build_incorporates_checked_blend(self):
        """Verify start_build detects .checked.blend and passes it to PipelineJob."""
        model_path = Path(__file__).resolve().parents[2] / "examples" / "models" / "winch_cage.amodel"
        self.window.model.setText(str(model_path))
        until(lambda: self.window.info is not None)
        until(lambda: not self.window.workers)

        out_blend = self.folder / "scene_output.blend"
        checked_blend = self.folder / "scene_output.checked.blend"
        checked_blend.write_text("dummy blend content", encoding="utf-8")
        self.window.output.setText(str(out_blend))

        self.window.process.start = MagicMock()
        self.window.start_build()
        self.window.running = False
        if self.window.log_file:
            self.window.log_file.close()
            self.window.log_file = None
        self.assertIsNotNone(self.window.job)
        self.assertEqual(Path(self.window.job.checked_blend_path).resolve(), checked_blend.resolve())
        self.assertIn("Incorporating calibrated models & materials", self.window.log.toPlainText())


if __name__ == "__main__":
    unittest.main()

