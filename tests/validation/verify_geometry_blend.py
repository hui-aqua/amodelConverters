"""Validate generated structural dimensions against source profiles."""
import sys,json,math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
import bpy
from mathutils import Vector
from sim2blender.amodel import read_model
from sim2blender.blender.geometry import local_frame
scene=bpy.context.scene
model=read_model(scene.objects['Membrane cage']['source_file'])
components={}
for c in model.cells:
 if c['component_tag'] in ('beam','truss'):components.setdefault((c['component_tag'],c['component_id']),c)
objects={(o.get('component_type'),o.get('component_id')):o for o in scene.objects if o.get('component_type') in ('beam','truss')}
assert set(objects)==set(components)
checks=[]
for key,cell in components.items():
 obj=objects[key];g=cell['geometry']
 assert obj['active']
 a,b=[Vector(model.nodes[n].point) for n in cell['nodes']]
 x,y,z,_=local_frame(a,b,cell['point3'])
 if key[0]=='truss':
  assert obj.modifiers['Rope cloth'].point_cache.is_baked
  assert obj.modifiers['Rope surface'].type=='NODES'
  assert abs(obj['diameter_m']-g['diameter'])<1e-9
  lookup={int(k):v for k,v in json.loads(obj['source_node_lookup']).items()}
  for nid,index in lookup.items():
   assert (obj.data.vertices[index].co-Vector(model.nodes[nid].point)).length<1e-4
  lengths={}
  for edge,datum in zip(obj.data.edges,obj.data.attributes['element_id'].data):
   va,vb=(obj.data.vertices[i].co for i in edge.vertices)
   lengths[datum.value]=lengths.get(datum.value,0)+(vb-va).length
  for source in model.cells:
   if source['component_tag']=='truss' and source['component_id']==key[1]:
    expected=math.dist(*(model.nodes[n].point for n in source['nodes']))
    assert abs(lengths[source['element_id']]-expected)<1e-4
  checks.append(dict(type='truss',component_id=key[1],kind='rope',physics='CLOTH',source_centerline_checked=True))
  continue
 assert obj.rigid_body.type=='PASSIVE'
 selected=set()
 for p,datum in zip(obj.data.polygons,obj.data.attributes['element_id'].data):
  if datum.value==cell['element_id']:selected.update(p.vertices)
 assert selected,(key,'missing faces')
 coords=[obj.data.vertices[i].co-a for i in selected]
 length=(b-a).length
 assert abs(min(p.dot(x) for p in coords))<1e-4,key
 assert abs(max(p.dot(x) for p in coords)-length)<1e-4,key
 if g['kind'] in ('tube','rope'):
  radii=[math.hypot(p.dot(y),p.dot(z)) for p in coords]
  assert abs(max(radii)-g['diameter']/2)<1e-4,(key,max(radii),g['diameter']/2)
  if g['kind']=='tube' and g['wall_thickness']:
   assert abs(min(radii)-(g['diameter']/2-g['wall_thickness']))<1e-4,key
 else:
  width=max(p.dot(y) for p in coords)-min(p.dot(y) for p in coords)
  height=max(p.dot(z) for p in coords)-min(p.dot(z) for p in coords)
  assert abs(width-g['width'])<1e-4,(key,width,g['width'])
  assert abs(height-g['height'])<1e-4,(key,height,g['height'])
 checks.append(dict(type=key[0],component_id=key[1],kind=g['kind'],checked_element=cell['element_id']))
assert scene['fish_count']==1000
assert len([o for o in scene.objects if o.name.startswith('Fish_')])==1000
print('Verified actual mesh dimensions and source length for',len(checks),'structural components; 1000 fish.',flush=True)
Path('output/geometry_validation.json').write_text(json.dumps(checks,indent=2))
