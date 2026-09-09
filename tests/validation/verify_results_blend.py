"""Reopen a replay and compare evaluated centerlines with the source export."""
from collections import defaultdict
from bisect import bisect_right
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import bpy
from sim2blender.amodel import read_model
from sim2blender.results import read_results, map_nodes, sample_frames
from sim2blender.blender.build import Enclosure

scene = bpy.context.scene
model = read_model(scene['amodel_path'])
results = read_results(scene['results_path'])
mapping = map_nodes(model, results)
objects = [o for o in scene.objects if 'model_node_ids' in o]
assert objects
assert list(scene['source_times']) == results.times
source_frames = list(scene['source_frames'])
assert scene.render.fps_base == 1
assert source_frames == sample_frames(len(results.times), scene['structural_step_seconds'], scene.render.fps)
assert (scene.frame_start, scene.frame_end) == (1, math.ceil(source_frames[-1]))
expected = defaultdict(list)
for cell in model.cells:
    expected[(cell['component_tag'], cell['component_id'])].append(cell)
assert len(objects) == len(expected)
seen = set()
modifiers = []
for obj in objects:
    tag, cid, _ = obj.name.split('_', 2)
    cells = expected[(tag, int(cid))]
    ids = list(obj['model_node_ids'])
    assert ids == sorted({n for c in cells for n in c['nodes']})
    assert list(obj['result_vids']) == [mapping[n] for n in ids]
    actual = [tuple(ids[i] for i in p.vertices) for p in obj.data.polygons] if tag == 'membrane' else [tuple(ids[i] for i in e.vertices) for e in obj.data.edges]
    assert sorted(tuple(sorted(c)) for c in actual) == sorted(tuple(sorted(c['nodes'])) for c in cells)
    seen.update(ids)
    assert not obj.data.shape_keys.use_relative
    assert len(obj.data.shape_keys.key_blocks) == len(results.times)
    for modifier in obj.modifiers:
        assert modifier.type in {'WIREFRAME', 'NODES'}
        modifiers.append((modifier, modifier.show_viewport))
        modifier.show_viewport = False
assert seen == model.nodes.keys()
max_error = 0.0
comparisons = 0
fish = [o for o in scene.objects if o.name.startswith('Fish_')]
assert len(fish) == scene.get('fish_count', 0)
fish_checks = 0
if fish:
    cage = scene.objects['Membrane cage']
    assert cage.hide_render
    assert scene.render.engine == 'CYCLES'
    assert all(scene.objects.get(n) for n in ('Key softbox', 'Warm fill', 'Rim'))
    for obj in objects:
        if not obj.name.startswith('membrane_'):
            continue
        assert obj.data.uv_layers.get('Net metres')
        assert obj.modifiers['Visible net strands'].node_group.nodes.get('Net surface and strands')
        for polygon in obj.data.polygons:
            material = obj.data.materials[polygon.material_index]
            assert material.use_nodes
            assert any(n.type == 'BSDF_TRANSPARENT' for n in material.node_tree.nodes)
            textures = [n.image for n in material.node_tree.nodes if n.type == 'TEX_IMAGE']
            assert textures and all(image.packed_file for image in textures)
# Check every output video frame and every exact structural sample, including
# fractional key times. Fish are baked and checked at output video frames.
samples = sorted(set(source_frames) | set(range(1, scene.frame_end+1)))
for frame in samples:
    step = min(max(bisect_right(source_frames, frame)-1, 0), len(source_frames)-1)
    fraction = (frame-source_frames[step])/(source_frames[step+1]-source_frames[step]) if step+1 < len(source_frames) else 0
    scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            assert len(mesh.vertices) == len(obj['result_vids'])
            for vertex, vid in zip(mesh.vertices, obj['result_vids']):
                point = evaluated.matrix_world @ vertex.co
                a = results.positions[step][vid]
                b = results.positions[min(step+1, len(results.times)-1)][vid]
                error = max(abs(point[k] - ((1-fraction)*a[k]+fraction*b[k])) for k in range(3))
                assert error < 1e-4, (obj.name, step, fraction, vid, error)
                max_error = max(max_error, error)
                comparisons += 1
        finally:
            evaluated.to_mesh_clear()
    if fish and float(frame).is_integer():
        evaluated = cage.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            if scene.get('camera_tracking'):
                from bpy_extras.object_utils import world_to_camera_view
                from itertools import product
                from mathutils import Vector
                low = tuple(min(p[k] for p in points) for k in range(3))
                high = tuple(max(p[k] for p in points) for k in range(3))
                for corner in product(*zip(low, high)):
                    projected = world_to_camera_view(scene, scene.camera, Vector(corner))
                    assert 0 < projected.x < 1 and 0 < projected.y < 1 and projected.z > 0, (step, 'camera framing')
            for point, nid in zip(points, cage['containment_node_ids']):
                a = results.positions[step][mapping[nid]]
                b = results.positions[min(step+1, len(results.times)-1)][mapping[nid]]
                assert max(abs(point[k]-((1-fraction)*a[k]+fraction*b[k])) for k in range(3)) < 1e-4
            volume = Enclosure(points, [tuple(p.vertices) for p in mesh.polygons])
            for obj in fish:
                assert volume.contains(obj.location, scene.get('fish_clearance_radius', scene['fish_length']*.6)), (step, obj.name)
                fish_checks += 1
        finally:
            evaluated.to_mesh_clear()
for modifier, visible in modifiers:
    modifier.show_viewport = visible
destination = Path(bpy.data.filepath)
report = dict(structural_samples=len(results.times), video_frames=scene.frame_end, video_fps=scene.render.fps, structural_step_seconds=scene['structural_step_seconds'], duration_seconds=scene['duration_seconds'], last_sample_frame=source_frames[-1], checked_timeline_positions=len(samples), active_nodes=len(seen), objects=len(objects), node_comparisons=comparisons, max_evaluated_coordinate_error=max_error, fish_count=len(fish), fish_containment_checks=fish_checks)
destination.with_suffix('.validation.json').write_text(json.dumps(report, indent=2))
scene.frame_set(scene.frame_end)
scene.render.filepath = str(destination.with_name(destination.stem+'_last.png'))
bpy.ops.render.render(write_still=True)
print('SAVED REPLAY VERIFIED', json.dumps(report), flush=True)
