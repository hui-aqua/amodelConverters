"""Small end-to-end checks for both workflows with an appended fish asset."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src'))
import bpy
from sim2blender.workflows import model_physics, replay_geometry, replay_fish
from sim2blender.blender.scene import mesh_object
from sim2blender.blender.enclosure import Enclosure

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    points = [(x,y,z) for z in (-2,2) for y in (-2,2) for x in (-2,2)]
    faces = [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
    nodes = ''.join(f'<node id="{i+100}" x="{p[0]}" y="{p[1]}" z="{p[2]}" translate="false"/>' for i,p in enumerate(points))
    elements = ''.join('<element id="{}" {}/>'.format(i, ' '.join(f'node{a}="{n+100}"' for a,n in zip('ABCD',face))) for i,face in enumerate(faces))
    model = folder/'cube.amodel'
    model.write_text(f'<model><Nodes>{nodes}</Nodes><Components><membrane id="1" active="true" diameter="0.002" maskwidthy="0.025" maskwidthz="0.025"><elements>{elements}</elements></membrane></Components></model>')
    results = folder/'out.txt'
    results.write_text('Time [-] VID [-] X Y Z\n' + ''.join(f'{t} {i+1} {p[0]} {p[1]} {p[2]+t*.1}\n' for t in range(3) for i,p in enumerate(points)))
    asset = mesh_object('TestSpecies', [(p[0],p[1]*.3,p[2]*.2) for p in points], [], faces, bpy.context.scene.collection)
    asset.data.materials.append(bpy.data.materials.new('Test species material'))
    asset_path = folder/'fish.blend'
    bpy.data.libraries.write(str(asset_path), {asset})
    options = ['--fish-count','3','--fish-length','.2','--fish-asset',str(asset_path),'--fish-object','TestSpecies','--fish-species','test-species']
    physics_path = folder/'physics.blend'
    model_physics.main([str(model), '--frames','3','-o',str(physics_path), *options])
    assert physics_path.is_file()
    assert bpy.context.scene['fish_species'] == 'test-species'
    assert bpy.context.scene.objects['Fish_001']['fish_asset_custom']
    replay_path = folder/'replay.blend'
    replay_geometry.main([str(model),str(results),'-o',str(replay_path),'--fps','25','--step-seconds','.125'])
    assert bpy.context.scene.frame_end == 8
    styled_path = folder/'styled.blend'
    replay_fish.main(['-o',str(styled_path),'--skip-render',*options])
    bpy.ops.wm.open_mainfile(filepath=str(styled_path))
    scene = bpy.context.scene
    assert scene.render.fps == 25
    assert list(scene['source_frames']) == [1,4.125,7.25]
    assert scene['fish_species'] == 'test-species'
    cage = scene.objects['Membrane cage']
    fish = [o for o in scene.objects if o.name.startswith('Fish_')]
    assert len(fish) == 3 and all(o['fish_asset_custom'] for o in fish)
    assert all(o.data is fish[0].data for o in fish)
    for frame in range(1,9):
        scene.frame_set(frame)
        evaluated = cage.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            volume = Enclosure([v.co for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons])
            assert all(volume.contains(o.location, scene['fish_clearance_radius']) for o in fish)
        finally:
            evaluated.to_mesh_clear()
    assert abs(cage.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices[0].co.z + 1.8) < 1e-5
print('BOTH WORKFLOWS VERIFIED: custom asset, shared materials/mesh, fractional timing, saved replay and 24 fish containment checks', flush=True)
