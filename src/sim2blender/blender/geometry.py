"""Source-sized structural meshes and round net strands for Blender."""
import json
import math


def local_frame(start, end, point3=None):
    from mathutils import Vector
    start, end = Vector(start), Vector(end)
    delta = end-start
    if delta.length < 1e-9:
        raise ValueError('Zero-length structural member')
    x = delta.normalized()
    z = Vector(point3)-start if point3 is not None else Vector((0,0,1))
    z -= x*z.dot(x)
    fallback = z.length < 1e-8 or point3 is None
    if z.length < 1e-8:
        z = min((Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1))), key=lambda a:abs(a.dot(x)))
        z -= x*z.dot(x)
    z.normalize()
    y = z.cross(x).normalized()
    return x,y,z,fallback


def member_mesh(start, end, geometry, point3=None):
    """Sweep an exact section along the source centerline, without guessed sag."""
    from mathutils import Vector
    x,y,z,fallback = local_frame(start,end,point3)
    start,end=Vector(start),Vector(end)
    length=(end-start).length
    points,faces=[],[]
    if geometry['kind']=='rope' and geometry['diameter']>0:
        radius=geometry['diameter']/2
        # Three shallow helical lobes remain inside the nominal circular envelope.
        # Bound detail to avoid millions of invisible turns on long moorings.
        turns=min(6,max(1,length/(geometry['diameter']*6)))
        steps=max(8,math.ceil(turns*8))
        sides=16
        for k in range(steps+1):
            t=k/steps
            for j in range(sides):
                angle=j*math.tau/sides
                phase=3*(angle-math.tau*turns*t)
                r=radius*(.94+.06*math.cos(phase))
                points.append(start+x*(length*t)+y*(r*math.cos(angle))+z*(r*math.sin(angle)))
        for k in range(steps):
            for j in range(sides):
                a=k*sides+j;b=k*sides+(j+1)%sides
                faces.append((a,b,b+sides,a+sides))
        faces.extend([tuple(reversed(range(sides))),tuple(steps*sides+j for j in range(sides))])
        return points,faces,fallback
    profile=geometry.get('profile',[])
    if not profile:
        return [start,end],[],fallback
    n=len(profile)
    for origin in (start,end):
        points.extend(origin+y*u+z*v for u,v in profile)
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    wall=geometry.get('wall_thickness',0)
    radius=geometry.get('diameter',0)/2
    if 0<wall<radius:
        ratio=(radius-wall)/radius
        for origin in (start,end):
            points.extend(origin+y*(u*ratio)+z*(v*ratio) for u,v in profile)
        for i in range(n):
            j=(i+1)%n
            faces.extend([(2*n+j,2*n+i,3*n+i,3*n+j),(i,2*n+i,2*n+j,j),(n+j,3*n+j,3*n+i,n+i)])
    else:
        faces.extend([tuple(reversed(range(n))),tuple(range(n,2*n))])
    return points,faces,fallback


def build_members(model, collection, tags=('beam', 'truss'), *, replay=None):
    import bpy
    import bmesh
    from collections import defaultdict
    groups=defaultdict(list)
    for c in model.cells:
        if c['component_tag'] in tags:
            groups[(c['component_tag'],c['component_id'])].append(c)
    report=[]
    for component_number, ((tag,cid),cells) in enumerate(groups.items(), 1):
        if replay is not None:
            print(f'GUI_STAGE: Replaying {tag} component {cid} '
                  f'({component_number}/{len(groups)}, {len(cells)} elements)…', flush=True)
        geometry=cells[0]['geometry']
        vertices,faces,edges,element_ids=[],[],[],[]
        fallback_count=0
        bindings=[]
        for cell in cells:
            a,b=(model.nodes[n].point for n in cell['nodes'])
            pts,polys,fallback=member_mesh(a,b,geometry,cell['point3'])
            offset=len(vertices)
            vertices.extend(pts)
            if replay is not None:
                from mathutils import Vector
                x,y,z,_ = local_frame(a,b,cell['point3'])
                length = (Vector(b)-Vector(a)).length
                origin = Vector(a)
                local = [((p-origin).dot(x)/length,
                          (p-origin).dot(y), (p-origin).dot(z)) for p in pts]
                bindings.append((cell, local))
            faces.extend(tuple(offset+i for i in f) for f in polys)
            if not polys:edges.append((offset,offset+1))
            element_ids.extend([cell['element_id']]*len(polys))
            fallback_count+=int(fallback)
        mesh=bpy.data.meshes.new(f'{tag}_{cid} section mesh')
        mesh.from_pydata(vertices,edges,faces)
        mesh.update()
        # Source polygons may run either way; ensure consistent outward normals.
        bm=bmesh.new();bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(mesh);bm.free()
        obj=bpy.data.objects.new(f'{tag.title()} {cid}: {cells[0]["component_name"]}',mesh)
        collection.objects.link(obj)
        if replay is not None:
            _animate_member_sections(obj, model, bindings, *replay)
        obj['active']=True
        obj['component_id']=cid
        obj['component_type']=tag
        obj['geometry_source']=geometry['source']
        obj['source_geometry_json']=json.dumps(geometry)
        obj['orientation_fallback_count']=fallback_count
        for key in ('diameter','wall_thickness','width','height','area'):
            if key in geometry:obj[key+'_m' if key!='area' else 'area_m2']=geometry[key]
        attr=mesh.attributes.new('element_id','INT','FACE')
        for datum,value in zip(attr.data,element_ids):datum.value=value
        material=bpy.data.materials.new(obj.name)
        material.diffuse_color=(.37,.25,.11,1) if tag=='truss' else (.13,.17,.2,1)
        mesh.materials.append(material)
        if geometry['kind'] in ('rope','tube'):
            for p in mesh.polygons:p.use_smooth=len(p.vertices)==4
        if tag=='truss':obj['rope_appearance']='Three helical surface lobes, nominal diameter envelope; visual lay limited to six turns per element.'
        report.append(dict(component_id=cid,name=cells[0]['component_name'],type=tag,elements=len(cells),orientation_fallback_count=fallback_count,**geometry))
    return report


def _animate_member_sections(obj, model, bindings, results, mapping, frames):
    """Animate four control points per element instead of every surface vertex.

    Controls encode the two endpoints and unit section axes. A Geometry Nodes
    modifier reconstructs the detailed mesh at playback time. Linear control
    interpolation reproduces the previous surface-shape-key interpolation.
    XYZ exports have no rotational DOFs, so retain the source section reference.
    """
    import bpy
    from mathutils import Vector
    from sim2blender.blender.animation import action_fcurves
    mesh=bpy.data.meshes.new(f'{obj.name} replay controls')
    mesh.from_pydata([(0,0,0)]*(4*len(bindings)),[],[])
    control=bpy.data.objects.new(mesh.name,mesh)
    obj.users_collection[0].objects.link(control)
    control['replay_control']=True
    control.hide_render=True
    control.hide_set(True)
    control.hide_select=True
    for step, positions in enumerate(results.positions):
        coords=[]
        for cell, _ in bindings:
            na,nb=cell['nodes']
            a,b=(Vector(positions[mapping[n]]) for n in (na,nb))
            point3=cell['point3']
            if point3 is not None:
                point3=Vector(point3)+a-Vector(model.nodes[na].point)
            _,y,z,_=local_frame(a,b,point3)
            for point in (a,b,a+y,a+z):
                coords.extend(point)
        key=control.shape_key_add(name=f'Time_{results.times[step]:.4f}')
        key.interpolation='KEY_LINEAR'
        key.data.foreach_set('co',coords)
    keys=control.data.shape_keys
    keys.use_relative=False
    for frame,key in zip(frames,keys.key_blocks):
        keys.eval_time=key.frame
        keys.keyframe_insert('eval_time',frame=frame)
    for curve in action_fcurves(keys.animation_data.action):
        for point in curve.keyframe_points:
            point.interpolation='LINEAR'
    obj['motion_source']='AquaSim results'
    obj['replay_control_object']=control.name

    # Per-vertex bindings are static and stored only once.
    attr=obj.data.attributes.new('replay_control_index','INT','POINT')
    attr.data.foreach_set('value', [4*i for i, (_,local) in enumerate(bindings) for _ in local])
    attr=obj.data.attributes.new('replay_section_coords','FLOAT_VECTOR','POINT')
    attr.data.foreach_set('vector', [v for _,local in bindings for point in local for v in point])

    group=bpy.data.node_groups.new(f'{obj.name} replay deformation','GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    n,l=group.nodes,group.links
    inp=n.new('NodeGroupInput'); out=n.new('NodeGroupOutput')
    info=n.new('GeometryNodeObjectInfo'); info.inputs['Object'].default_value=control
    position=n.new('GeometryNodeInputPosition')
    index=n.new('GeometryNodeInputNamedAttribute'); index.data_type='INT'
    index.inputs['Name'].default_value='replay_control_index'
    local=n.new('GeometryNodeInputNamedAttribute'); local.data_type='FLOAT_VECTOR'
    local.inputs['Name'].default_value='replay_section_coords'
    xyz=n.new('ShaderNodeSeparateXYZ'); l.new(local.outputs['Attribute'],xyz.inputs[0])
    samples=[]
    for offset in range(4):
        add=n.new('ShaderNodeMath'); add.operation='ADD'; add.inputs[1].default_value=offset
        l.new(index.outputs['Attribute'],add.inputs[0])
        sample=n.new('GeometryNodeSampleIndex'); sample.data_type='FLOAT_VECTOR'; sample.domain='POINT'
        l.new(info.outputs['Geometry'],sample.inputs['Geometry'])
        l.new(position.outputs['Position'],sample.inputs['Value'])
        l.new(add.outputs[0],sample.inputs['Index'])
        samples.append(sample.outputs['Value'])
    result=samples[0]
    for end,weight in zip(samples[1:],xyz.outputs):
        delta=n.new('ShaderNodeVectorMath'); delta.operation='SUBTRACT'
        l.new(end,delta.inputs[0]); l.new(samples[0],delta.inputs[1])
        scale=n.new('ShaderNodeVectorMath'); scale.operation='SCALE'
        l.new(delta.outputs['Vector'],scale.inputs[0]); l.new(weight,scale.inputs['Scale'])
        add=n.new('ShaderNodeVectorMath'); add.operation='ADD'
        l.new(result,add.inputs[0]); l.new(scale.outputs['Vector'],add.inputs[1])
        result=add.outputs['Vector']
    deform=n.new('GeometryNodeSetPosition')
    l.new(inp.outputs['Geometry'],deform.inputs['Geometry'])
    l.new(result,deform.inputs['Position'])
    l.new(deform.outputs['Geometry'],out.inputs['Geometry'])
    obj.modifiers.new('AquaSim replay deformation','NODES').node_group=group


def round_net(cage, membrane, node_ids):
    """Round FE edge strands with source twine sizes, following evaluated cloth.

    This is a coarse FE-edge display, not a reconstruction of each physical mesh.
    Preserve physical mesh widths explicitly for future detailed net generation.
    """
    import bpy
    diameters={n:0 for n in node_ids}
    for c in membrane:
        for n in c['nodes']:diameters[n]=max(diameters[n],c['geometry']['diameter'])
    attr=cage.data.attributes.new('twine_diameter','FLOAT','POINT')
    for d,n in zip(attr.data,node_ids):d.value=diameters[n]
    for key in ('diameter','mesh_width_y','mesh_width_z'):
        a=cage.data.attributes.new('source_'+key,'FLOAT','FACE')
        for d,c in zip(a.data,membrane):d.value=c['geometry'][key]
    cage['net_display']='Round finite-element edges at source twine diameter; physical mask widths stored on faces. Shared nodes use larger adjacent twine.'
    group=bpy.data.node_groups.new('Round source-sized net strands','GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    n,l=group.nodes,group.links
    inp,out=n.new('NodeGroupInput'),n.new('NodeGroupOutput')
    curves=n.new('GeometryNodeMeshToCurve')
    radius=n.new('GeometryNodeSetCurveRadius')
    size=n.new('GeometryNodeInputNamedAttribute');size.data_type='FLOAT';size.inputs['Name'].default_value='twine_diameter'
    circle=n.new('GeometryNodeCurvePrimitiveCircle');circle.inputs['Resolution'].default_value=8;circle.inputs['Radius'].default_value=.5
    mesh=n.new('GeometryNodeCurveToMesh')
    material=n.new('GeometryNodeSetMaterial');material.inputs['Material'].default_value=cage.data.materials[0]
    l.new(inp.outputs['Geometry'],curves.inputs['Mesh'])
    l.new(curves.outputs['Curve'],radius.inputs['Curve'])
    l.new(size.outputs['Attribute'],radius.inputs['Radius'])
    l.new(radius.outputs['Curve'],mesh.inputs['Curve'])
    if 'Scale' in mesh.inputs:
        # Blender 5.2 exposes profile scale explicitly instead of implicitly
        # multiplying the stored curve radius.
        l.new(size.outputs['Attribute'],mesh.inputs['Scale'])
    l.new(circle.outputs['Curve'],mesh.inputs['Profile Curve'])
    l.new(mesh.outputs['Mesh'],material.inputs['Geometry'])
    l.new(material.outputs['Geometry'],out.inputs['Geometry'])
    cage.modifiers.new('Visible net strands','NODES').node_group=group
