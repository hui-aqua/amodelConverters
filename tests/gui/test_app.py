"""Offscreen Qt tests including an actual small Blender build when available."""
import os
import json
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from sim2blender.gui.app import MainWindow
from sim2blender.gui.model_job import find_blender,ModelJob


APP=QApplication.instance() or QApplication([])


def until(predicate,timeout=30):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('Timed out waiting for Qt operation')
        QTest.qWait(20)


class GuiTests(unittest.TestCase):
    def setup_replay(self):
        points=[(x,y,z) for z in (-2,2) for y in (-2,2) for x in (-2,2)]
        faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
        nodes=''.join(f'<node id="{i+100}" x="{p[0]}" y="{p[1]}" z="{p[2]}"/>' for i,p in enumerate(points))
        elements=['<element id="{}" {}/>'.format(i,' '.join(f'node{a}="{n+100}"' for a,n in zip('ABCD',face))) for i,face in enumerate(faces)]
        model=self.folder/'Replay cage.amodel'
        model.write_text(f'<model><Nodes>{nodes}</Nodes><Components><membrane id="1" name="Enclosing net" active="true"><elements>{"".join(elements)}</elements></membrane><membrane id="2" name="Extra sheet" active="true"><elements>{elements[0]}</elements></membrane></Components></model>')
        results=self.folder/'motion out.txt'
        results.write_text('Time [-] VID [-] X Y Z\n'+''.join(f'{t} {i+1} {p[0]} {p[1]} {p[2]+t*.1}\n' for t in range(3) for i,p in enumerate(points)))
        self.window.model.setText(str(model));until(lambda:self.window.info is not None)
        until(lambda:not self.window.workers)
        self.window.workflow.setCurrentIndex(1);self.window.results.setText(str(results))
        until(lambda:self.window.results_info is not None)
        until(lambda:not self.window.workers)
        self.window.output.setText(str(self.folder/'GUI replay.blend'))
        self.window.components.item(1).setCheckState(Qt.CheckState.Unchecked)
        self.window.blender.setText(find_blender())

    def test_real_replay_with_and_without_salmon(self):
        if not find_blender():self.skipTest('Blender is not installed')
        self.setup_replay()
        self.assertEqual(self.window.results_info['samples'],3)
        self.assertIn('Structural motion time: 0.25 s',self.window.timing_summary.text())
        self.window.wave_period.setValue(6)
        self.assertIn('Structural motion time: 0.3 s',self.window.timing_summary.text())
        self.assertIn('Video / fish frames: 9',self.window.timing_summary.text())
        self.assertFalse(self.window.pins.isVisible())
        self.assertFalse(self.window.frames.isVisible())
        self.assertTrue(self.window.build_button.isEnabled())
        self.window.start_build();until(lambda:not self.window.running,60)
        self.assertIsNotNone(self.window.last_output,self.window.log.toPlainText())
        fish=json.loads(self.window.last_output.with_suffix('.fish.json').read_text())
        self.assertEqual(fish['fish_count'],2)
        self.assertEqual(fish['frames'],9)
        self.assertAlmostEqual(fish['duration_seconds'],.3)
        self.assertAlmostEqual(fish['structural_step_seconds'],.15)
        self.assertEqual(fish['video_fps'],25)
        replay=json.loads(self.window.last_output.with_suffix('.replay.json').read_text())
        self.assertEqual(replay['objects'],2)  # Extra sheet remains in the source replay.
        self.assertEqual(replay['last_sample_frame'],8.5)
        self.assertEqual(replay['wave_period_seconds'],6)
        self.assertEqual(replay['structural_frames_per_wave'],40)
        self.assertIn('Adding salmon',self.window.log.toPlainText())
        self.window.add_fish.setChecked(False)
        self.window.components.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertTrue(self.window.build_button.isEnabled())
        self.window.output.setText(str(self.folder/'Structural only.blend'))
        self.window.start_build();until(lambda:not self.window.running,60)
        self.assertIsNotNone(self.window.last_output,self.window.log.toPlainText())
        self.assertFalse(self.window.last_output.with_suffix('.fish.json').exists())
        self.assertTrue(self.window.last_output.with_suffix('.json').exists())
        self.window.workflow.setCurrentIndex(0)
        self.assertTrue(self.window.frames.isVisible())
        self.assertFalse(self.window.build_button.isEnabled())  # Model mode still needs an enclosure.

    def test_invalid_replay_results_stop_before_salmon(self):
        if not find_blender():self.skipTest('Blender is not installed')
        self.setup_replay()
        Path(self.window.results.text()).write_text('not a results export')
        self.window.results_changed()
        until(lambda:not self.window.results_timer.isActive() and not self.window.workers)
        self.assertIsNone(self.window.last_output)
        self.assertFalse(self.window.build_button.isEnabled())
        self.assertIn('Could not read results',self.window.timing_summary.text())
        self.assertNotIn('Adding salmon',self.window.log.toPlainText())

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Sim2Blender GUI ')
        self.folder=Path(self.temp.name)
        self.window=MainWindow(self.folder/'settings.ini')
        self.window.show()
        self.window.model.setText(str(Path(__file__).resolve().parents[2]/'examples/models/winch_cage.amodel'))
        until(lambda:self.window.info is not None)
        until(lambda:not self.window.workers)
        self.window.output.setText(str(self.folder/'GUI salmon.blend'))
        self.window.count.setValue(2);self.window.frames.setValue(2)

    def tearDown(self):
        if self.window.running:
            self.window.cancel();until(lambda:not self.window.running)
        until(lambda:not self.window.workers)
        self.window.close();self.window.deleteLater();APP.processEvents()
        self.temp.cleanup()

    def test_real_build(self):
        blender=find_blender()
        if not blender:self.skipTest('Blender is not installed')
        self.window.blender.setText(blender)
        self.assertTrue(self.window.build_button.isEnabled())
        self.window.build_button.click()
        self.assertTrue(self.window.running)
        until(lambda:not self.window.running,60)
        self.assertIsNotNone(self.window.last_output,self.window.log.toPlainText())
        self.assertTrue(self.window.last_output.is_file())
        self.assertTrue(self.window.open_button.isEnabled())
        self.assertIn('Validated 2 fish',self.window.log.toPlainText())
        self.assertTrue(self.window.last_output.with_suffix('.build.log').is_file())

    def test_failure_and_cancellation(self):
        with patch.object(ModelJob,'command',return_value=(sys.executable,['-c',"print('Example failure',flush=True);raise SystemExit(2)"])):
            self.window.start_build();until(lambda:not self.window.running)
        self.assertIn('Build failed',self.window.status.text())
        self.assertFalse(self.window.open_button.isEnabled())
        with patch.object(ModelJob,'command',return_value=(sys.executable,['-c',"import time;print('Running',flush=True);time.sleep(60)"])):
            self.window.start_build()
            until(lambda:'Running' in self.window.log.toPlainText())
            self.window.cancel();until(lambda:not self.window.running)
        self.assertIn('cancelled',self.window.status.text())
        self.assertTrue(self.window.form.isEnabled())

    def test_missing_executable(self):
        with patch.object(ModelJob,'command',return_value=(str(self.folder/'missing.exe'),[])):
            self.window.start_build();until(lambda:not self.window.running)
        self.assertIn('Could not start',self.window.status.text())
        self.assertFalse(self.window.open_button.isEnabled())


if __name__=='__main__':unittest.main()
