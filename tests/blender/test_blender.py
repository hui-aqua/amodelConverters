"""Run with Blender --background --python tests/test_blender.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import unittest
from mathutils import Vector
from sim2blender.blender.build import Enclosure, boundary_caps, mesh_object, constrain_axes, add_fish_school, stitch_membrane_seams
from sim2blender.amodel import Node
import bpy


class BlenderTests(unittest.TestCase):
    def setUp(self):
        self.points = [(x,y,z) for z in (-1,1) for y in (-1,1) for x in (-1,1)]
        self.faces = [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]

    def test_whole_fish_and_caps(self):
        box = Enclosure(self.points, self.faces)
        self.assertTrue(box.contains((0,0,0), .3))
        self.assertFalse(box.contains((.9,0,0), .3))
        self.assertFalse(box.contains((2,0,0)))
        with self.assertRaisesRegex(ValueError, 'open'):
            boundary_caps(self.faces[1:], self.points)
        caps = boundary_caps(self.faces[1:], self.points, True)
        self.assertEqual(len(caps),1)
        self.assertTrue(Enclosure(self.points,self.faces[1:]+caps).contains((0,0,0)))
        with self.assertRaisesRegex(ValueError, 'Nonmanifold'):
            boundary_caps(self.faces+self.faces[:1],self.points,True)

    def test_concavity(self):
        outline = [(0,0),(3,0),(3,1),(1,1),(1,3),(0,3)]
        points = [(x,y,z) for z in (0,2) for x,y in outline]
        faces = [tuple(range(6)),tuple(range(6,12))] + [(i,(i+1)%6,(i+1)%6+6,i+6) for i in range(6)]
        volume = Enclosure(points,faces)
        self.assertTrue(volume.contains((.5,2,1),.1))
        self.assertFalse(volume.contains((2,2,1)))

    def test_nonconforming_seam(self):
        points = self.points + [(0, -1, -1)]
        faces = list(self.faces)
        faces[2] = (0, 4, 5, 1, 8)
        with self.assertRaises(ValueError):
            boundary_caps(faces, points, True)
        stitched = stitch_membrane_seams(faces, points)
        self.assertEqual(len(stitched), len(faces))
        self.assertEqual(stitched[0], (0, 8, 1, 3, 2))
        self.assertEqual(boundary_caps(stitched, points), [])
        self.assertTrue(Enclosure(points, stitched).contains((0, 0, 0), .3))
        # A displaced seam must not be silently joined.
        points[8] = (0, -1.01, -1)
        self.assertEqual(stitch_membrane_seams(faces, points), faces)

    def test_riktig_membrane_seam(self):
        from sim2blender.amodel import read_model, PROJECT_ROOT
        model = read_model(PROJECT_ROOT/'examples/models/riktig_amodel_ULS.amodel')
        cells = [c for c in model.cells if c['component_tag'] == 'membrane']
        ids = sorted({n for c in cells for n in c['nodes']})
        index = {n: i for i, n in enumerate(ids)}
        points = [model.nodes[n].point for n in ids]
        faces = [tuple(index[n] for n in c['nodes']) for c in cells]
        stitched = stitch_membrane_seams(faces, points)
        self.assertEqual(sum(map(len, stitched))-sum(map(len, faces)), 180)
        caps = boundary_caps(stitched, points, True)
        self.assertEqual(len(caps), 1)
        self.assertTrue(Enclosure(points, stitched+caps).contains((0, 0, -10), .36))

    def test_translated_volume_and_ambiguous_ray(self):
        shifted = [Vector(p)+Vector((1000,1000,-1000)) for p in self.points]
        box = Enclosure(shifted,self.faces)
        self.assertTrue(box.contains((1000,1000,-1000),.3))
        self.assertFalse(box.contains((1000.9,1000,-1000),.3))
        class RepeatedHit:
            def find_nearest(self, point):
                return Vector((1,0,0)),Vector((1,0,0)),0,1
            def ray_cast(self, origin, direction):
                return Vector((1,0,0)),Vector((1,0,0)),0,0
        box.bvh=RepeatedHit()
        self.assertFalse(box.contains((1000,1000,-1000),.3))

    def test_axis_constraints_and_school(self):
        obj = mesh_object('Test cage', self.points, [], self.faces, bpy.context.scene.collection)
        nodes = [Node(i,p,(False,True,False)) for i,p in enumerate(self.points)]
        constrain_axes(obj,nodes)
        obj.data.vertices[0].co += Vector((.2,.2,.2))
        bpy.context.view_layer.update()
        result = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices[0].co
        self.assertAlmostEqual(result.x,-1)
        self.assertAlmostEqual(result.y,-.8)
        self.assertAlmostEqual(result.z,-1)
        fish = add_fish_school(obj,self.faces,fish_count=3,frames=3,fish_length=.2)
        self.assertEqual(len(fish),3)
        for frame in (1,2,3):
            bpy.context.scene.frame_set(frame)
            mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
            volume = Enclosure([v.co for v in mesh.vertices],self.faces)
            self.assertTrue(all(volume.contains(f.location,.12) for f in fish))
        self.assertNotEqual(tuple(fish[0].location), (0,0,0))

    def test_fixed_vertex_cloth_pin(self):
        import tempfile
        from types import SimpleNamespace
        from sim2blender.blender.build import build
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'cube.amodel'
            nodes = ''.join(f'<node id="{i}" x="{p[0]}" y="{p[1]}" z="{p[2]}" translate="{"false" if i == 0 else "true"}"/>' for i,p in enumerate(self.points))
            elements = ''.join('<element id="{}" {}/>'.format(i, ' '.join(f'node{a}="{n}"' for a,n in zip('ABCD',face))) for i,face in enumerate(self.faces))
            path.write_text(f'<model><Nodes>{nodes}</Nodes><Components><membrane id="1" active="true"><elements>{elements}</elements></membrane></Components></model>')
            cage = build(SimpleNamespace(input=path, output=Path(folder)/'test.blend', membrane_ids=None, cap_openings=False, pin_top=False, fish_count=0, fish_length=.2, speed=.6, frames=3, seed=7))
            self.assertEqual(cage.vertex_groups['Fixed nodes'].weight(0), 1)
            self.assertTrue(cage.modifiers['Cage cloth'].point_cache.is_baked)
            cage.modifiers['Visible net strands'].show_viewport = False
            bpy.context.scene.frame_set(3)
            mesh = cage.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
            self.assertLess((mesh.vertices[0].co-Vector(self.points[0])).length,1e-5)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(BlenderTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise RuntimeError('Blender tests failed')
