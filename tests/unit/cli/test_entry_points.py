"""Canonical and compatibility launchers route to the same implementation."""
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from sim2blender.cli.blender_entry import main,WORKFLOWS


class EntryPointTests(unittest.TestCase):
    def test_workflow_dispatch(self):
        for command,module in WORKFLOWS.items():
            workflow=Mock()
            with patch('importlib.import_module',return_value=workflow) as loader:
                main([command,'a path with spaces','--fps','25'])
            loader.assert_called_once_with('sim2blender.workflows.'+module)
            workflow.main.assert_called_once_with(['a path with spaces','--fps','25'])

    def test_old_and_new_launchers(self):
        root = Path(__file__).resolve().parents[3]
        for relative in ('scripts/run_workflow.py', 'launchers/cli/run_workflow.py'):
            self.assertIs(runpy.run_path(str(root / relative))['main'], main)
        from sim2blender.gui.app import main as gui_main
        self.assertTrue(callable(gui_main))


if __name__=='__main__':unittest.main()
