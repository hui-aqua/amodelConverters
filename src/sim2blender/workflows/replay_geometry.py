"""Run with Blender --background --python scripts/animate_results.py -- ..."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
import bpy
from sim2blender.io.aquasim.model import read_model
from sim2blender.io.aquasim.results import read_results, map_nodes
from sim2blender.core.timeline import sample_frames
from sim2blender.blender.scene import mesh_object, setup_view


def main(argv=None):
    parser = argparse.ArgumentParser(description='Replay exported AquaSim positions without physics')
    parser.add_argument('model', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('-o', '--output', type=Path, default=Path('output/aquasim_replay.blend'))
    parser.add_argument('--fps', type=int, default=25, help='Video frames per second')
    parser.add_argument('--step-seconds', type=float, default=.125, help='Seconds between structural samples')
    args = parser.parse_args(argv if argv is not None else (sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []))
    if args.fps < 1: parser.error('--fps must be positive')
    model = read_model(args.model)
    results = read_results(args.results)
    frames = sample_frames(len(results.times), args.step_seconds, args.fps)
    mapping = map_nodes(model, results)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, math.ceil(frames[-1])
    scene.render.fps = args.fps
    scene.render.fps_base = 1
    scene.unit_settings.system = 'METRIC'
    scene['source_times'] = results.times
    scene['source_frames'] = frames
    scene['structural_step_seconds'] = args.step_seconds
    scene['duration_seconds'] = (len(frames)-1)*args.step_seconds
    scene['time_units'] = 'Source labels retained; physical time = sample index * structural_step_seconds'
    scene['amodel_path'] = str(args.model.resolve())
    scene['results_path'] = str(args.results.resolve())
    groups = defaultdict(list)
    for cell in model.cells:
        groups[(cell['component_tag'], cell['component_id'])].append(cell)
    animated = []
    for (tag, cid), cells in groups.items():
        ids = sorted({n for cell in cells for n in cell['nodes']})
        indices = {nid:i for i,nid in enumerate(ids)}
        topology = [tuple(indices[n] for n in cell['nodes']) for cell in cells]
        points = [results.positions[0][mapping[n]] for n in ids]
        obj = mesh_object(f'{tag}_{cid}_{cells[0]["component_name"]}', points,
                          topology if tag != 'membrane' else [],
                          topology if tag == 'membrane' else [], scene.collection)
        obj['model_node_ids'] = ids
        obj['result_vids'] = [mapping[n] for n in ids]
        mat = bpy.data.materials.new(f'{tag}_{cid}')
        mat.diffuse_color = {'membrane':(.12,.42,.48,1), 'beam':(.9,.48,.12,1), 'truss':(.7,.75,.8,1)}[tag]
        obj.data.materials.append(mat)
        for step, positions in enumerate(results.positions):
            key = obj.shape_key_add(name=f'Time {results.times[step]:g}')
            key.interpolation = 'KEY_LINEAR'
            key.data.foreach_set('co', [v for n in ids for v in positions[mapping[n]]])
        keys = obj.data.shape_keys
        keys.use_relative = False
        # Use Blender's actual key times, including their float rounding.
        # Key every source sample at its exact fractional video-frame time.
        for step, key in enumerate(keys.key_blocks):
            keys.eval_time = key.frame
            keys.keyframe_insert('eval_time', frame=frames[step])
        for curve in keys.animation_data.action.layers[0].strips[0].channelbag(keys.animation_data.action_slot).fcurves:
            for point in curve.keyframe_points: point.interpolation = 'LINEAR'
        if tag == 'membrane':
            wire = obj.modifiers.new('Finite element net strands', 'WIREFRAME')
            wire.thickness = max(cells[0]['geometry'].get('diameter', .003), .003)
        else:
            group = bpy.data.node_groups.new(f'{tag}_{cid} tubes', 'GeometryNodeTree')
            group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            nodes, links = group.nodes, group.links
            inp=nodes.new('NodeGroupInput'); out=nodes.new('NodeGroupOutput')
            curve=nodes.new('GeometryNodeMeshToCurve'); circle=nodes.new('GeometryNodeCurvePrimitiveCircle')
            circle.inputs['Resolution'].default_value=8
            circle.inputs['Radius'].default_value=max(cells[0]['geometry'].get('diameter', .04)/2, .01)
            tube=nodes.new('GeometryNodeCurveToMesh')
            links.new(inp.outputs['Geometry'],curve.inputs['Mesh'])
            links.new(curve.outputs['Curve'],tube.inputs['Curve'])
            links.new(circle.outputs['Curve'],tube.inputs['Profile Curve'])
            material=nodes.new('GeometryNodeSetMaterial')
            material.inputs['Material'].default_value=mat
            links.new(tube.outputs['Mesh'],material.inputs['Geometry'])
            links.new(material.outputs['Geometry'],out.inputs['Geometry'])
            obj.modifiers.new('Structural centerline tubes','NODES').node_group=group
        animated.append(obj)
    setup_view(scene, [p for sample in (results.positions[0], results.positions[-1]) for p in sample.values()], scene.collection)
    # Verify every stored node at every step, including shape-key evaluation timing.
    max_error = 0.0
    for step, sample in enumerate(results.positions):
        frame = frames[step]
        scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
        for obj in animated:
            keys = obj.data.shape_keys
            key = keys.key_blocks[step]
            if abs(keys.eval_time-key.frame) > .001: raise AssertionError('Playback timing mismatch')
            for vertex, vid in zip(key.data, obj['result_vids']):
                max_error = max(max_error, max(abs(vertex.co[a]-sample[vid][a]) for a in range(3)))
    if max_error > .0001: raise AssertionError(f'Position error {max_error}')
    scene.frame_set(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(steps=len(results.times), video_fps=args.fps, structural_step_seconds=args.step_seconds, last_sample_frame=frames[-1], video_frame_end=scene.frame_end, duration_seconds=scene['duration_seconds'], mapped_nodes=len(mapping), extra_result_nodes=len(results.positions[0])-len(mapping), objects=len(animated), max_coordinate_error=max_error, node_mapping=mapping)
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2))
    scene.render.filepath = str(args.output.with_suffix('.png').resolve())
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    bpy.ops.render.render(write_still=True)
    print('REPLAY VERIFIED', {k:v for k,v in report.items() if k!='node_mapping'})


if __name__ == '__main__': main()
