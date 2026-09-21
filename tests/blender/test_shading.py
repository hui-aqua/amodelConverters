"""Small material regressions independent of visual subjective checks."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim2blender.blender.shading import lattice_pixels

class LatticeTests(unittest.TestCase):
    def test_openings_and_coverage(self):
        size=128;u=.1;v=.08
        pixels=lattice_pixels(size,u,v)
        alpha=pixels[3::4]
        self.assertEqual(alpha[(size//2)*size+size//2],0)
        self.assertEqual(alpha[0],1)
        self.assertAlmostEqual(sum(alpha)/(size*size),u+v-u*v,delta=.003)
        self.assertTrue(all(0<=x<=1 for x in pixels))

if __name__=='__main__':unittest.main()
