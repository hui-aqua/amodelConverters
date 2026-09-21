"""Tests for wave and current hydrodynamics model and its effects on water, feed, and fish."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import unittest
try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.water import add_water
    from sim2blender.blender.environment import (
        calculate_water_velocity,
        calculate_wave_elevation,
        set_wave_and_current,
        get_hydrodynamic_parameters,
    )
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.data.scenes.new("EnvTestScene")
        if hasattr(bpy.context, "window") and bpy.context.window:
            bpy.context.window.scene = self.scene
        self.scene.render.fps = 25
        self.scene.frame_start = 1
        self.scene.frame_end = 10

    def tearDown(self):
        other_scene = next((s for s in bpy.data.scenes if s != self.scene), None)
        if other_scene and hasattr(bpy.context, "window") and bpy.context.window:
            bpy.context.window.scene = other_scene
        if self.scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(self.scene, do_unlink=True)

    def test_water_velocity_and_wave_elevation(self):
        # Current = 0.5 m/s along +X (0 deg), Wave = 1.0 m height, 5.0 s period
        v_surf = calculate_water_velocity(
            Vector((0, 0, 0)), t=0.0,
            current_speed=0.5, current_dir_deg=0.0,
            wave_height=1.0, wave_period=5.0, wave_length=30.0, wave_dir_deg=0.0,
        )
        self.assertGreater(v_surf.x, 0.5)  # Current + wave peak velocity along +X

        # Elevation at t=0 peak should be level + H/2 = 0.5
        eta = calculate_wave_elevation(0, 0, t=0.0, wave_height=1.0, wave_period=5.0)
        self.assertAlmostEqual(eta, 0.5)

    def test_set_wave_and_current_animates_surface(self):
        res = add_water(self.scene, level=0.0, depth=50.0, size=100.0)
        surf = res["surface"]

        set_wave_and_current(
            self.scene,
            current_speed=0.6,
            wave_height=1.2,
            wave_period=4.0,
            animate_water_surface=True,
        )

        params = get_hydrodynamic_parameters(self.scene)
        self.assertEqual(params["current_speed"], 0.6)
        self.assertEqual(params["wave_height"], 1.2)

        # Check keyframes inserted on water surface shape keys
        self.assertIsNotNone(surf.data.shape_keys)
        self.assertIsNotNone(surf.data.shape_keys.animation_data)

    def test_wave_and_current_effect_on_feed_pellets(self):
        from sim2blender.blender.feed import compute_particle_trajectory

        p_still, _ = compute_particle_trajectory(
            Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 0, 0)), Vector((0, 0, 0)),
            duration_s=8.0, current_speed=0.0, wave_height=0.0,
        )
        p_curr, _ = compute_particle_trajectory(
            Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 0, 0)), Vector((0, 0, 0)),
            duration_s=8.0, current_speed=0.5, current_dir_deg=90.0, wave_height=0.0,
        )
        # In still water, motion stays in XZ plane (Y = 0)
        self.assertAlmostEqual(p_still[-1].y, 0.0, places=3)
        # In +Y current, pellet drifts significantly in +Y direction
        self.assertGreater(p_curr[-1].y, 2.5)

        # In waves, particle trajectory is altered by orbital velocity field
        p_wave, _ = compute_particle_trajectory(
            Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 0, 0)), Vector((0, 0, 0)),
            duration_s=8.0, current_speed=0.0, wave_height=1.0, wave_period=4.0,
        )
        self.assertNotEqual(round(p_still[-1].x, 3), round(p_wave[-1].x, 3))

    def test_wave_and_current_effect_on_fish_schooling(self):
        import bmesh
        from sim2blender.blender.fish.school import run_fish_schooling

        mesh = bpy.data.meshes.new("Membrane cage")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=15.0)
        bm.to_mesh(mesh)
        bm.free()
        cage = bpy.data.objects.new("Membrane cage", mesh)
        self.scene.collection.objects.link(cage)

        cfg = {
            "fish_count": 5,
            "current_speed_m_s": 0.4,
            "current_direction_deg": 45.0,
            "wave_height_m": 0.8,
            "wave_period_s": 4.0,
        }
        run_fish_schooling(cfg)
        school = bpy.data.collections.get("Fish school")
        self.assertIsNotNone(school)
        self.assertEqual(len(school.objects), 5)
        fish_obj = school.objects[0]
        self.assertIsNotNone(fish_obj.animation_data)
        self.assertIsNotNone(fish_obj.animation_data.action)

    def test_cloth_physics_under_wave_and_current(self):
        # 1. Configure wave and current with cloth forces
        set_wave_and_current(
            self.scene,
            current_speed=0.8,
            current_dir_deg=0.0,
            wave_height=1.0,
            wave_period=4.0,
            wave_dir_deg=0.0,
            setup_cloth_forces=True,
        )

        curr_force = self.scene.objects.get("Hydrodynamic_Current_Force")
        wave_force = self.scene.objects.get("Hydrodynamic_Wave_Force")
        self.assertIsNotNone(curr_force)
        self.assertIsNotNone(wave_force)
        self.assertEqual(curr_force.field.type, "WIND")
        self.assertEqual(wave_force.field.type, "WIND")
        self.assertGreater(curr_force.field.strength, 0.0)

        # Check wave force has scripted driver
        fcurves = wave_force.animation_data.drivers if wave_force.animation_data else []
        self.assertTrue(len(fcurves) > 0)

        # 2. Test physical cloth simulation of a cage cylinder responding to hydrodynamics
        bpy.ops.mesh.primitive_cylinder_add(radius=5.0, depth=10.0)
        cage = bpy.context.object
        p0 = [v.co.copy() for v in cage.data.vertices]

        pins = cage.vertex_groups.new(name="Fixed top")
        top_verts = [i for i, v in enumerate(p0) if v.z > 4.9]
        pins.add(top_verts, 1.0, "REPLACE")

        cloth = cage.modifiers.new("Cage cloth", "CLOTH")
        cloth.settings.vertex_group_mass = pins.name
        cloth.settings.air_damping = 5.0
        cloth.point_cache.frame_start = 1
        cloth.point_cache.frame_end = 15

        with bpy.context.temp_override(point_cache=cloth.point_cache):
            bpy.ops.ptcache.bake(bake=True)

        self.assertTrue(cloth.point_cache.is_baked)

        # Evaluate deformation at frame 15
        self.scene.frame_set(15)
        deps = bpy.context.evaluated_depsgraph_get()
        eval_cage = cage.evaluated_get(deps)
        dx = [v.co.x - p0[i].x for i, v in enumerate(eval_cage.data.vertices)]

        # Cage should deflect downstream in +X direction under wave and current
        max_dx = max(dx)
        mean_dx = sum(dx) / len(dx)
        self.assertGreater(max_dx, 0.5, f"Expected cloth deflection > 0.5m, got {max_dx:.3f}m")
        self.assertGreater(mean_dx, 0.2, f"Expected mean cloth deflection > 0.2m, got {mean_dx:.3f}m")


suite = unittest.defaultTestLoader.loadTestsFromTestCase(EnvironmentTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError("Environment tests failed")

