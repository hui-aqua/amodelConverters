"""Shared Blender mesh, constraint and viewport helpers."""

def mesh_object(name, points, edges, faces, collection):
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, edges, faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def constrain_axes(obj, nodes):
    """Keep original per-axis DOFs as attributes and enforce locks after cloth."""
    import bpy
    for axis, label in enumerate('xyz'):
        attr = obj.data.attributes.new('translate_' + label, 'BOOLEAN', 'POINT')
        for datum, node in zip(attr.data, nodes):
            datum.value = node.translate[axis]
    rest = obj.data.attributes.new('rest_position', 'FLOAT_VECTOR', 'POINT')
    mask = obj.data.attributes.new('translation_mask', 'FLOAT_VECTOR', 'POINT')
    for i, node in enumerate(nodes):
        rest.data[i].vector = node.point
        mask.data[i].vector = tuple(float(v) for v in node.translate)
    if all(all(n.translate) for n in nodes):
        return
    group = bpy.data.node_groups.new('Enforce source translation locks', 'GeometryNodeTree')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    ns, links = group.nodes, group.links
    inp, out = ns.new('NodeGroupInput'), ns.new('NodeGroupOutput')
    position = ns.new('GeometryNodeInputPosition')
    restnode, masknode = ns.new('GeometryNodeInputNamedAttribute'), ns.new('GeometryNodeInputNamedAttribute')
    for node, name in ((restnode, 'rest_position'), (masknode, 'translation_mask')):
        node.data_type = 'FLOAT_VECTOR'
        node.inputs['Name'].default_value = name
    delta, allowed, result = [ns.new('ShaderNodeVectorMath') for _ in range(3)]
    delta.operation, allowed.operation, result.operation = 'SUBTRACT', 'MULTIPLY', 'ADD'
    links.new(position.outputs[0], delta.inputs[0])
    links.new(restnode.outputs['Attribute'], delta.inputs[1])
    links.new(delta.outputs[0], allowed.inputs[0])
    links.new(masknode.outputs['Attribute'], allowed.inputs[1])
    links.new(restnode.outputs['Attribute'], result.inputs[0])
    links.new(allowed.outputs[0], result.inputs[1])
    setter = ns.new('GeometryNodeSetPosition')
    links.new(inp.outputs['Geometry'], setter.inputs['Geometry'])
    links.new(result.outputs[0], setter.inputs['Position'])
    links.new(setter.outputs['Geometry'], out.inputs['Geometry'])
    obj.modifiers.new('Source axis constraints', 'NODES').node_group = group


def setup_view(scene, points, collection):
    """Provide a useful saved viewport and a camera for a quick preview."""
    import bpy
    from mathutils import Vector
    low = Vector(tuple(min(p[a] for p in points) for a in range(3)))
    high = Vector(tuple(max(p[a] for p in points) for a in range(3)))
    center = (low + high) / 2
    size = max((high - low).length, 1)
    camera = scene.objects.get('Cage overview')
    if camera is None:
        camera = bpy.data.objects.new('Cage overview', bpy.data.cameras.new('Cage overview'))
        collection.objects.link(camera)
    camera.location = center + Vector((1.2, -1.8, .7)).normalized() * size * 1.5
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = size * 1.1
    camera.data.clip_end = size * 10
    scene.camera = camera
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('Cage background')
    scene.world.color = (.025, .035, .05)
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_distance = size * 1.2
            area.spaces.active.region_3d.view_location = center
            area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
            area.spaces.active.clip_end = size * 10


