import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from sim2blender.core.timeline import frames_from_seconds, sample_frames, wave_timing
from sim2blender.core.paths import PROJECT_ROOT


class TimelineTests(unittest.TestCase):
    def test_wave_timeline_matches_replay(self):
        for count,period,per_wave,fps in ((406,10.,80,25),(3,6.,40,25),(1,5.,40,30)):
            timing=wave_timing(count,period,per_wave,fps)
            self.assertEqual(timing['last_sample_frame'],sample_frames(count,period/per_wave,fps)[-1])
            self.assertAlmostEqual(timing['duration_seconds'],(count-1)*period/per_wave)
        timing=wave_timing(406,10,80,25)
        self.assertEqual(timing['duration_seconds'],50.625)
        self.assertEqual(timing['video_frame_end'],1267)
        self.assertAlmostEqual(timing['video_duration_seconds'],50.68)
        for count,period,per_wave,fps in ((0,5,40,25),(3,0,40,25),(3,5,0,25),(3,5,2.5,25),(3,5,40,0)):
            with self.assertRaises(ValueError):wave_timing(count,period,per_wave,fps)

    def test_shared_origin_for_independent_sources(self):
        self.assertEqual(frames_from_seconds([10, 10.125], 25, origin_seconds=10), [1, 4.125])
        for actual, expected in zip(frames_from_seconds([10.04, 10.08], 25, origin_seconds=10), [2, 3]):
            self.assertAlmostEqual(actual, expected)

    def test_irregular_times_and_validation(self):
        self.assertEqual(frames_from_seconds([0, .04, .2]), [1, 2, 6])
        for times in ([], [0, 0], [1, 0], [float('nan')]):
            with self.assertRaises(ValueError):
                frames_from_seconds(times)

    def test_legacy_imports_and_defaults(self):
        from sim2blender.amodel import read_model as old_reader
        from sim2blender.io.aquasim.model import read_model
        from sim2blender.results import sample_frames as old_timing
        self.assertIs(old_reader, read_model)
        self.assertIs(old_timing, sample_frames)
        self.assertTrue((PROJECT_ROOT/'examples/models/winch_cage.amodel').is_file())
