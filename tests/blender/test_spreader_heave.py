"""Blender integration tests for wave-induced spreader heave motion (RAO = 0.5)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    import bpy
    from sim2blender.blender.feed import run_feed_animation, SPREADER_Z_OFFSET
    from sim2blender.blender.spreader_waterline import visualize_spreader_waterline, ROOT_OBJ_NAME
    from sim2blender.blender.animation import action_fcurves
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


def find_fcurve(obj, data_path, index=0):
    if not obj.animation_data or not obj.animation_data.action:
        return None
    for fc in action_fcurves(obj.animation_data.action):
        if fc.data_path == data_path and fc.array_index == index:
            return fc
    return None


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class SpreaderHeaveTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.scene.render.fps = 25
        self.scene.frame_start = 1
        self.scene.frame_end = 50

    def test_spreader_heave_motion_rao_05(self):
        """Verify spreader heaves with RAO = 0.5 under waves (H=0.4m, T=5s)."""
        wave_h = 0.40
        wave_t = 5.0
        z_offset = 0.52
        water_z = 0.0
        rao = 0.5

        config = {
            "spreader_z_offset": z_offset,
            "water_level_z": water_z,
            "wave_height_m": wave_h,
            "wave_period_s": wave_t,
            "wave_length_m": 25.0,
            "wave_direction_deg": 0.0,
            "spreader_heave_rao": rao,
            "mass_flow_kg_min": 1.0,
            "visual_particle_mass_kg": 0.01,
        }
        # 125 frames at 25 fps covers the full 5.0s wave period
        self.scene.frame_end = 125
        run_feed_animation(config)

        rotor = bpy.data.objects.get("Feed_Rotor_30RPM")
        self.assertIsNotNone(rotor)

        still_obj = bpy.data.objects.get("spreader_still")
        self.assertIsNotNone(still_obj)

        z_positions = []
        fcurve_rotor = find_fcurve(rotor, "location", index=2)
        self.assertIsNotNone(fcurve_rotor, "Rotor must have location Z fcurve for heave motion")

        for f in range(1, 126):
            z_val = fcurve_rotor.evaluate(f)
            z_positions.append(z_val)

        z_max = max(z_positions)
        z_min = min(z_positions)
        heave_amplitude = (z_max - z_min) / 2.0
        expected_amplitude = rao * (wave_h / 2.0)  # 0.5 * 0.20 = 0.10 m

        self.assertAlmostEqual(heave_amplitude, expected_amplitude, places=3,
                               msg=f"Expected heave amplitude {expected_amplitude:.3f}m, got {heave_amplitude:.3f}m")
        self.assertAlmostEqual(z_max, z_offset + expected_amplitude, places=3,
                               msg=f"Peak elevation should be {z_offset + expected_amplitude:.3f}m")
        self.assertAlmostEqual(z_min, z_offset - expected_amplitude, places=3,
                               msg=f"Trough elevation should be {z_offset - expected_amplitude:.3f}m")

        # Verify still_obj has identical heave motion
        fcurve_still = find_fcurve(still_obj, "location", index=2)
        self.assertIsNotNone(fcurve_still, "Stationary base must have location Z fcurve")
        for f in (1, 25, 50, 75):
            self.assertAlmostEqual(fcurve_rotor.evaluate(f), fcurve_still.evaluate(f), places=5)

    def test_spreader_heave_disabled_when_rao_zero(self):
        """When RAO = 0.0, spreader should remain completely static at equilibrium."""
        config = {
            "spreader_z_offset": 0.52,
            "water_level_z": 0.0,
            "wave_height_m": 0.40,
            "wave_period_s": 5.0,
            "spreader_heave_rao": 0.0,
            "mass_flow_kg_min": 1.0,
            "visual_particle_mass_kg": 0.01,
        }
        run_feed_animation(config)

        rotor = bpy.data.objects.get("Feed_Rotor_30RPM")
        self.assertIsNotNone(rotor)
        # Location should be static at 0.52m
        self.assertAlmostEqual(rotor.location.z, 0.52, places=4)
        fcurve_z = find_fcurve(rotor, "location", index=2)
        self.assertIsNone(fcurve_z, "Rotor should not have location Z fcurve when RAO=0")

    def test_pellet_emission_heave_coupling(self):
        """Pellet initial position and velocity must couple with the spreader heave."""
        config = {
            "spreader_z_offset": 0.52,
            "water_level_z": 0.0,
            "wave_height_m": 0.60,
            "wave_period_s": 4.0,
            "spreader_heave_rao": 0.5,
            "mass_flow_kg_min": 30.0,
            "visual_particle_mass_kg": 0.01,
        }
        run_feed_animation(config)

        particles = [o for o in bpy.data.objects if o.name.startswith("FeedPellet_")]
        self.assertTrue(len(particles) > 5)

        # Examine initial launch Z positions of pellets across time
        z_starts = []
        for p in particles[:20]:
            fcurve_z = find_fcurve(p, "location", index=2)
            if fcurve_z and fcurve_z.keyframe_points:
                first_k = fcurve_z.keyframe_points[0]
                z_starts.append(first_k.co[1])

        self.assertTrue(len(z_starts) > 5)
        # Since pellets are emitted over a wave cycle, their initial Z must vary
        z_diff = max(z_starts) - min(z_starts)
        self.assertGreater(z_diff, 0.05, f"Pellets should be emitted at varying heave heights, got diff {z_diff:.4f}m")

    def test_waterline_preview_heave_animation(self):
        """Verify interactive waterline visualizer supports heave motion."""
        res = visualize_spreader_waterline(
            z_offset=0.52,
            water_level_z=0.0,
            heave_rao=0.5,
            wave_height=0.40,
            wave_period=5.0,
            animate_heave=True,
        )
        root = res["root"]
        self.assertEqual(root["spreader_heave_rao"], 0.5)

        fcurve = find_fcurve(root, "location", index=2)
        self.assertIsNotNone(fcurve, "Root object should have location Z fcurve when animate_heave=True")
        z_vals = [fcurve.evaluate(f) for f in range(1, 101)]
        amp = (max(z_vals) - min(z_vals)) / 2.0
        self.assertAlmostEqual(amp, 0.5 * 0.20, places=3)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SpreaderHeaveTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)
