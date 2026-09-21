import math
import unittest
from sim2blender.core.waves import jonswap_components, spectral_elevation


class SpectrumTests(unittest.TestCase):
    def test_energy_and_dispersion(self):
        waves = jonswap_components(2.4, 7)
        self.assertAlmostEqual(4*math.sqrt(sum(w[0]**2/2 for w in waves)), 2.4)
        for _, omega, kx, ky, _ in waves:
            self.assertAlmostEqual(math.hypot(kx, ky), omega**2/9.81)

    def test_repeatability_and_irregularity(self):
        waves = jonswap_components(2, 6)
        self.assertEqual(waves, jonswap_components(2, 6))
        self.assertNotEqual(waves, jonswap_components(2, 6, seed=43))
        self.assertNotAlmostEqual(spectral_elevation(waves, 0, 0, 0), spectral_elevation(waves, 0, 0, 6))
        self.assertEqual(spectral_elevation(jonswap_components(0, 6), 3, 4, 5), 0)

    def test_validation_and_direction(self):
        for kwargs in ({'period': 0}, {'gamma': 0}, {'count': 1}, {'spread': -1}):
            args = dict(height=1, period=6)
            args.update(kwargs)
            with self.assertRaises(ValueError):
                jonswap_components(**args)
        for _, _, kx, _, _ in jonswap_components(1, 6, direction=90, spread=0):
            self.assertAlmostEqual(kx, 0)
