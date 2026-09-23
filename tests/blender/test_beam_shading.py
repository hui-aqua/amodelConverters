"""Run in background Blender; optionally render the three-way comparison."""
import sys, json, math, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
try:
    import bpy
    from mathutils import Vector
    from sim2blender.blender.geometry import member_mesh
    from sim2blender.blender.scene import mesh_object
    from sim2blender.blender.beam_shading import preprocess_hdpe_beams
    from sim2blender.blender.shading import principled
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False


def pipe(name, length=.55, hollow=True):
    r=.25
    g=dict(kind='tube',diameter=2*r,wall_thickness=.035 if hollow else 0,
           profile=[(r*math.cos(i*math.tau/32),r*math.sin(i*math.tau/32)) for i in range(32)])
    points,faces,_=member_mesh((0,0,0),(length,0,0),g)
    obj=mesh_object(name,points,[],faces,bpy.context.scene.collection)
    obj['component_type']='beam'
    obj['source_geometry_json']=json.dumps(g)
    for f in obj.data.polygons: f.use_smooth=len(f.vertices)==4
    return obj


def snapshot(obj):
    m=obj.data
    return (obj.name,tuple(tuple(v.co) for v in m.vertices),tuple(tuple(e.vertices) for e in m.edges),
            tuple(tuple(f.vertices) for f in m.polygons),tuple(obj.matrix_world),dict(obj.items()))


@unittest.skipUnless(HAS_BLENDER, "Blender (bpy) is not available in current Python environment")
class BeamShadingTests(unittest.TestCase):
    def test_imported_model_and_thousand_segments(self):
        import time
        from sim2blender.io.aquasim.model import read_model
        from sim2blender.core.paths import PROJECT_ROOT
        from sim2blender.blender.geometry import build_members
        collection=bpy.data.collections.new('Imported beam test')
        bpy.context.scene.collection.children.link(collection)
        build_members(read_model(PROJECT_ROOT/'examples/models/winch_cage.amodel'),collection,tags=('beam',))
        originals={obj:snapshot(obj) for obj in collection.objects}
        result=preprocess_hdpe_beams(collection.objects)
        self.assertGreater(result['processed'],0)
        for obj,before in originals.items():self.assertEqual(snapshot(obj),before)
        for obj in list(collection.objects):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.collections.remove(collection)
        seed=pipe('Separate segment 0')
        segments=[seed]
        for i in range(999):
            obj=seed.copy();obj.data=seed.data.copy()
            bpy.context.scene.collection.objects.link(obj)
            segments.append(obj)
        started=time.perf_counter()
        result=preprocess_hdpe_beams(segments)
        elapsed=time.perf_counter()-started
        print(f'1000 separate segment meshes: {elapsed:.3f} seconds')
        self.assertEqual(result['processed'],1000)
        self.assertEqual(result['meshes_processed'],1000)
        self.assertEqual(result['modifiers_added'],0)
        for obj in segments:bpy.data.objects.remove(obj,do_unlink=True)

    def test_preservation_caps_and_repeatability(self):
        for hollow in (False,True):
            obj=pipe('Original AquaSim name',hollow=hollow)
            before=snapshot(obj)
            report=preprocess_hdpe_beams([obj])
            self.assertEqual(report['processed'],1)
            self.assertEqual(snapshot(obj),before)
            flags=([f.use_smooth for f in obj.data.polygons],[e.use_edge_sharp for e in obj.data.edges])
            self.assertEqual(sum(flags[0]),64 if hollow else 32)
            for f in obj.data.polygons:
                if abs(f.normal.x)>.99:
                    self.assertFalse(f.use_smooth)
                else:
                    self.assertTrue(f.use_smooth)
            preprocess_hdpe_beams([obj])
            self.assertEqual(flags,([f.use_smooth for f in obj.data.polygons],[e.use_edge_sharp for e in obj.data.edges]))
            self.assertEqual(len(obj.modifiers),0)
            bpy.data.objects.remove(obj,do_unlink=True)

    def test_selection_and_shared_data(self):
        obj=pipe('Beam')
        clone=bpy.data.objects.new('Shared',obj.data)
        bpy.context.scene.collection.objects.link(clone)
        self.assertEqual(preprocess_hdpe_beams([obj])['skipped'],1)
        clone['component_type']='beam';clone['source_geometry_json']=obj['source_geometry_json']
        result=preprocess_hdpe_beams([obj,clone])
        self.assertEqual(result['processed'],2)
        self.assertEqual(result['meshes_processed'],1)
        clone['component_type']='truss'
        self.assertEqual(preprocess_hdpe_beams([clone])['skipped'],1)
        bpy.data.objects.remove(clone,do_unlink=True)
        bpy.data.objects.remove(obj,do_unlink=True)

    def test_weighted_normal_comparison(self):
        obj=pipe('Weighted comparison')
        preprocess_hdpe_beams([obj])
        bpy.context.view_layer.update()
        def normals():
            ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            m=ev.to_mesh()
            result=[n.vector.copy() for n in m.corner_normals]
            ev.to_mesh_clear()
            return result
        plain=normals()
        mod=obj.modifiers.new('Comparison only','WEIGHTED_NORMAL')
        mod.keep_sharp=True
        bpy.context.view_layer.update()
        weighted=normals()
        delta=max((a-b).length for a,b in zip(plain,weighted))
        print('Weighted Normal maximum corner-normal delta:',delta)
        self.assertLess(delta,1e-5)
        bpy.data.objects.remove(obj,do_unlink=True)


def render_comparison():
    scene=bpy.context.scene
    for obj in list(scene.objects): bpy.data.objects.remove(obj,do_unlink=True)
    mat=bpy.data.materials.new('Comparison black HDPE')
    principled(mat,(.005,.005,.005),.5,0)
    for row in range(3):
        for i in range(7):
            obj=pipe(f'row{row}_segment{i}')
            obj.location=(i*.55-1.9,0,(2-row)*.85)
            obj.data.materials.append(mat)
            if row>0:preprocess_hdpe_beams([obj])
            if row==2:
                mod=obj.modifiers.new('Weighted Normal comparison','WEIGHTED_NORMAL');mod.keep_sharp=True
    camera=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'))
    scene.collection.objects.link(camera)
    camera.location=(3,-9,4)
    camera.rotation_euler=(Vector((0,0,.85))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=5.4;scene.camera=camera
    light=bpy.data.objects.new('Softbox',bpy.data.lights.new('Softbox','AREA'))
    scene.collection.objects.link(light);light.location=(0,-3,6);light.data.energy=1500;light.data.shape='RECTANGLE';light.data.size=6;light.data.size_y=4
    light.rotation_euler=(Vector((0,0,.85))-light.location).to_track_quat('-Z','Y').to_euler()
    scene.world.color=(.15,.15,.15)
    scene.render.engine='CYCLES';scene.cycles.samples=32
    scene.render.resolution_x=1100;scene.render.resolution_y=700;scene.render.resolution_percentage=100
    scene.render.filepath=str(Path('output/hdpe_shading_comparison.png').resolve())
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path('output/hdpe_shading_comparison.blend').resolve()))

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BeamShadingTests))
    if not result.wasSuccessful():raise RuntimeError('Beam shading tests failed')
    if '--render-comparison' in sys.argv:render_comparison()
