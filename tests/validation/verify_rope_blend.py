"""Verify saved rope caches, all shared-node attachments and rigid supports."""
import sys,json,math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import bpy
from mathutils import Vector
from sim2blender.amodel import read_model
scene=bpy.context.scene;cage=scene.objects['Membrane cage']
model=read_model(cage['source_file'])
ropes=[o for o in scene.objects if o.get('component_type')=='truss']
beams=[o for o in scene.objects if o.get('component_type')=='beam']
assert len(ropes)==scene['rope_cloth_count']
for o in ropes:
 assert o.modifiers['Rope cloth'].type=='CLOTH' and o.modifiers['Rope cloth'].show_viewport
 assert o.modifiers['Rope cloth'].point_cache.is_baked
 o.modifiers['Rope surface'].show_viewport=False
for o in beams:
 assert o.rigid_body.type=='PASSIVE'
 assert not any(m.type=='CLOTH' for m in o.modifiers)
beam_nodes={nid for c in model.cells if c['component_tag']=='beam' for nid in c['nodes']}
cage.modifiers['Visible net strands'].show_viewport=False
lookups={o.name:{int(k):v for k,v in json.loads(o['source_node_lookup']).items()} for o in ropes}
maximum_displacement=0;maximum_stretch=1;maximum_attachment_error=0;checks=0
for frame in range(1,scene.frame_end+1):
 scene.frame_set(frame)
 deps=bpy.context.evaluated_depsgraph_get()
 mesh=cage.evaluated_get(deps).data
 shared={d.value:mesh.vertices[i].co.copy() for i,d in enumerate(cage.data.attributes['node_id'].data)}
 for nid in beam_nodes:
  p=Vector(model.nodes[nid].point)
  if nid in shared:assert (shared[nid]-p).length<1e-4
  shared[nid]=p
 for obj in ropes:
  mesh=obj.evaluated_get(deps).data
  for original,v in zip(obj.data.vertices,mesh.vertices):
   assert all(math.isfinite(a) for a in v.co)
   maximum_displacement=max(maximum_displacement,(original.co-v.co).length)
  for edge in obj.data.edges:
   i,j=edge.vertices
   rest=(obj.data.vertices[i].co-obj.data.vertices[j].co).length
   maximum_stretch=max(maximum_stretch,(mesh.vertices[i].co-mesh.vertices[j].co).length/rest)
  for nid,i in lookups[obj.name].items():
   p=mesh.vertices[i].co.copy();node=model.nodes[nid]
   for a,free in enumerate(node.translate):
    if not free:assert abs(p[a]-node.point[a])<1e-4,(obj.name,frame,nid)
   if nid in shared:
    error=(p-shared[nid]).length;maximum_attachment_error=max(maximum_attachment_error,error)
    assert error<1e-4,(obj.name,frame,nid,error)
    checks+=1
   else:shared[nid]=p
assert maximum_displacement>.001
assert maximum_stretch<1.5,maximum_stretch
report=dict(rope_cloth_objects=len(ropes),passive_rigid_beams=len(beams),frames=scene.frame_end,shared_node_checks=checks,maximum_attachment_error=maximum_attachment_error,maximum_rope_displacement=maximum_displacement,maximum_edge_stretch_ratio=maximum_stretch)
Path('output/rope_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
