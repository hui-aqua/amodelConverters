"""Rope cloth with explicit, baked attachment targets and post-simulation surfaces.

Attachments are solved in dependency order (one-way), not a coupled force solve.
The first simulated owner of a shared source node supplies all later targets.
"""
import json
import math


def rope_centerline(model, cells, max_segment=.5):
    from sim2blender.io.aquasim.model import Node
    nodes=[];edges=[];lookup={};element_ids=[]
    def source(nid):
        if nid not in lookup:
            lookup[nid]=len(nodes);nodes.append(model.nodes[nid])
        return lookup[nid]
    for cell in cells:
        a,b=cell['nodes'];ia,ib=source(a),source(b)
        pa,pb=model.nodes[a].point,model.nodes[b].point
        length=math.dist(pa,pb)
        if length<1e-9:raise ValueError(f'Zero-length rope element {cell["element_id"]}')
        count=max(2,math.ceil(length/max_segment))
        previous=ia
        for k in range(1,count+1):
            if k==count:current=ib
            else:
                current=len(nodes)
                point=tuple(pa[j]+(pb[j]-pa[j])*k/count for j in range(3))
                nodes.append(Node(-current-1,point,(True,True,True)))
            edges.append((previous,current));element_ids.append(cell['element_id']);previous=current
    return nodes,edges,lookup,element_ids


def bake_cloth(obj,cloth,frames):
    import bpy
    scene=bpy.context.scene
    scene.frame_set(1)
    cloth.point_cache.frame_start=1;cloth.point_cache.frame_end=frames
    bpy.context.view_layer.objects.active=obj
    with bpy.context.temp_override(point_cache=cloth.point_cache):
        bpy.ops.ptcache.bake(bake=True)
    if not cloth.point_cache.is_baked:raise RuntimeError(f'Cloth did not bake: {obj.name}')


def sample_node_motion(obj,lookup,frames):
    import bpy
    samples={nid:[] for nid in lookup}
    for frame in range(1,frames+1):
        bpy.context.scene.frame_set(frame)
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh()
        try:
            for nid,index in lookup.items():samples[nid].append(tuple(obj.matrix_world@mesh.vertices[index].co))
        finally:evaluated.to_mesh_clear()
    return samples


def create_rope_cloth(model,cells,collection,frames,owners):
    import bpy
    from sim2blender.blender.scene import mesh_object,constrain_axes
    nodes,edges,lookup,element_ids=rope_centerline(model,cells)
    cell=cells[0];g=cell['geometry'];cid=cell['component_id']
    obj=mesh_object(f'Truss {cid}: {cell["component_name"]}',[n.point for n in nodes],edges,[],collection)
    obj['active']=True;obj['component_id']=cid;obj['component_type']='truss'
    obj['geometry_source']=g['source'];obj['source_geometry_json']=json.dumps(g)
    obj['diameter_m']=g['diameter'];obj['area_m2']=g['area']
    obj['physics']='Cloth centerline; surface generated after simulation'
    obj['attachment_model']='One-way baked node targets: membrane, passive beams, then earlier rope owners'
    obj['source_node_lookup']=json.dumps(lookup)
    obj['attachment_node_ids']=json.dumps([nid for nid in lookup if nid in owners])
    for name,values,domain in [('node_id',[n.id for n in nodes],'POINT'),('element_id',element_ids,'EDGE')]:
        attr=obj.data.attributes.new(name,'INT',domain)
        for datum,value in zip(attr.data,values):datum.value=value
    pins=obj.vertex_groups.new(name='Fixed nodes and attachments')
    pinned=[i for i,n in enumerate(nodes) if not any(n.translate) or n.id in owners]
    if pinned:pins.add(pinned,1,'REPLACE')
    obj['source_fixed_node_count']=sum(not any(n.translate) for n in nodes)
    dynamic={nid:owners[nid] for nid in lookup if nid in owners and any(math.dist(owners[nid][0],p)>1e-7 for p in owners[nid][1:])}
    # Absolute shape keys animate only pin targets before cloth. Free vertices
    # keep the same rest shape; use_dynamic_mesh remains disabled.
    if dynamic:
        for frame in range(frames):
            key=obj.shape_key_add(name=f'Attachment targets {frame+1:04}')
            for nid,trajectory in dynamic.items():
                i=lookup[nid];node=nodes[i]
                key.data[i].co=tuple(trajectory[frame][a] if node.translate[a] else node.point[a] for a in range(3))
        keys=obj.data.shape_keys;keys.use_relative=False
        for frame,key in enumerate(keys.key_blocks,1):
            key.interpolation='KEY_LINEAR'
            keys.eval_time=key.frame
            keys.keyframe_insert('eval_time',frame=frame)
        for layer in keys.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:key.interpolation='LINEAR'
    cloth=obj.modifiers.new('Rope cloth','CLOTH')
    cloth.settings.quality=8
    cloth.settings.mass=.05
    cloth.settings.tension_stiffness=100
    cloth.settings.compression_stiffness=100
    cloth.settings.bending_stiffness=.05
    cloth.settings.tension_damping=10
    cloth.settings.compression_damping=10
    cloth.settings.air_damping=5
    cloth.settings.vertex_group_mass=pins.name
    cloth.settings.use_sewing_springs=False
    cloth.settings.use_dynamic_mesh=False
    cloth.settings.effector_weights.gravity=.03
    # Shared-node attachments provide contact here; sub-millimetre line-mesh
    # collision is intentionally not substituted for rope/beam contact mechanics.
    cloth.collision_settings.use_collision=False
    constrain_axes(obj,nodes)
    material=bpy.data.materials.new(obj.name);material.diffuse_color=(.37,.25,.11,1)
    obj.data.materials.append(material)
    print(f'Baking rope {cid}: {len(nodes)} vertices, {len(pinned)} pin targets',flush=True)
    bake_cloth(obj,cloth,frames)
    return obj,lookup


def rope_surface(obj,diameter):
    """Generate a three-lobed round profile downstream of Cloth."""
    import bpy
    g=bpy.data.node_groups.new('Rope surface after cloth','GeometryNodeTree')
    g.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    g.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    n,l=g.nodes,g.links
    inp,out=n.new('NodeGroupInput'),n.new('NodeGroupOutput')
    curves=n.new('GeometryNodeMeshToCurve')
    tilt=n.new('GeometryNodeSetCurveTilt')
    factor=n.new('GeometryNodeSplineParameter')
    turns=n.new('ShaderNodeMath');turns.operation='MULTIPLY';turns.inputs[1].default_value=6*math.tau
    l.new(inp.outputs['Geometry'],curves.inputs['Mesh'])
    l.new(curves.outputs['Curve'],tilt.inputs['Curve'])
    l.new(factor.outputs['Factor'],turns.inputs[0]);l.new(turns.outputs[0],tilt.inputs['Tilt'])
    circle=n.new('GeometryNodeCurvePrimitiveCircle');circle.inputs['Resolution'].default_value=16;circle.inputs['Radius'].default_value=diameter/2
    pos=n.new('GeometryNodeInputPosition');split=n.new('ShaderNodeSeparateXYZ')
    angle=n.new('ShaderNodeMath');angle.operation='ARCTAN2'
    three=n.new('ShaderNodeMath');three.operation='MULTIPLY';three.inputs[1].default_value=3
    cosine=n.new('ShaderNodeMath');cosine.operation='COSINE'
    lobes=n.new('ShaderNodeMath');lobes.operation='MULTIPLY_ADD';lobes.inputs[1].default_value=.06;lobes.inputs[2].default_value=.94
    scaled=n.new('ShaderNodeVectorMath');scaled.operation='SCALE'
    profile=n.new('GeometryNodeSetPosition')
    l.new(pos.outputs[0],split.inputs[0]);l.new(split.outputs['Y'],angle.inputs[0]);l.new(split.outputs['X'],angle.inputs[1])
    l.new(angle.outputs[0],three.inputs[0]);l.new(three.outputs[0],cosine.inputs[0]);l.new(cosine.outputs[0],lobes.inputs[0])
    l.new(pos.outputs[0],scaled.inputs[0]);l.new(lobes.outputs[0],scaled.inputs['Scale'])
    l.new(circle.outputs['Curve'],profile.inputs['Geometry']);l.new(scaled.outputs[0],profile.inputs['Position'])
    mesh=n.new('GeometryNodeCurveToMesh');mesh.inputs['Fill Caps'].default_value=True
    l.new(tilt.outputs['Curve'],mesh.inputs['Curve']);l.new(profile.outputs['Geometry'],mesh.inputs['Profile Curve'])
    material=n.new('GeometryNodeSetMaterial');material.inputs['Material'].default_value=obj.data.materials[0]
    l.new(mesh.outputs['Mesh'],material.inputs['Geometry']);l.new(material.outputs['Geometry'],out.inputs['Geometry'])
    obj.modifiers.new('Rope surface','NODES').node_group=g


def build_rope_dynamics(model,collection,cage,membrane_ids,frames):
    from collections import defaultdict
    beam_nodes={nid for c in model.cells if c['component_tag']=='beam' for nid in c['nodes']}
    owners=sample_node_motion(cage,{nid:i for i,nid in enumerate(membrane_ids)},frames)
    for nid in beam_nodes:owners[nid]=[model.nodes[nid].point]*frames
    groups=defaultdict(list)
    for c in model.cells:
        if c['component_tag']=='truss':groups[c['component_id']].append(c)
    objects=[];report=[]
    while groups:
        # Prefer components already attached to solved geometry/fixed supports.
        cid=max(groups,key=lambda cid:(sum(n in owners or not any(model.nodes[n].translate) for n in {i for c in groups[cid] for i in c['nodes']}),-cid))
        cells=groups.pop(cid)
        obj,lookup=create_rope_cloth(model,cells,collection,frames,owners)
        new={nid:i for nid,i in lookup.items() if nid not in owners}
        if new:owners.update(sample_node_motion(obj,new,frames))
        objects.append(obj)
        report.append(dict(component_id=cid,name=cells[0]['component_name'],type='truss',elements=len(cells),physics='CLOTH',**cells[0]['geometry']))
    # Add surfaces only after every dependent pin trajectory has been sampled.
    for obj in objects:rope_surface(obj,obj['diameter_m'])
    return objects,report


def rigid_beams(collection):
    import bpy
    for obj in collection.objects:
        if obj.get('component_type')!='beam':continue
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True);bpy.context.view_layer.objects.active=obj
        bpy.ops.rigidbody.object_add(type='PASSIVE')
        obj.rigid_body.collision_shape='MESH'
        obj.rigid_body.use_margin=True;obj.rigid_body.collision_margin=.001
        obj['physics']='Passive rigid support; source geometry fixed in world space'
        obj.select_set(False)
