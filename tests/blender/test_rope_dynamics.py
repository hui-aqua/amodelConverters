"""Regression tests for deformable rope physics and attachments."""
import sys,unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import bpy
from mathutils import Vector
from sim2blender.amodel import Model,Node
from sim2blender.blender.build import mesh_object
from sim2blender.blender.ropes import rope_centerline,create_rope_cloth,rope_surface,rigid_beams,sample_node_motion


class RopeTests(unittest.TestCase):
    def model(self):
        nodes={i:Node(i,(float(i),0,0),(True,True,True)) for i in range(3)}
        geometry=dict(kind='rope',diameter=.03,area=.0007,source='test')
        cells=[dict(nodes=(i,i+1),component_id=1,component_name='Test rope',element_id=i+1,geometry=geometry) for i in range(2)]
        return Model(nodes,cells)

    def test_subdivision_and_shared_node(self):
        model=self.model();nodes,edges,lookup,ids=rope_centerline(model,model.cells)
        self.assertEqual(len(nodes),5)
        self.assertEqual(len(edges),4)
        self.assertEqual(sum(n.id==1 for n in nodes),1)
        self.assertEqual(sum(lookup[1] in e for e in edges),2)
        self.assertTrue(all((Vector(nodes[a].point)-Vector(nodes[b].point)).length<=.5 for a,b in edges))

    def test_cloth_sag_pins_and_surface(self):
        model=self.model()
        owners={0:[(0,0,0)]*30,2:[(2,0,0)]*30}
        obj,lookup=create_rope_cloth(model,model.cells,bpy.context.scene.collection,30,owners)
        bpy.context.scene.frame_set(30)
        mesh=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        self.assertLess(mesh.vertices[lookup[1]].co.z,-.001)
        self.assertLess(mesh.vertices[lookup[0]].co.length,1e-6)
        self.assertLess((mesh.vertices[lookup[2]].co-Vector((2,0,0))).length,1e-6)
        self.assertTrue(obj.modifiers['Rope cloth'].point_cache.is_baked)
        self.assertFalse(obj.modifiers['Rope cloth'].settings.use_sewing_springs)
        bpy.context.scene.frame_set(1)
        rope_surface(obj,.03);bpy.context.view_layer.update()
        self.assertEqual([m.type for m in obj.modifiers],['CLOTH','NODES'])
        mesh=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        self.assertGreater(len(mesh.polygons),0)
        self.assertAlmostEqual(max((v.co.y**2+v.co.z**2)**.5 for v in mesh.vertices),.015,places=5)

    def test_moving_attachment_and_fixed_source(self):
        model=self.model();model.nodes[0].translate=(False,False,False)
        trajectory=[(2,0,i*.01) for i in range(10)]
        obj,lookup=create_rope_cloth(model,model.cells,bpy.context.scene.collection,10,{2:trajectory})
        samples=sample_node_motion(obj,lookup,10)
        for a,b in zip(samples[2],trajectory):self.assertLess((Vector(a)-Vector(b)).length,1e-5)
        self.assertTrue(all(Vector(p).length<1e-6 for p in samples[0]))

    def test_beams_passive_rigid(self):
        collection=bpy.data.collections.new('Test rigid beams');bpy.context.scene.collection.children.link(collection)
        beam=mesh_object('Test beam',[(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)],collection)
        beam['component_type']='beam';rigid_beams(collection)
        self.assertEqual(beam.rigid_body.type,'PASSIVE')
        self.assertFalse(any(m.type=='CLOTH' for m in beam.modifiers))


r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RopeTests))
if not r.wasSuccessful():raise RuntimeError('Rope dynamics tests failed')
