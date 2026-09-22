"""Integration tests verifying strict activation of optional functions in Sim2Blender.

Ensures that when optional functions (Environment, Replay, Fish Schooling,
Feed Spreader, Fish Feeding, Cinematic Camera) are unselected/disabled:
1. No ocean water surface or volume is created.
2. No wave animation or current force fields are added to the scene.
3. Spreader rotor remains strictly static without wave heave motion.
4. Unselected stages leave no extraneous objects in the Blender scene.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import bpy

from sim2blender.workflows.unified_pipeline import build_unified_scene


def _make_dummy_model(output_path: Path) -> Path:
    """Create a minimal cube .amodel file for pipeline testing."""
    points = [(x, y, z) for z in (-2.0, 2.0) for y in (-2.0, 2.0) for x in (-2.0, 2.0)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    nodes = "".join(
        f'<node id="{i+100}" x="{p[0]}" y="{p[1]}" z="{p[2]}" translate="false"/>'
        for i, p in enumerate(points)
    )
    elements = "".join(
        f'<element id="{i}" ' + " ".join(f'node{a}="{n+100}"' for a, n in zip("ABCD", face)) + "/>"
        for i, face in enumerate(faces)
    )
    content = (
        f'<model><Nodes>{nodes}</Nodes>'
        f'<Components><membrane id="1" active="true" diameter="0.002" maskwidthy="0.025" maskwidthz="0.025">'
        f'<elements>{elements}</elements></membrane></Components></model>'
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


class TestOptionalFunctions(unittest.TestCase):
    """Verify that optional functions ONLY take effect when explicitly enabled."""

    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.temp_dir = tempfile.TemporaryDirectory(prefix="test_opt_func_")
        self.folder = Path(self.temp_dir.name)
        self.model_path = _make_dummy_model(self.folder / "cage.amodel")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_environment_disabled_produces_no_water_mesh_or_waves(self):
        """When environment is None or enabled=False, no water objects or waves must exist."""
        output_blend = self.folder / "scene_no_env.blend"
        config = {
            "model": str(self.model_path),
            "output": str(output_blend),
            "membrane_ids": [1],
            "frames": 10,
            "environment": None,  # Deselected in GUI
            "replay": None,
            "fish_schooling": None,
            "feed_animation": None,
            "fish_feeding": None,
            "cinematic_camera": None,
        }

        build_unified_scene(config)
        scene = bpy.context.scene

        # Must NOT create water surface or volume
        self.assertIsNone(scene.objects.get("Ocean Water Surface"))
        self.assertIsNone(scene.objects.get("Ocean Water Volume"))
        self.assertIsNone(scene.objects.get("Water surface"))

        # Hydrodynamics must be inactive
        self.assertFalse(scene.get("hydrodynamics_active", False))
        self.assertEqual(scene.get("wave_height_m", 0.0), 0.0)
        self.assertEqual(scene.get("current_speed_m_s", 0.0), 0.0)

    def test_environment_disabled_with_feed_has_zero_heave_and_no_waves(self):
        """When environment is disabled but feed is enabled, spreader must NOT heave."""
        output_blend = self.folder / "scene_feed_no_env.blend"
        config = {
            "model": str(self.model_path),
            "output": str(output_blend),
            "membrane_ids": [1],
            "frames": 15,
            "environment": None,  # Deselected
            "feed_animation": {
                "enabled": True,
                "spreader_z_offset": 0.52,
                "spreader_heave_rao": 0.5,
                "rpm": -30.0,
                "mass_flow_kg_min": 10.0,
                "visual_particle_mass_kg": 0.05,
            },
        }

        build_unified_scene(config)
        scene = bpy.context.scene

        # Water meshes must NOT exist
        self.assertIsNone(scene.objects.get("Ocean Water Surface"))
        self.assertIsNone(scene.objects.get("Ocean Water Volume"))
        self.assertFalse(scene.get("hydrodynamics_active", False))

        # Feed rotor must exist
        rotor = scene.objects.get("Feed_Rotor_30RPM")
        self.assertIsNotNone(rotor)

        # Spreader rotor Z must remain constant (0.52 m) across all frames - NO HEAVE
        for frame in range(1, 16):
            scene.frame_set(frame)
            evaluated_rotor = rotor.evaluated_get(bpy.context.evaluated_depsgraph_get())
            z_pos = evaluated_rotor.matrix_world.translation.z
            self.assertAlmostEqual(z_pos, 0.52, places=3,
                                   msg=f"Frame {frame} had unexpected Z variation {z_pos} with no environment")

    def test_environment_enabled_creates_water_and_waves(self):
        """When environment is enabled, ocean water surface, volume, and wave props must exist."""
        output_blend = self.folder / "scene_with_env.blend"
        config = {
            "model": str(self.model_path),
            "output": str(output_blend),
            "membrane_ids": [1],
            "frames": 5,
            "environment": {
                "enabled": True,
                "water_level_m": 0.0,
                "water_depth_m": 50.0,
                "water_size_m": 100.0,
                "wave_height_m": 0.40,
                "wave_period_s": 5.0,
                "current_speed_m_s": 0.20,
            },
        }

        build_unified_scene(config)
        scene = bpy.context.scene

        # Water meshes MUST exist
        self.assertIsNotNone(scene.objects.get("Water surface"))
        self.assertIsNotNone(scene.objects.get("Water volume"))
        self.assertTrue(scene.get("hydrodynamics_active", False))
        self.assertEqual(scene.get("wave_height_m"), 0.40)
        self.assertEqual(scene.get("current_speed_m_s"), 0.20)

    def test_unselected_subsystems_leave_no_unwanted_objects(self):
        """When optional subsystems are disabled, their objects must NOT be created."""
        output_blend = self.folder / "scene_bare.blend"
        config = {
            "model": str(self.model_path),
            "output": str(output_blend),
            "membrane_ids": [1],
            "frames": 5,
            "environment": None,
            "replay": None,
            "fish_schooling": None,
            "feed_animation": None,
            "fish_feeding": None,
            "cinematic_camera": None,
        }

        build_unified_scene(config)
        scene = bpy.context.scene

        # No feed spreader or particles
        self.assertIsNone(scene.objects.get("Feed_Rotor_30RPM"))
        self.assertIsNone(bpy.data.collections.get("FishFeed_Proxy_Particles"))

        # No fish objects
        fish_objs = [o for o in scene.objects if o.name.startswith("Fish_")]
        self.assertEqual(len(fish_objs), 0)

        # No cinematic camera
        self.assertIsNone(scene.objects.get("Cinematic_Camera_Rig"))
        self.assertIsNone(scene.objects.get("CinematicCamera"))


if __name__ == "__main__":
    unittest.main()
