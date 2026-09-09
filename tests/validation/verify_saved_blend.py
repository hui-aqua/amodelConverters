"""Verify a saved trial, including baked geometry, independently of generation."""
import sys
from pathlib import Path
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import bpy
from sim2blender.amodel import read_model
from sim2blender.blender.build import boundary_caps, Enclosure

scene = bpy.context.scene
destination = Path(bpy.data.filepath)
cage = scene.objects['Membrane cage']
cloth = cage.modifiers['Cage cloth']
assert cloth.point_cache.is_baked
model = read_model(cage['source_file'])
markers = [o for o in scene.objects if o.name.startswith('Constraint node ')]
assert len(markers) == sum(not all(n.translate) for n in model.nodes.values())
for obj in markers:
    node = model.nodes[obj['node_id']]
    assert tuple(obj.lock_location) == tuple(not v for v in node.translate)
    assert max(abs(a-b) for a,b in zip(obj.location,node.point)) < 1e-4
faces = [tuple(p.vertices) for p in cage.data.polygons]
faces += boundary_caps(faces, [v.co for v in cage.data.vertices], True)
wire = cage.modifiers['Visible net strands']
wire.show_viewport = False
fish = [o for o in scene.objects if o.name.startswith('Fish_')]
assert len(fish) == scene['fish_count']
first_positions = None
max_cloth_displacement = 0
for frame in range(scene.frame_start, scene.frame_end+1):
    scene.frame_set(frame)
    evaluated = cage.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        points = [v.co.copy() for v in mesh.vertices]
        volume = Enclosure(points, faces)
        assert all(volume.contains(o.location, scene.get('fish_clearance_radius', scene['fish_length']*.6)) for o in fish), frame
        max_cloth_displacement = max(max_cloth_displacement, max((p-v.co).length for p,v in zip(points,cage.data.vertices)))
        pins = cage.vertex_groups['Fixed nodes'].index
        for v, p in zip(cage.data.vertices,points):
            if any(g.group == pins and g.weight == 1 for g in v.groups):
                assert (v.co-p).length < 1e-4, (frame,v.index)
    finally:
        evaluated.to_mesh_clear()
    if frame == scene.frame_start:
        first_positions = [o.location.copy() for o in fish]
assert any((o.location-p).length > .01 for o,p in zip(fish,first_positions))
assert max_cloth_displacement > 1e-4
report = dict(fish_count=len(fish), frames=scene.frame_end, containment_checks=len(fish)*scene.frame_end, constrained_nodes=len(markers), cloth_baked=cloth.point_cache.is_baked, virtual_caps=cage['virtual_cap_count'], additional_top_supports=cage.get('additional_top_supports',0), fish_relocations=scene['fish_relocations'], max_cloth_displacement=max_cloth_displacement)
destination.with_name('validation.json' if destination.stem == 'fish_cage' else destination.stem+'_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report), flush=True)
wire.show_viewport = True
scene.frame_set(1)
scene.render.filepath = str(destination.with_name(destination.stem+'_preview.png'))
bpy.ops.render.render(write_still=True)
