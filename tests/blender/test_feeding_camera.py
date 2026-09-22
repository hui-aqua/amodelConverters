"""Unit and integration tests for Feeding Camera and pyramid volume pellet counter."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import bpy
from mathutils import Vector

from sim2blender.blender.feeding_camera import (
    setup_feeding_camera,
    count_pellets_in_frustum,
    build_frustum_pyramid_mesh,
    DEFAULT_FEEDING_CAMERA_CONFIG,
)
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


class TestFeedingCamera(unittest.TestCase):
    """Test suite for Feeding Camera pyramid frustum construction and pellet counting."""

    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.temp_dir = tempfile.TemporaryDirectory(prefix="test_feedcam_")
        self.folder = Path(self.temp_dir.name)
        self.model_path = _make_dummy_model(self.folder / "cage.amodel")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_setup_feeding_camera_and_frustum(self):
        """Verify feeding camera, pyramid frustum mesh, and HUD text creation."""
        scene = bpy.context.scene
        config = {
            "position": (2.5, 0.0, -5.0),
            "target": (0.0, 0.0, -5.0),
            "visual_distance_m": 2.5,
            "clip_start_m": 0.1,
            "focal_length_mm": 32.0,
            "aspect_ratio": (16, 9),
            "render_width": 1920,
            "render_height": 1080,
            "show_frustum": True,
            "show_counter": True,
        }

        cam_obj, frustum_obj, hud_obj = setup_feeding_camera(config, scene)

        # Check camera properties
        self.assertIsNotNone(cam_obj)
        self.assertEqual(cam_obj.name, "Feeding_Camera")
        self.assertAlmostEqual(cam_obj.location.x, 2.5, places=4)
        self.assertAlmostEqual(cam_obj.location.y, 0.0, places=4)
        self.assertAlmostEqual(cam_obj.location.z, -5.0, places=4)
        self.assertAlmostEqual(cam_obj.data.lens, 32.0, places=4)
        self.assertAlmostEqual(cam_obj.data.clip_start, 0.1, places=4)
        self.assertAlmostEqual(cam_obj.data.clip_end, 2.5, places=4)

        # Check render resolution FHD 16:9
        self.assertEqual(scene.render.resolution_x, 1920)
        self.assertEqual(scene.render.resolution_y, 1080)

        # Check frustum pyramid mesh (5 vertices: apex + 4 corners)
        self.assertIsNotNone(frustum_obj)
        self.assertEqual(frustum_obj.name, "Feeding_Camera_Frustum")
        self.assertIn(len(frustum_obj.data.vertices), (5, 9))
        self.assertEqual(frustum_obj.parent, cam_obj)

        # Check HUD counter text
        self.assertIsNotNone(hud_obj)
        self.assertEqual(hud_obj.name, "Feeding_Camera_HUD")
        self.assertEqual(hud_obj.parent, cam_obj)
        self.assertIn("Pellets: 0", hud_obj.data.body)

    def test_pellet_counting_inside_and_outside_frustum(self):
        """Verify strict detection inside the pyramid volume (FHD aspect ratio, 2.5m range)."""
        scene = bpy.context.scene
        scene.frame_start = 1
        scene.frame_end = 5

        # Camera at (2.5, 0, -5) looking at (0, 0, -5)
        config = {
            "position": (2.5, 0.0, -5.0),
            "target": (0.0, 0.0, -5.0),
            "visual_distance_m": 2.5,
            "clip_start_m": 0.1,
            "focal_length_mm": 32.0,
            "aspect_ratio": (16, 9),
            "show_frustum": True,
            "show_counter": True,
        }
        cam_obj, _, hud_obj = setup_feeding_camera(config, scene)

        # Create dummy pellet meshes
        # View direction is along -X axis from 2.5 down to 0.0.
        # Pellet 1: inside frustum at (1.5, 0.0, -5.0) -> depth = 1.0m (within 0.1 - 2.5m)
        mesh1 = bpy.data.meshes.new("P1")
        p1 = bpy.data.objects.new("Pellet_001", mesh1)
        p1.location = (1.5, 0.0, -5.0)
        scene.collection.objects.link(p1)

        # Pellet 2: inside frustum at (0.5, 0.0, -5.0) -> depth = 2.0m (within 0.1 - 2.5m)
        mesh2 = bpy.data.meshes.new("P2")
        p2 = bpy.data.objects.new("Pellet_002", mesh2)
        p2.location = (0.5, 0.0, -5.0)
        scene.collection.objects.link(p2)

        # Pellet 3: outside frustum (too far: depth = 3.5m > 2.5m) at (-1.0, 0.0, -5.0)
        mesh3 = bpy.data.meshes.new("P3")
        p3 = bpy.data.objects.new("Pellet_003", mesh3)
        p3.location = (-1.0, 0.0, -5.0)
        scene.collection.objects.link(p3)

        # Pellet 4: outside frustum (lateral offset: y = 5.0m) at (1.5, 5.0, -5.0)
        mesh4 = bpy.data.meshes.new("P4")
        p4 = bpy.data.objects.new("Pellet_004", mesh4)
        p4.location = (1.5, 5.0, -5.0)
        scene.collection.objects.link(p4)

        # Pellet 5: behind camera (x = 4.0m) at (4.0, 0.0, -5.0)
        mesh5 = bpy.data.meshes.new("P5")
        p5 = bpy.data.objects.new("Pellet_005", mesh5)
        p5.location = (4.0, 0.0, -5.0)
        scene.collection.objects.link(p5)

        stats = count_pellets_in_frustum(cam_obj, [p1, p2, p3, p4, p5], scene, 2.5, 0.1)

        self.assertEqual(stats["total_unique_pellets_detected"], 2)
        self.assertIn("Pellet_001", stats["pellet_details"])
        self.assertIn("Pellet_002", stats["pellet_details"])
        self.assertNotIn("Pellet_003", stats["pellet_details"])
        self.assertNotIn("Pellet_004", stats["pellet_details"])
        self.assertNotIn("Pellet_005", stats["pellet_details"])

        # Check HUD updated text
        self.assertIn("Pellets: 2", hud_obj.data.body)

    def test_pipeline_integration_with_feeding_camera(self):
        """Verify feeding camera works inside build_unified_scene and exports JSON report."""
        output_blend = self.folder / "scene_with_feedcam.blend"
        config = {
            "model": str(self.model_path),
            "output": str(output_blend),
            "membrane_ids": [1],
            "frames": 10,
            "environment": None,
            "replay": None,
            "fish_schooling": None,
            "feed_animation": None,
            "fish_feeding": None,
            "cinematic_camera": None,
            "feeding_camera": {
                "enabled": True,
                "position": [2.5, 0.0, -5.0],
                "target": [0.0, 0.0, -5.0],
                "visual_distance_m": 2.5,
                "clip_start_m": 0.1,
                "focal_length_mm": 32.0,
                "aspect_ratio": [16, 9],
                "render_width": 1920,
                "render_height": 1080,
                "show_frustum": True,
                "show_counter": True,
            },
        }

        build_unified_scene(config)
        scene = bpy.context.scene

        self.assertIsNotNone(scene.objects.get("Feeding_Camera"))
        self.assertIsNotNone(scene.objects.get("Feeding_Camera_Frustum"))
        self.assertIsNotNone(scene.objects.get("Feeding_Camera_HUD"))

        # Verify JSON report was created
        report_path = output_blend.with_suffix(".feeding_camera.json")
        self.assertTrue(report_path.exists())
        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(data["camera_name"], "Feeding_Camera")
        self.assertEqual(data["camera_position"], [2.5, 0.0, -5.0])
        self.assertEqual(data["visual_distance_m"], 2.5)

    def test_pipeline_feeding_camera_disabled_strictly(self):
        """Verify when feeding camera is None or enabled=False, no feeding camera objects exist."""
        output_blend = self.folder / "scene_no_feedcam.blend"
        config = {
            "model": str(self.model_path),
            "output": str(output_blend),
            "membrane_ids": [1],
            "frames": 10,
            "environment": None,
            "replay": None,
            "fish_schooling": None,
            "feed_animation": None,
            "fish_feeding": None,
            "cinematic_camera": None,
            "feeding_camera": None,  # Disabled
        }

        build_unified_scene(config)
        scene = bpy.context.scene

        self.assertIsNone(scene.objects.get("Feeding_Camera"))
        self.assertIsNone(scene.objects.get("Feeding_Camera_Frustum"))
        self.assertIsNone(scene.objects.get("Feeding_Camera_HUD"))
        report_path = output_blend.with_suffix(".feeding_camera.json")
        self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
