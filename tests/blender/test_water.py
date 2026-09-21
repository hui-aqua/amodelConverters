"""Tests for Blender water surface and underwater volume creation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import unittest
try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.water import add_water
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class WaterTests(unittest.TestCase):
    def setUp(self):
        # Create a fresh scene for testing
        self.scene = bpy.data.scenes.new("WaterTestScene")

    def tearDown(self):
        if self.scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(self.scene, do_unlink=True)

    def test_add_water_default_z0(self):
        res = add_water(self.scene, level=0.0, depth=100.0, size=200.0)
        surf = res["surface"]
        vol = res["volume"]

        self.assertIsNotNone(surf)
        self.assertIsNotNone(vol)
        self.assertTrue(surf["is_water"])
        self.assertEqual(surf["water_level"], 0.0)
        self.assertEqual(surf["water_depth"], 100.0)

        # Check surface mesh points are at Z = 0.0
        surf_verts = surf.data.vertices
        self.assertTrue(all(abs(v.co.z - 0.0) < 1e-5 for v in surf_verts))

        # Check volume mesh extends from Z = 0.0 down to Z = -100.0
        vol_verts = vol.data.vertices
        z_coords = [v.co.z for v in vol_verts]
        self.assertAlmostEqual(max(z_coords), 0.0)
        self.assertAlmostEqual(min(z_coords), -100.0)

        # Check materials attached
        self.assertEqual(len(surf.data.materials), 1)
        self.assertEqual(len(vol.data.materials), 1)
        self.assertEqual(surf.data.materials[0].name, "Ocean Water Surface Material")
        self.assertEqual(vol.data.materials[0].name, "Ocean Water Volume Material")

    def test_custom_water_level(self):
        res = add_water(self.scene, level=-2.0, depth=50.0, size=150.0)
        surf = res["surface"]
        vol = res["volume"]

        self.assertAlmostEqual(surf["water_level"], -2.0)
        surf_verts = surf.data.vertices
        self.assertTrue(all(abs(v.co.z - (-2.0)) < 1e-5 for v in surf_verts))

        vol_verts = vol.data.vertices
        z_coords = [v.co.z for v in vol_verts]
        self.assertAlmostEqual(max(z_coords), -2.0)
        self.assertAlmostEqual(min(z_coords), -52.0)

    def test_ocean_lighting_and_rendering(self):
        from sim2blender.blender.water import setup_ocean_lighting
        from sim2blender.blender.shading import setup_screen_rendering

        lighting = setup_ocean_lighting(self.scene, sun_energy=5.0)
        self.assertIsNotNone(lighting["sun"])
        self.assertEqual(lighting["sun"].data.type, "SUN")
        self.assertEqual(lighting["sun"].data.energy, 5.0)
        self.assertIsNotNone(lighting["world"])
        self.assertEqual(lighting["world"].name, "Ocean Sky")
        self.assertIsNotNone(lighting["underwater_fill"])

        # Test screen rendering setup
        setup_screen_rendering(self.scene, engine="CYCLES", samples=64)
        self.assertEqual(self.scene.render.engine, "CYCLES")
        self.assertEqual(self.scene.cycles.samples, 64)
        self.assertTrue(self.scene.cycles.use_denoising)
        self.assertEqual(self.scene.render.resolution_x, 1920)
        self.assertEqual(self.scene.render.resolution_y, 1080)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(WaterTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError("Water tests failed")

