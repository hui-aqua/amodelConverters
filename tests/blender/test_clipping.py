"""Render the moving height mask and verify pixels after save/reload."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
try:
    import bpy
    from sim2blender.blender.clipping import apply_height_mask
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, 'Blender required')
class ClippingTests(unittest.TestCase):
    def test_animated_world_height_render(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.object
        cube.location.z = 0
        cube.keyframe_insert('location', frame=1)
        cube.location.z = 1
        cube.keyframe_insert('location', frame=2)
        mat = bpy.data.materials.new('Emission')
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        emission = nodes.new('ShaderNodeEmission')
        mat.node_tree.links.new(emission.outputs[0], nodes.get('Material Output').inputs['Surface'])
        cube.data.materials.append(mat)
        bpy.ops.object.camera_add(location=(0,-6,0), rotation=(1.57079632679,0,0))
        scene.camera = bpy.context.object
        scene.camera.data.type = 'ORTHO'
        scene.camera.data.ortho_scale = 4
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 1
        scene.cycles.use_denoising = False
        scene.render.resolution_x = scene.render.resolution_y = 64
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.image_settings.color_mode = 'RGBA'
        apply_height_mask(scene)
        with tempfile.TemporaryDirectory() as directory:
            blend = str(Path(directory)/'mask.blend')
            bpy.ops.wm.save_as_mainfile(filepath=blend)
            bpy.ops.wm.open_mainfile(filepath=blend)
            scene = bpy.context.scene

            def alpha(frame):
                scene.frame_set(frame)
                scene.render.filepath = str(Path(directory)/'test.png')
                bpy.ops.render.render(write_still=True)
                image = bpy.data.images.load(scene.render.filepath, check_existing=False)
                values = list(image.pixels)
                bpy.data.images.remove(image)
                return lambda y: values[(y*64+32)*4+3]

            pixels = alpha(1)
            self.assertGreater(pixels(24), 0.9)
            self.assertGreater(pixels(34), 0.9)
            self.assertLess(pixels(39), 0.1)
            pixels = alpha(2)
            self.assertGreater(pixels(34), 0.9)
            self.assertLess(pixels(24), 0.1)
            self.assertLess(pixels(39), 0.1)
            scene['replay_clip_z_m'] = 0.8
            scene.update_tag()
            self.assertGreater(alpha(2)(39), 0.9)
            scene['replay_clip_enabled'] = False
            scene.update_tag()
            self.assertGreater(alpha(2)(50), 0.9)
            scene.render.engine = 'BLENDER_EEVEE'
            scene['replay_clip_enabled'] = True
            scene['replay_clip_z_m'] = 0.26
            scene.update_tag()
            pixels = alpha(1)
            self.assertGreater(pixels(24), 0.9)
            self.assertLess(pixels(39), 0.1)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
