"""Unit and integration tests for pre-build 3D model and color preview."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.model_preview import (
        build_model_preview_scene,
        create_reference_cage_mesh,
        create_water_surface_plane,
        inspect_object_materials,
        get_object_bounds_and_dimensions,
        load_preview_obj_model,
        register_model_inspector_ui,
        unregister_model_inspector_ui,
        PREVIEW_COLLECTION_NAME,
        WATER_PLANE_NAME,
    )
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


def _make_dummy_model(output_path: Path) -> Path:
    """Create a minimal cube .amodel file for preview testing."""
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
    beams = '<element id="200" StartNode_ID="100" EndNode_ID="101"/>'
    content = (
        f'<model><Nodes>{nodes}</Nodes>'
        f'<Components>'
        f'<membrane id="1" active="true" diameter="0.002" maskwidthy="0.025" maskwidthz="0.025">'
        f'<elements>{elements}</elements></membrane>'
        f'<beam id="2" active="true" diameter="0.25">'
        f'<elements>{beams}</elements></beam>'
        f'</Components></model>'
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _make_dummy_obj(output_path: Path) -> Path:
    """Create a simple OBJ file with a matching MTL companion."""
    mtl_path = output_path.with_suffix(".mtl")
    mtl_content = (
        "newmtl TestMaterial\n"
        "Kd 0.8 0.2 0.1\n"
        "map_Kd non_existent_texture_image.png\n"
    )
    mtl_path.write_text(mtl_content, encoding="utf-8")

    obj_content = (
        f"mtllib {mtl_path.name}\n"
        "usemtl TestMaterial\n"
        "v -0.5 -0.5 0.0\n"
        "v 0.5 -0.5 0.0\n"
        "v 0.5 0.5 0.0\n"
        "v -0.5 0.5 0.0\n"
        "f 1 2 3 4\n"
    )
    output_path.write_text(obj_content, encoding="utf-8")
    return output_path


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class ModelPreviewTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.temp_dir = tempfile.TemporaryDirectory(prefix="test_model_preview_")
        self.folder = Path(self.temp_dir.name)
        self.dummy_model = _make_dummy_model(self.folder / "cage.amodel")
        self.dummy_obj = _make_dummy_obj(self.folder / "equipment.obj")

    def tearDown(self):
        self.temp_dir.cleanup()
        unregister_model_inspector_ui()

    def test_inspect_object_materials(self):
        """Test material base color and missing texture extraction."""
        imported = load_preview_obj_model(
            self.dummy_obj,
            name="TestEquipment",
            position=(0.0, 0.0, 1.0),
        )
        self.assertTrue(len(imported) >= 1)
        obj = imported[0]
        mats = inspect_object_materials(obj)
        self.assertTrue(len(mats) >= 1)
        first_mat = mats[0]
        self.assertIn("name", first_mat)
        self.assertIn("base_color", first_mat)
        self.assertIn("missing_textures", first_mat)
        # Should detect the non-existent texture
        self.assertTrue(len(first_mat["missing_textures"]) >= 1)

    def test_get_object_bounds_and_dimensions(self):
        """Test bounding box and dimension calculation."""
        imported = load_preview_obj_model(
            self.dummy_obj,
            name="TestEquipment",
            position=(1.0, 2.0, 3.0),
        )
        self.assertTrue(len(imported) >= 1)
        bounds = get_object_bounds_and_dimensions(imported[0])
        dim = bounds["dimensions"]
        # Quad is 1.0 x 1.0
        self.assertAlmostEqual(dim[0], 1.0, places=2)
        self.assertAlmostEqual(dim[1], 1.0, places=2)
        self.assertEqual(bounds["vertex_count"], 4)

    def test_create_reference_cage_mesh(self):
        """Test cage mesh creation from .amodel file."""
        objs = create_reference_cage_mesh(self.dummy_model)
        self.assertTrue(len(objs) >= 1)
        membrane_obj = next((o for o in objs if o.get("is_preview_cage")), None)
        self.assertIsNotNone(membrane_obj)
        self.assertEqual(len(membrane_obj.data.polygons), 6)

    def test_create_water_surface_plane(self):
        """Test water surface reference plane creation at specific Z."""
        water = create_water_surface_plane(water_level_z=1.75, size=40.0)
        self.assertIsNotNone(water)
        self.assertEqual(water.name, WATER_PLANE_NAME)
        self.assertAlmostEqual(water.location.z, 1.75, places=3)

    def test_build_model_preview_scene(self):
        """Test complete preview scene assembly."""
        config = {
            "model_path": str(self.dummy_model),
            "water_level_z": 0.0,
            "include_water": True,
            "obj_models": [
                {
                    "path": str(self.dummy_obj),
                    "name": "Custom_Sensor",
                    "position": [0.0, 0.0, 2.5],
                }
            ],
            "setup_camera": True,
            "setup_lighting": True,
            "setup_ui": True,
        }
        summary = build_model_preview_scene(config)

        self.assertGreaterEqual(summary["total_models"], 2)
        self.assertTrue(len(summary["cage_objects"]) >= 1)
        self.assertTrue(len(summary["obj_objects"]) >= 1)
        self.assertEqual(summary["water_surface"], WATER_PLANE_NAME)

        # Check collection exists
        col = bpy.data.collections.get(PREVIEW_COLLECTION_NAME)
        self.assertIsNotNone(col)

        # Check camera and lights exist
        self.assertIsNotNone(bpy.data.objects.get("Preview_Camera"))
        self.assertIsNotNone(bpy.data.objects.get("Preview_Key_Sun"))

    def test_operators_execution(self):
        """Test focus, copy transform, and toggle water operators."""
        register_model_inspector_ui()

        water = create_water_surface_plane(water_level_z=0.0)
        self.assertFalse(water.hide_viewport)

        # Toggle water
        bpy.ops.sim2blender.toggle_water_surface()
        self.assertTrue(water.hide_viewport)
        bpy.ops.sim2blender.toggle_water_surface()
        self.assertFalse(water.hide_viewport)

        # Focus model
        imported = load_preview_obj_model(
            self.dummy_obj,
            name="FocusTarget",
            position=(5.0, 5.0, 5.0),
        )
        self.assertTrue(len(imported) >= 1)
        res = bpy.ops.sim2blender.focus_model(object_name=imported[0].name)
        self.assertEqual(res, {"FINISHED"})
        self.assertEqual(bpy.context.view_layer.objects.active.name, imported[0].name)

        # Copy transform
        res_copy = bpy.ops.sim2blender.copy_model_transform(object_name=imported[0].name)
        self.assertEqual(res_copy, {"FINISHED"})
        self.assertIn("position=", bpy.context.scene.get("last_copied_transform", ""))


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv += sys.argv[sys.argv.index("--") + 1:]
    unittest.main(argv=argv)
