"""Fish must follow a translating, shrinking AquaSim net, including its open top."""
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
try:
    import bpy
    from sim2blender.workflows.unified_pipeline import build_unified_scene
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, 'Blender required')
class SchoolReplayTests(unittest.TestCase):
    def test_invalid_shell_is_rejected(self):
        from sim2blender.blender.scene import mesh_object
        from sim2blender.blender.fish.boundary import AnimatedCageBoundary
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cage = mesh_object('Membrane cage', [(0,0,0),(1,0,0),(0,1,0),(-1,0,0),(0,-1,0)],
                           [], [(0,1,2),(0,3,4)], bpy.context.scene.collection)
        with self.assertRaisesRegex(ValueError, 'branched'):
            AnimatedCageBoundary(cage)

    def test_display_restored_when_fish_cannot_fit(self):
        from sim2blender.blender.fish.school import run_fish_schooling
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.mesh.primitive_cube_add(size=2)
        cage = bpy.context.object
        cage.name = 'Membrane cage'
        display = cage.modifiers.new('Finite element net strands', 'WIREFRAME')
        bpy.context.scene.frame_end = 1
        with self.assertRaisesRegex(ValueError, 'No safe fish position'):
            run_fish_schooling(dict(fish_count=1,fish_length_mean_m=20,fish_length_std_m=0))
        self.assertTrue(display.show_viewport)

    def test_failed_projection_does_not_accept_outside_position(self):
        import random
        from unittest.mock import patch
        from mathutils import Vector
        from sim2blender.blender.fish.boundary import AnimatedCageBoundary, safe_fish_position
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.mesh.primitive_cube_add(size=4)
        with AnimatedCageBoundary(bpy.context.object) as boundary:
            enclosure = boundary.enclosure_at(1)
        outside = Vector((10,0,0))
        with patch('sim2blender.blender.fish.school.project_inside_enclosure', return_value=outside):
            position = safe_fish_position(outside, .3, enclosure, random.Random(7))
        self.assertTrue(enclosure.contains(position, .3))

    def run_moving_net(self, feeding=False):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        points = [(x,y,z) for z in (-2,2) for y in (-2,2) for x in (-2,2)]
        # Open top; the containment cap is virtual, not rendered net strands.
        faces = [(0,1,3,2),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            model, result, output = (folder/name for name in ('net.amodel','out.txt','school.blend'))
            nodes = ''.join(f'<node id="{i+100}" x="{x}" y="{y}" z="{z}"/>' for i,(x,y,z) in enumerate(points))
            elements = ''.join('<element id="{}" {}/>'.format(i, ' '.join(
                f'node{axis}="{n+100}"' for axis,n in zip('ABCD',face))) for i,face in enumerate(faces))
            model.write_text(f'<model><Nodes>{nodes}</Nodes><Components><membrane id="1" active="true" diameter="0.003"><elements>{elements}</elements></membrane></Components></model>')
            result.write_text('Time [-] VID [-] X Y Z\n' + ''.join(
                f'{step} {i+1} {x*(1-step*.15)+step*2} {y*(1-step*.15)} {z*(1-step*.15)}\n'
                for step in range(3) for i,(x,y,z) in enumerate(points)))
            config = dict(model=str(model),output=str(output),
                replay=dict(enabled=True,results=str(result),wave_period=5,frames_per_wave=40,fps=25),
                fish_schooling=dict(enabled=True,fish_count=12,fish_length_mean_m=.3,
                                   fish_length_std_m=.025,tail_motion=True,tail_amplitude_m=.04))
            if feeding:
                config['fish_feeding'] = dict(config.pop('fish_schooling'))
            build_unified_scene(config)
            bpy.ops.wm.open_mainfile(filepath=str(output))
            scene = bpy.context.scene
            fish = [obj for obj in scene.objects if obj.name.startswith('Fish_')]
            self.assertEqual(len(fish), 12)
            checks = sorted(set([1+i*.25 for i in range(29)] + [4.125,7.25]))
            for frame in checks:
                scene.frame_set(math.floor(frame),subframe=frame-math.floor(frame))
                step = min((frame-1)/3.125,2)
                half = 2*(1-step*.15)
                center = step*2
                graph = bpy.context.evaluated_depsgraph_get()
                for obj in fish:
                    evaluated = obj.evaluated_get(graph)
                    # Verify the full undulating fish, not just its center.
                    for vertex in evaluated.data.vertices:
                        p = evaluated.matrix_world @ vertex.co
                        self.assertLessEqual(abs(p.x-center),half+1e-5, f'{obj.name} outside at {frame}')
                        self.assertLessEqual(abs(p.y),half+1e-5)
                        self.assertLessEqual(abs(p.z),half+1e-5)

    def test_schooling_tracks_replay(self):
        self.run_moving_net()

    def test_feeding_tracks_replay(self):
        self.run_moving_net(feeding=True)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + (sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []))
