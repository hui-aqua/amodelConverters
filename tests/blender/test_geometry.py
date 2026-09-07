"""Blender geometry regression tests. Run with --python-exit-code 1."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import unittest
import math
import inspect
import xml.etree.ElementTree as ET
import bpy
from mathutils import Vector
from sim2blender.amodel import read_model
from sim2blender.geometry import component_geometry
from sim2blender.blender.geometry import member_mesh, local_frame, round_net
from sim2blender.blender.build import mesh_object, add_fish_school


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=read_model(Path('examples/models/winch_cage.amodel'))
        cls.cells={c['component_id']:c for c in cls.model.cells}

    def test_floater_and_wall_units(self):
        g=self.cells[1]['geometry']
        self.assertAlmostEqual(g['diameter'],.5)
        self.assertAlmostEqual(g['wall_thickness'],.5/13.6,places=7)
        g=self.cells[4]['geometry']
        self.assertAlmostEqual(g['diameter'],.5)
        self.assertAlmostEqual(g['wall_thickness'],.045454545)
        g=self.cells[7]['geometry']
        self.assertAlmostEqual(g['diameter'],.355)
        self.assertAlmostEqual(g['wall_thickness'],.017)

    def test_profile_symmetry_and_section_offset(self):
        g=self.cells[2]['geometry']
        self.assertEqual(g['kind'],'profile')
        self.assertEqual(len(g['profile']),16)
        self.assertAlmostEqual(g['width'],.25)
        self.assertAlmostEqual(g['height'],.5)
        thin=self.cells[6]['geometry']
        self.assertEqual(thin['kind'],'profile')
        self.assertAlmostEqual(thin['width'],.002)
        self.assertAlmostEqual(thin['height'],.1)
        xml=ET.fromstring('<beam><crossection symmetry="true"><points><point x="0" y="1"/><point x="2" y="1"/><point x="2" y="0"/><point x="0" y="0"/></points></crossection></beam>')
        g=component_geometry(xml)
        self.assertAlmostEqual(g['width'],4)
        self.assertAlmostEqual(g['height'],1)
        self.assertEqual(min(p[1] for p in g['profile']),0)

    def test_orientation_and_member_dimensions(self):
        x,y,z,fallback=local_frame((0,0,0),(2,0,0),(0,1,0))
        self.assertFalse(fallback)
        self.assertLess((z-Vector((0,1,0))).length,1e-6)
        g=self.cells[2]['geometry']
        points,faces,_=member_mesh((0,0,0),(2,0,0),g,(0,1,0))
        self.assertAlmostEqual(max(p.y for p in points)-min(p.y for p in points),.5)
        self.assertAlmostEqual(max(p.z for p in points)-min(p.z for p in points),.25)
        self.assertEqual(min(p.x for p in points),0)
        self.assertEqual(max(p.x for p in points),2)

    def test_tube_inner_outer_surface(self):
        g=self.cells[4]['geometry']
        points,faces,_=member_mesh((0,0,0),(2,0,0),g,(0,0,1))
        radii=[math.hypot(p.y,p.z) for p in points]
        self.assertAlmostEqual(max(radii),.25,places=6)
        self.assertAlmostEqual(min(radii),.25-g['wall_thickness'],places=6)
        self.assertEqual(len(faces),128)

    def test_rope_diameters_and_envelope(self):
        for cid,diameter in [(29,.01),(52,.012),(32,.024),(25,.03),(48,.056),(49,.096)]:
            g=self.cells[cid]['geometry']
            self.assertAlmostEqual(g['diameter'],diameter)
            points,_,_=member_mesh((0,0,0),(2,0,0),g,(0,0,1))
            radii=[math.hypot(p.y,p.z) for p in points]
            self.assertAlmostEqual(max(radii),diameter/2,places=6)
            self.assertLess(min(radii),max(radii)*.95)
        self.assertEqual(inspect.signature(add_fish_school).parameters['fish_count'].default,1000)

    def test_round_net_diameter(self):
        cage=mesh_object('Net radius test',[(0,0,0),(2,0,0)],[(0,1)],[],bpy.context.scene.collection)
        cage.data.materials.append(bpy.data.materials.new('test'))
        g=dict(diameter=.02,mesh_width_y=.1,mesh_width_z=.1)
        round_net(cage,[dict(nodes=(0,1),geometry=g)],(0,1))
        bpy.context.view_layer.update()
        mesh=cage.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        self.assertGreater(len(mesh.vertices),0)
        self.assertAlmostEqual(max(v.co.y for v in mesh.vertices)-min(v.co.y for v in mesh.vertices),.02,places=5)
        self.assertAlmostEqual(self.cells[12]['geometry']['diameter'],.00185)
        self.assertAlmostEqual(self.cells[12]['geometry']['mesh_width_y'],.024)


r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GeometryTests))
if not r.wasSuccessful():raise RuntimeError('Geometry tests failed')
