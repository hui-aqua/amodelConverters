import tempfile
from pathlib import Path
import unittest
from sim2blender.amodel import Model, Node
from sim2blender.results import read_results, map_nodes, sample_frames


class ResultsTests(unittest.TestCase):
    def test_physical_timeline(self):
        frames = sample_frames(406, .125, 25)
        self.assertEqual(frames[:3], [1, 4.125, 7.25])
        self.assertEqual(frames[-1], 1266.625)
        self.assertEqual((frames[-1]-1)/25, 50.625)
        for count, dt, fps in ((0, .125, 25), (2, 0, 25), (2, float('nan'), 25), (2, .125, 0)):
            with self.assertRaises(ValueError):
                sample_frames(count, dt, fps)

    def read(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'out.txt'
            path.write_text('Time [-] VID [-] X Y Z\n' + rows)
            return read_results(path)

    def test_solver_ids_are_not_model_ids(self):
        result = self.read('0 1 0 0 -80.2\n1 1 1 2 -79\n')
        model = Model({73: Node(73, (0, 0, -80.2), (True,)*3)}, [])
        self.assertEqual(map_nodes(model, result), {73: 1})
        self.assertEqual(result.positions[1][1], (1, 2, -79))

    def test_reject_invalid_samples(self):
        for rows in ('0 1 0 0 0\n0 1 0 0 0\n',
                     '1 1 0 0 0\n0 1 0 0 0\n',
                     '0 1 0 0 0\n1 2 0 0 0\n', '0 1 nan 0 0\n'):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.read(rows)

    def test_reject_ambiguous_and_missing_matches(self):
        model = Model({73: Node(73, (0, 0, 0), (True,)*3)}, [])
        for rows in ('0 1 1 0 0\n', '0 1 0 0 0\n0 2 0 0 0\n'):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                map_nodes(model, self.read(rows))

    def test_blank_lines_unordered_ids_and_irregular_times(self):
        result = self.read('\n0 2 1 0 0\n0 1 0 0 0\n\n2.5 1 3 0 0\n2.5 2 4 0 0\n')
        self.assertEqual(result.times, [0, 2.5])
        self.assertEqual(result.positions[1][2], (4, 0, 0))

    def test_reject_empty_and_malformed(self):
        for rows in ('', '0 1 0 0\n', '0 1.5 0 0 0\n', 'inf 1 0 0 0\n'):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.read(rows)

    def test_reject_model_nodes_sharing_vid(self):
        model = Model({i: Node(i, (0, 0, 0), (True,)*3) for i in (7, 8)}, [])
        with self.assertRaises(ValueError):
            map_nodes(model, self.read('0 1 0 0 0\n'))


if __name__ == '__main__': unittest.main()
