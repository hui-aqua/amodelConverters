"""Tests for Blender spreader waterline adjustment and visualization."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import unittest
import tempfile

try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.spreader_waterline import (
        visualize_spreader_waterline,
        update_spreader_waterline_transform,
        ROOT_OBJ_NAME,
        WATER_SURFACE_NAME,
        TEXT_OBJ_NAME,
        RULER_OBJ_NAME,
    )
    from sim2blender.blender.feed import run_feed_animation
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class SpreaderWaterlineTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.data.scenes.new("WaterlineTestScene")
        bpy.context.window.scene = self.scene

    def tearDown(self):
        for col_name in ["Spreader_Waterline_Preview", "Feed_Animation_30RPM_30kgmin", "FishFeed_Proxy_Particles"]:
            col = bpy.data.collections.get(col_name)
            if col is not None:
                for obj in list(col.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.collections.remove(col)
        for name in ["spreader_move", "spreader_still", "FishFeed_Outlet_30kgmin", "Feed_Rotor_30RPM"]:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
        if self.scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(self.scene, do_unlink=True)

    def test_default_waterline_visualization(self):
        """Test default 0.52m lift with water surface at Z=0.0."""
        res = visualize_spreader_waterline(
            z_offset=0.52,
            water_level_z=0.0,
            scene=self.scene,
            setup_interactive_ui=False,
            setup_camera_and_lighting=True,
        )

        root = res["root"]
        water_surf = res["water_surface"]
        text_obj = res["text"]
        ruler_obj = res["ruler"]

        self.assertIsNotNone(root)
        self.assertIsNotNone(water_surf)
        self.assertIsNotNone(text_obj)
        self.assertIsNotNone(ruler_obj)

        # Check root position and stored properties
        self.assertAlmostEqual(root.location.z, 0.52, places=3)
        self.assertAlmostEqual(root["waterline_z_offset"], 0.52, places=3)
        self.assertAlmostEqual(root["water_level_z"], 0.0, places=3)

        # Water surface at Z=0
        self.assertAlmostEqual(water_surf.location.z, 0.0, places=3)

        # Spreader children parented to root
        spreader_move = res["spreader_move"]
        spreader_still = res["spreader_still"]
        if spreader_move:
            self.assertEqual(spreader_move.parent, root)
        if spreader_still:
            self.assertEqual(spreader_still.parent, root)

        # 3D Text content contains +0.520 m
        self.assertIn("+0.520 m", text_obj.data.body)

        # Ruler scale matches offset
        self.assertAlmostEqual(ruler_obj.scale.z, 0.52, places=3)

    def test_y_up_obj_conversion_survives_rig_parenting(self):
        """Source +Y becomes +Z even after the rig resets object rotation."""
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / f"spreader_{part}.obj" for part in ("move", "still")]
            for path in paths:
                path.write_text("v 0 0 0\nv 1 2 3\nv 1 0 0\nf 1 2 3\n")
            result = visualize_spreader_waterline(
                move_obj_path=paths[0], still_obj_path=paths[1],
                z_offset=0.52, water_level_z=1.0, scene=self.scene,
                setup_interactive_ui=False, setup_camera_and_lighting=False,
            )
            for key in ("spreader_move", "spreader_still"):
                obj = result[key]
                point = obj.matrix_world @ obj.data.vertices[1].co
                for actual, expected in zip(point, (1.0, -3.0, 3.52)):
                    self.assertAlmostEqual(actual, expected, places=5)

    def test_custom_water_level_and_offset(self):
        """Test custom non-zero water level (e.g. Z = -1.5m) and custom lift (0.80m)."""
        res = visualize_spreader_waterline(
            z_offset=0.80,
            water_level_z=-1.5,
            scene=self.scene,
            setup_interactive_ui=False,
            setup_camera_and_lighting=False,
        )

        root = res["root"]
        water_surf = res["water_surface"]

        # Expected world Z = -1.5 + 0.80 = -0.70m
        self.assertAlmostEqual(root.location.z, -0.70, places=3)
        self.assertAlmostEqual(water_surf.location.z, -1.5, places=3)

    def test_transform_update(self):
        """Test dynamic transform updates as user adjusts offset."""
        visualize_spreader_waterline(
            z_offset=0.52,
            water_level_z=0.0,
            scene=self.scene,
            setup_interactive_ui=False,
            setup_camera_and_lighting=False,
        )

        update_spreader_waterline_transform(self.scene, z_offset=0.95, water_level_z=0.2)

        root = bpy.data.objects.get(ROOT_OBJ_NAME)
        water_surf = bpy.data.objects.get(WATER_SURFACE_NAME)
        text_obj = bpy.data.objects.get(TEXT_OBJ_NAME)

        self.assertAlmostEqual(root.location.z, 1.15, places=3)
        self.assertAlmostEqual(water_surf.location.z, 0.2, places=3)
        self.assertIn("+0.950 m", text_obj.data.body)

    def test_feed_animation_inherits_spreader_z_offset(self):
        """Verify feed animation positions rotor at water_level_z + spreader_z_offset."""
        self.scene.frame_start = 1
        self.scene.frame_end = 5
        self.scene.render.fps = 30

        run_feed_animation({
            "spreader_z_offset": 0.52,
            "water_level_z": 0.0,
            "rpm": -30.0,
            "mass_flow_kg_min": 1.0,
            "visual_particle_mass_kg": 0.1,
            "particle_lifetime_s": 0.5,
        })

        rotor = bpy.data.objects.get("Feed_Rotor_30RPM")
        self.assertIsNotNone(rotor)
        self.assertAlmostEqual(rotor.location.z, 0.52, places=3)

        outlet = bpy.data.objects.get("FishFeed_Outlet_30kgmin")
        self.assertIsNotNone(outlet)
        # World Z of outlet should be above 0.52m
        self.assertGreater(outlet.matrix_world.translation.z, 0.52)

        move = bpy.data.objects.get("spreader_move")
        still = bpy.data.objects.get("spreader_still")
        if move and still:
            bpy.context.view_layer.update()
            self.assertAlmostEqual(still.matrix_world.translation.z, 0.52, places=3)
            self.assertAlmostEqual(move.matrix_world.translation.z, 0.52, places=3)
            self.assertAlmostEqual(rotor.matrix_world.translation.z, 0.52, places=3)

        self.assertEqual(self.scene["feed_spreader_z_offset"], 0.52)


if __name__ == "__main__":
    import sys
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv += sys.argv[sys.argv.index("--") + 1:]
    unittest.main(argv=argv)
