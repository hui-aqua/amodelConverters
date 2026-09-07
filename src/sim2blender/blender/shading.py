"""Packed open-mesh materials and a studio lighting setup for the cage.

The texture is a visual lattice on the existing cloth surface, not additional
physical twines. Image filtering averages subpixel openings in distant views.
"""
from array import array
import math


def lattice_pixels(size, coverage_u, coverage_v):
    """Return linear height RGB + antialiased strand alpha for one repeat."""
    pixels=array('f')
    for y in range(size):
        v=min((y+.5)/size,1-(y+.5)/size)
        av=max(0,min(1,(coverage_v/2-v)*size+.5))
        hv=math.sqrt(max(0,1-(v/max(coverage_v/2,1e-9))**2))
        for x in range(size):
            u=min((x+.5)/size,1-(x+.5)/size)
            au=max(0,min(1,(coverage_u/2-u)*size+.5))
            hu=math.sqrt(max(0,1-(u/max(coverage_u/2,1e-9))**2))
            h=max(hu,hv)
            pixels.extend((h,h,h,max(au,av)))
    return pixels


def principled(material,color,roughness=.5,metallic=0):
    material.use_nodes=True
    nodes=material.node_tree.nodes
    shader=next((n for n in nodes if n.type=='BSDF_PRINCIPLED'),None)
    if shader is None:shader=nodes.new('ShaderNodeBsdfPrincipled')
    shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=roughness
    shader.inputs['Metallic'].default_value=metallic
    material.diffuse_color=(*color,1)
    return shader


def net_material(diameter,width_u,width_v):
    import bpy
    name=f'Net | {diameter*1000:.4g} mm twine | {width_u*1000:.4g} x {width_v*1000:.4g} mm'
    existing=bpy.data.materials.get(name)
    if existing:return existing
    mat=bpy.data.materials.new(name)
    shader=principled(mat,(.055,.29,.22),.48)
    mat.surface_render_method='DITHERED'
    mat.use_transparent_shadow=True
    n,l=mat.node_tree.nodes,mat.node_tree.links
    uv=n.new('ShaderNodeTexCoord')
    scale=n.new('ShaderNodeVectorMath');scale.operation='DIVIDE';scale.inputs[1].default_value=(width_u,width_v,1)
    texture=n.new('ShaderNodeTexImage');texture.label='Packed physical net lattice; filtered alpha at distance'
    texture.extension='REPEAT';texture.interpolation='Linear'
    key=f'Net lattice {diameter/width_u:.6f} {diameter/width_v:.6f}'
    img=bpy.data.images.get(key)
    if img is None:
        img=bpy.data.images.new(key,width=256,height=256,alpha=True)
        img.colorspace_settings.name='Non-Color'
        img.pixels.foreach_set(lattice_pixels(256,min(diameter/width_u,.95),min(diameter/width_v,.95)))
        img.pack()
    texture.image=img
    l.new(uv.outputs['UV'],scale.inputs[0]);l.new(scale.outputs['Vector'],texture.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.35;bump.inputs['Distance'].default_value=diameter*.35
    l.new(texture.outputs['Color'],bump.inputs['Height']);l.new(bump.outputs['Normal'],shader.inputs['Normal'])
    transparent=n.new('ShaderNodeBsdfTransparent')
    mix=n.new('ShaderNodeMixShader')
    l.new(texture.outputs['Alpha'],mix.inputs[0]);l.new(transparent.outputs[0],mix.inputs[1]);l.new(shader.outputs[0],mix.inputs[2])
    out=next(node for node in n if node.type=='OUTPUT_MATERIAL')
    l.new(mix.outputs[0],out.inputs['Surface'])
    mat['twine_diameter_m']=diameter;mat['mesh_spacing_u_m']=width_u;mat['mesh_spacing_v_m']=width_v
    mat['visualization']='Openings are shader transparency; source geometry and cloth cache unchanged.'
    return mat


def shade_net(cage):
    """Add a metric UV lattice alongside the physical FE edge strands."""
    from mathutils import Vector
    mesh=cage.data
    uv=mesh.uv_layers.get('Net metres') or mesh.uv_layers.new(name='Net metres')
    mesh.uv_layers.active=uv
    for face in mesh.polygons:
        points=[mesh.vertices[i].co for i in face.vertices]
        origin=points[0];u=(points[1]-origin).normalized()
        normal=Vector((0,0,0))
        for a,b in zip(points,points[1:]+points[:1]):normal+=(a-origin).cross(b-origin)
        v=normal.normalized().cross(u).normalized()
        for loop,p in zip(face.loop_indices,points):uv.data[loop].uv=((p-origin).dot(u),(p-origin).dot(v))
    def value(name,index,fallback):
        attr=mesh.attributes.get(name)
        return max(attr.data[index].value if attr else fallback,1e-6)
    for face in mesh.polygons:
        d=value('source_diameter',face.index,.002)
        u=value('source_mesh_width_y',face.index,.025)
        v=value('source_mesh_width_z',face.index,.025)
        material=net_material(d,u,v)
        slots=list(mesh.materials)
        if material not in slots:mesh.materials.append(material)
        face.material_index=list(mesh.materials).index(material)
    group=cage.modifiers['Visible net strands'].node_group
    nodes,links=group.nodes,group.links
    if not nodes.get('Net surface and strands'):
        out=next(n for n in nodes if n.type=='GROUP_OUTPUT')
        inp=next(n for n in nodes if n.type=='GROUP_INPUT')
        strand_socket=out.inputs['Geometry'].links[0].from_socket
        join=nodes.new('GeometryNodeJoinGeometry');join.name='Net surface and strands'
        links.new(strand_socket,join.inputs['Geometry'])
        links.new(inp.outputs['Geometry'],join.inputs['Geometry'])
        links.new(join.outputs['Geometry'],out.inputs['Geometry'])
    cage['net_display']='Source-sized round FE edges plus packed open-mesh lattice shading. Metric UVs deform with cloth; material transparency is visual only.'


def studio(scene):
    import bpy
    from mathutils import Vector
    scene.render.engine='CYCLES'
    scene.cycles.samples=32
    scene.cycles.use_denoising=True
    scene.cycles.transparent_max_bounces=16
    scene.render.resolution_x=1400;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=1
    if scene.world is None:scene.world=bpy.data.worlds.new('Cage studio')
    scene.world.use_nodes=True
    bg=scene.world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value=(.055,.085,.13,1);bg.inputs['Strength'].default_value=.45
    cage=scene.objects['Membrane cage']
    points=[v.co for v in cage.data.vertices]
    target=Vector(tuple((min(p[a] for p in points)+max(p[a] for p in points))/2 for a in range(3)))
    scale=max((max(p.z for p in points)-min(p.z for p in points))/50, .01)
    for name,location,power,size,color in [('Key softbox',(35,-55,35),180000,65,(.8,.91,1)),('Warm fill',(-55,-15,-20),110000,50,(1,.78,.54)),('Rim',(15,55,-5),220000,60,(.45,.78,1))]:
        obj=scene.objects.get(name)
        if obj is None:
            obj=bpy.data.objects.new(name,bpy.data.lights.new(name,'AREA'));scene.collection.objects.link(obj)
        obj.location=target+Vector(location)*scale;obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
        obj.data.energy=power*scale*scale;obj.data.shape='DISK';obj.data.size=size*scale;obj.data.color=color
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type=='VIEW_3D':
            area.spaces.active.shading.type='MATERIAL'
            area.spaces.active.shading.use_scene_lights=True
            area.spaces.active.shading.use_scene_world=True


def apply_visualization(scene,cage):
    shade_net(cage)
    for obj in scene.objects:
        if obj.type!='MESH':continue
        if obj.get('component_type')=='beam':
            for mat in obj.data.materials:
                shader=principled(mat,(.005,.005,.005),.5,0)
                shader.inputs['IOR'].default_value=1.0
                shader.inputs['Coat Weight'].default_value=0
                shader.inputs['Transmission Weight'].default_value=0
                mat['material_description']='Black HDPE; non-metallic satin plastic'
        elif obj.get('component_type')=='truss':
            for mat in obj.data.materials:principled(mat,(.33,.21,.075),.6)
        elif obj.name.startswith('Fish_'):
            for mat in obj.data.materials:principled(mat,(.16,.48,.6),.32,.3)
    if cage.data.materials:principled(cage.data.materials[0],(.04,.2,.15),.48)
    studio(scene)
