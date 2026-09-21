"""Asynchronous background inspectors for AquaSim model and results files."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QThread, Signal

from sim2blender.gui.model_job import inspect_model
from sim2blender.io.aquasim.results import inspect_results


class Inspector(QThread):
    """Background inspection thread for AquaSim .amodel files."""
    result = Signal(int, object, str)

    def __init__(self, path: str | Path, token: int, parent=None):
        super().__init__(parent)
        self.path, self.token = path, token

    def run(self):
        try:
            self.result.emit(self.token, inspect_model(self.path), '')
        except Exception as exc:
            self.result.emit(self.token, None, str(exc))


class ResultsInspector(Inspector):
    """Background inspection thread for AquaSim results out.txt files."""
    def run(self):
        try:
            before = Path(self.path).stat()
            info = inspect_results(self.path, self.isInterruptionRequested)
            after = Path(self.path).stat()
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise ValueError('Results file changed during inspection; select it again when export finishes.')
            info['stamp'] = (after.st_mtime_ns, after.st_size)
            self.result.emit(self.token, info, '')
        except Exception as exc:
            self.result.emit(self.token, None, str(exc))
