"""Blender integration tests for replaceable static fish assets."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src'))
import bpy
from mathutils import Vector
from sim2blender.blender.fish.assets import load_fish_template
from sim2blender.blender.fish.school import add_fish_school
from sim2blender.blender.enclosure import Enclosure
from sim2blender.blender.scene import mesh_object


class FishAssetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/'species.blend'
        points = [(x,y,z) for z in (-.2,.2) for y in (-2,2) for x in (-1,1)]
        self.faces = [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
        self.asset = mesh_object('SpeciesMesh', points, [], self.faces, bpy.context.scene.collection)
        material = bpy.data.materials.new('Species coloration')
        material.diffuse_color = (.8,.1,.3,1)
        self.asset.data.materials.append(material)
        self.asset.location = (10,20,30)
        bpy.context.view_layer.update()
        bpy.data.libraries.write(str(self.path), {self.asset})

    def tearDown(self):
        bpy.data.objects.remove(self.asset, do_unlink=True)
        self.directory.cleanup()

    def test_size_center_material_and_clearance(self):
        template = load_fish_template(.8, self.path, 'SpeciesMesh')
        points = [v.co for v in template.mesh.vertices]
        self.assertAlmostEqual(max(p.x for p in points)-min(p.x for p in points), .8)
        self.assertLess(abs(max(points,key=lambda p:p.x).x + min(points,key=lambda p:p.x).x), 1e-5)
        self.assertTrue(all(p.length < template.clearance_radius for p in points))
        self.assertGreater(template.clearance_radius, .8*.6)
        self.assertAlmostEqual(template.mesh.materials[0].diffuse_color[0], .8)
        self.assertTrue(template.custom)

    def test_custom_school_uses_geometry_clearance(self):
        points = [(x,y,z) for z in (-5,5) for y in (-5,5) for x in (-5,5)]
        cage = mesh_object('Asset enclosure', points, [], self.faces, bpy.context.scene.collection)
        fish = add_fish_school(cage, self.faces, 5, 3, .8, .6, fish_asset=self.path, fish_object='SpeciesMesh', species='test species')
        self.assertIs(fish[0].data, fish[1].data)
        self.assertEqual(bpy.context.scene['fish_species'], 'test species')
        radius = bpy.context.scene['fish_clearance_radius']
        volume = Enclosure(points, self.faces)
        for frame in (1,2,3):
            bpy.context.scene.frame_set(frame)
            self.assertTrue(all(volume.contains(f.location, radius) for f in fish))
        self.assertTrue(fish[0]['fish_asset_custom'])
        from sim2blender.blender.geometry import round_net
        from sim2blender.blender.scene import setup_view
        from sim2blender.blender.shading import apply_visualization
        cage.name = 'Membrane cage'
        cage.data.materials.append(bpy.data.materials.new('Net strands'))
        round_net(cage, [dict(nodes=f, geometry=dict(diameter=.002, mesh_width_y=.025, mesh_width_z=.025)) for f in self.faces], list(range(8)))
        setup_view(bpy.context.scene, points, bpy.context.scene.collection)
        apply_visualization(bpy.context.scene, cage)
        self.assertAlmostEqual(fish[0].data.materials[0].diffuse_color[0], .8)

    def test_bad_asset_and_name_rejected(self):
        with self.assertRaises(ValueError):
            load_fish_template(.6, self.path, 'missing')
        with self.assertRaises(ValueError):
            load_fish_template(.6, self.path.with_suffix('.obj'))

    def test_animated_asset_rejected(self):
        self.asset.keyframe_insert('location', frame=1)
        bpy.data.libraries.write(str(self.path), {self.asset})
        with self.assertRaisesRegex(ValueError, 'static mesh'):
            load_fish_template(.6, self.path, 'SpeciesMesh')


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FishAssetTests))
if not result.wasSuccessful():
    raise RuntimeError('Fish asset tests failed')
