import sys, json, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.geometry import member_mesh
    from sim2blender.blender.scene import mesh_object
    from sim2blender.blender.rope_shading import preprocess_rope_segments
    from sim2blender.blender.shading import studio
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class RopeShadingTests(unittest.TestCase):
    def test_independent_segments_and_caps(self):
        objects=[]
        for i,length in enumerate((.2,.35,.5)):
            g=dict(kind='rope',diameter=.1)
            points,faces,_=member_mesh((0,0,0),(length,0,0),g)
            obj=mesh_object('Source rope '+str(i),points,[],faces,bpy.context.scene.collection)
            obj['component_type']='truss';obj['source_geometry_json']=json.dumps(g)
            objects.append(obj)
        before=[(o.name,[tuple(v.co) for v in o.data.vertices],[tuple(f.vertices) for f in o.data.polygons]) for o in objects]
        self.assertEqual(preprocess_rope_segments(objects)['processed'],3)
        for obj in objects:
            for face in obj.data.polygons:
                for li in face.loop_indices:
                    normal=obj.data.corner_normals[li].vector
                    if len(face.vertices)>4:
                        self.assertFalse(face.use_smooth)
                        self.assertGreater(abs(normal.x),.999)
                    else:
                        p=obj.data.vertices[obj.data.loops[li].vertex_index].co
                        expected=Vector((0,p.y,p.z)).normalized()
                        self.assertLess((normal-expected).length,1e-3)
            self.assertEqual(len(obj.modifiers),0)
        preprocess_rope_segments(objects)
        self.assertEqual(before,[(o.name,[tuple(v.co) for v in o.data.vertices],[tuple(f.vertices) for f in o.data.polygons]) for o in objects])

    def test_studio_does_not_touch_hdpe(self):
        cage=mesh_object('Membrane cage',[(0,0,0),(0,0,50)],[],[],bpy.context.scene.collection)
        beam=mesh_object('Untouched HDPE',[(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)],bpy.context.scene.collection)
        beam['component_type']='beam'
        mat=bpy.data.materials.new('Preserve HDPE');mat.diffuse_color=(.005,.005,.005,1)
        beam.data.materials.append(mat)
        before=(tuple(mat.diffuse_color),beam.data.polygons[0].use_smooth)
        studio(bpy.context.scene)
        self.assertEqual(before,(tuple(mat.diffuse_color),beam.data.polygons[0].use_smooth))
        self.assertEqual(bpy.context.scene.objects['Key softbox'].data.energy,45000)
        self.assertEqual(bpy.context.scene.view_settings.exposure,0)
        self.assertAlmostEqual(bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value,.2)
        studio(bpy.context.scene)
        self.assertEqual(bpy.context.scene.objects['Key softbox'].data.energy,45000)

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RopeShadingTests))
if not result.wasSuccessful():raise RuntimeError('Rope shading tests failed')
