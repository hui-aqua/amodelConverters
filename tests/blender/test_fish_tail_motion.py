"""Blender integration tests for procedural fish tail swimming motion (Geometry Nodes)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.fish.salmon import salmon_mesh
    from sim2blender.blender.fish.tail_motion import (
        MODIFIER_NAME,
        NODE_GROUP_NAME,
        get_or_create_fish_tail_node_group,
        apply_fish_tail_motion,
    )
    from sim2blender.blender.fish.school import add_fish_school
    from sim2blender.blender.scene import mesh_object
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class FishTailMotionTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.scene.render.fps = 25
        self.scene.frame_start = 1
        self.scene.frame_end = 50

    def test_node_group_creation(self):
        tree = get_or_create_fish_tail_node_group()
        self.assertIsNotNone(tree)
        self.assertEqual(tree.name, NODE_GROUP_NAME)
        self.assertEqual(tree.type, "GEOMETRY")

        # Reuse existing tree if called again
        tree_again = get_or_create_fish_tail_node_group()
        self.assertIs(tree, tree_again)

    def test_apply_tail_motion_modifier(self):
        mesh = salmon_mesh(0.775)
        fish_obj = bpy.data.objects.new("TestFish", mesh)
        self.scene.collection.objects.link(fish_obj)

        mod = apply_fish_tail_motion(
            fish_obj,
            length=0.775,
            amplitude=0.065,
            frequency=2.2,
            phase=0.5,
        )
        self.assertIsNotNone(mod)
        self.assertEqual(mod.name, MODIFIER_NAME)
        self.assertEqual(mod.type, "NODES")
        self.assertEqual(mod.node_group.name, NODE_GROUP_NAME)

    def test_tail_undulation_deformation(self):
        mesh = salmon_mesh(0.775)
        fish_obj = bpy.data.objects.new("TestFishDeform", mesh)
        self.scene.collection.objects.link(fish_obj)

        apply_fish_tail_motion(
            fish_obj,
            length=0.775,
            amplitude=0.065,
            frequency=2.2,
            phase=0.0,
        )

        # Evaluate at frame 2 (t=0.08s, left crest)
        self.scene.frame_set(2)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj2 = fish_obj.evaluated_get(depsgraph)
        mesh2 = eval_obj2.to_mesh()
        pts_f2 = [v.co.copy() for v in mesh2.vertices]
        eval_obj2.to_mesh_clear()

        # Evaluate at frame 7 (t=0.28s, right crest, half-period later)
        self.scene.frame_set(7)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj7 = fish_obj.evaluated_get(depsgraph)
        mesh7 = eval_obj7.to_mesh()
        pts_f7 = [v.co.copy() for v in mesh7.vertices]
        eval_obj7.to_mesh_clear()

        # Check caudal fin lateral deflection (x < -0.35m)
        tail_diffs = [abs(p7.y - p2.y) for p2, p7 in zip(pts_f2, pts_f7) if p2.x < -0.35]
        self.assertTrue(len(tail_diffs) > 0)
        max_tail_deflection = max(tail_diffs)
        self.assertGreater(max_tail_deflection, 0.08, f"Expected tail peak deflection > 0.08m, got {max_tail_deflection:.4f}m")

        # Check head stability (x > 0.35m)
        head_diffs = [abs(p7.y - p2.y) for p2, p7 in zip(pts_f2, pts_f7) if p2.x > 0.35]
        self.assertTrue(len(head_diffs) > 0)
        max_head_deflection = max(head_diffs)
        self.assertLess(max_head_deflection, 0.02, f"Head should remain steady, got {max_head_deflection:.4f}m")

    def test_school_with_and_without_tail_motion(self):
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        points = [(x, y, z) for z in (-5, 5) for y in (-5, 5) for x in (-5, 5)]
        cage = mesh_object("SchoolEnclosure", points, [], faces, self.scene.collection)

        # School with tail motion enabled
        fish_school = add_fish_school(
            cage, faces, fish_count=4, frames=2, fish_length=0.775, tail_motion=True
        )
        for f in fish_school:
            self.assertIn(MODIFIER_NAME, f.modifiers)

        # Clean up
        for f in fish_school:
            bpy.data.objects.remove(f, do_unlink=True)
        old_col = bpy.data.collections.get("Fish school")
        if old_col:
            bpy.data.collections.remove(old_col)

        # School with tail motion disabled
        fish_school_no_tail = add_fish_school(
            cage, faces, fish_count=4, frames=2, fish_length=0.775, tail_motion=False
        )
        for f in fish_school_no_tail:
            self.assertNotIn(MODIFIER_NAME, f.modifiers)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FishTailMotionTests)
    )
    if not result.wasSuccessful():
        sys.exit(1)
