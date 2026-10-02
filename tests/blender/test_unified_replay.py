"""Regression checks for structural replay and disabled calibrated camera import."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
try:
    import bpy
    from mathutils import Vector
    from sim2blender.workflows.unified_pipeline import build_unified_scene
    from sim2blender.blender.model_preview import import_checked_models_from_blend
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, 'Blender (bpy) is required')
class UnifiedReplayTests(unittest.TestCase):
    def test_replay_and_camera_filter(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            objects = []
            for name in ('Feeding_Camera', 'Feeding_Camera_Body',
                         'Feeding_Camera_Frustum', 'Feeding_Camera_HUD', 'Custom_Winch'):
                obj = bpy.data.objects.new(name, None)
                bpy.context.scene.collection.objects.link(obj)
                objects.append(obj)
            for obj in objects[1:4]:
                obj.parent = objects[0]
            checked = folder / 'checked.blend'
            bpy.data.libraries.write(str(checked), set(objects))
            bpy.ops.wm.read_factory_settings(use_empty=True)
            model = folder / 'test.amodel'
            model.write_text('''<model><Nodes>
                <node id="10" x="0" y="0" z="0"/>
                <node id="20" x="2" y="0" z="0"/>
                <node id="30" x="0" y="2" z="0"/>
                </Nodes><Components>
                <membrane id="1" active="true" diameter="0.002">
                <elements><element id="1" nodeA="10" nodeB="20" nodeC="30"/></elements></membrane>
                <beam id="2" active="true"><crossection><points>
                <point x="-0.1" y="-0.1"/><point x="0.1" y="-0.1"/>
                <point x="0.1" y="0.1"/><point x="-0.1" y="0.1"/>
                </points></crossection><elements><element id="2" StartNode_ID="10" EndNode_ID="20"/>
                <element id="4" StartNode_ID="10" EndNode_ID="30"/></elements></beam>
                <truss id="3" active="true"><mooring areal="0.000314159265"/>
                <elements><element id="3" StartNode_ID="10" EndNode_ID="20"/>
                <element id="5" StartNode_ID="10" EndNode_ID="30"/></elements></truss>
                </Components></model>''')
            results = folder / 'out.txt'
            # Rotation and extension, followed by translation; IDs intentionally differ.
            samples = [((0,0,0),(2,0,0),(0,2,0)),
                       ((1,1,1),(1,4,1),(-1,1,1)),
                       ((3,1,1),(3,4,1),(1,1,1))]
            results.write_text('Time [-] VID [-] X Y Z\n' + ''.join(
                f'{t} {i+1} {p[0]} {p[1]} {p[2]}\n'
                for t, sample in enumerate(samples) for i,p in enumerate(sample)))
            output = folder / 'replay.blend'
            build_unified_scene(dict(model=str(model), output=str(output),
                checked_blend_path=str(checked), feeding_camera={'enabled': False},
                replay=dict(enabled=True, results=str(results), fps=25,
                            wave_period=5, frames_per_wave=40,
                            clip_enabled=True, clip_z_m=0.26)))
            bpy.ops.wm.open_mainfile(filepath=str(output))
            self.assertFalse(any(o.name.startswith('Feeding_Camera') for o in bpy.data.objects))
            self.assertIn('Custom_Winch', bpy.context.scene.objects)
            scene = bpy.context.scene
            self.assertAlmostEqual(scene['replay_clip_z_m'], 0.26)
            self.assertTrue(scene['replay_clip_enabled'])
            members = [o for o in scene.objects if o.get('component_type') in ('beam','truss')]
            self.assertEqual(len(members), 2)
            for obj in members:
                self.assertIsNone(obj.data.shape_keys)
                control = scene.objects[obj['replay_control_object']]
                self.assertEqual(len(control.data.vertices), 8)
                self.assertEqual(len(control.data.shape_keys.key_blocks), 3)
                self.assertTrue(control.hide_render)
                self.assertTrue(control.hide_get())
            for frame, a, b, c in ((1, *samples[0]),
                                   (4.125, *samples[1]),
                                   (5.6875, (2,1,1), (2,4,1), (0,1,1)),
                                   (7.25, *samples[2])):
                scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
                for obj in members:
                    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
                    count = 4 if obj['component_type']=='beam' else 16
                    vertices = list(mesh.vertices)
                    per_element = len(vertices)//2
                    for offset, end in ((0, b), (per_element, c)):
                        for ring, expected in ((vertices[offset:offset+count], a),
                                               (vertices[offset+per_element-count:offset+per_element], end)):
                            center = sum((v.co for v in ring), Vector()) / count
                            self.assertLess((center-Vector(expected)).length, 1e-5)
                            # Both end sections retain their source size after rotation/extension.
                            radius = 0.1*math.sqrt(2) if count == 4 else 0.01
                            self.assertAlmostEqual((ring[0].co-center).length, radius, places=5)
                    self.assertIsNone(obj.rigid_body)
            # Enabling the option still restores the complete calibrated rig.
            imported = import_checked_models_from_blend(checked, include_feeding_camera=True)
            self.assertEqual(sum(o.name.startswith('Feeding_Camera') for o in imported), 4)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
