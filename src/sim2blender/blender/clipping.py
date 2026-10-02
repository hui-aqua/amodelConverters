"""World-height visibility mask for animated replay surfaces and volumes."""
import math


def apply_height_mask(scene, height=0.26):
    """Keep shading below a live scene Z threshold, without altering simulation geometry."""
    import bpy
    height = float(height)
    if not math.isfinite(height):
        raise ValueError('Replay clipping height must be finite')
    scene['replay_clip_enabled'] = True
    scene['replay_clip_z_m'] = height
    scene.id_properties_ui('replay_clip_z_m').update(
        description='World Z clipping height in metres; geometry below remains visible')
    scene.id_properties_ui('replay_clip_enabled').update(
        description='Hide surfaces and volumes above the replay clipping height')

    mask = bpy.data.node_groups.new('Replay height mask', 'ShaderNodeTree')
    mask.interface.new_socket(name='Hidden', in_out='OUTPUT', socket_type='NodeSocketFloat')
    nodes, links = mask.nodes, mask.links
    position = nodes.new('ShaderNodeNewGeometry')
    xyz = nodes.new('ShaderNodeSeparateXYZ')
    compare = nodes.new('ShaderNodeMath'); compare.operation = 'GREATER_THAN'
    enabled = nodes.new('ShaderNodeMath'); enabled.operation = 'MULTIPLY'
    output = nodes.new('NodeGroupOutput')
    links.new(position.outputs['Position'], xyz.inputs[0])
    links.new(xyz.outputs['Z'], compare.inputs[0])
    links.new(compare.outputs[0], enabled.inputs[0])
    links.new(enabled.outputs[0], output.inputs['Hidden'])
    for socket, prop in ((compare.inputs[1], 'replay_clip_z_m'),
                         (enabled.inputs[1], 'replay_clip_enabled')):
        driver = socket.driver_add('default_value').driver
        variable = driver.variables.new(); variable.name = 'setting'
        variable.targets[0].id_type = 'SCENE'
        variable.targets[0].id = scene
        variable.targets[0].data_path = f'["{prop}"]'
        driver.expression = 'setting'

    materials = set()
    visited = set()

    def collect_tree(tree):
        if tree is None or tree in visited:
            return
        visited.add(tree)
        for node in tree.nodes:
            for socket in node.inputs:
                value = getattr(socket, 'default_value', None)
                if isinstance(value, bpy.types.Material):
                    materials.add(value)
            collect_tree(getattr(node, 'node_tree', None))

    def collect_objects(objects):
        for obj in objects:
            if obj.instance_collection:
                collect_objects(obj.instance_collection.all_objects)
            if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'VOLUME'}:
                continue
            slots = getattr(obj.data, 'materials', None)
            if slots is not None:
                if not len(slots) or any(mat is None for mat in slots):
                    default = bpy.data.materials.new('Replay default material')
                    default.diffuse_color = (0.8, 0.8, 0.8, 1)
                    if not len(slots):
                        slots.append(default)
                    for index, mat in enumerate(slots):
                        if mat is None:
                            slots[index] = default
                materials.update(slot.material for slot in obj.material_slots if slot.material)
            for modifier in obj.modifiers:
                collect_tree(getattr(modifier, 'node_group', None))

    collect_objects(scene.objects)
    for material in materials:
        material.use_nodes = True
        nodes, links = material.node_tree.nodes, material.node_tree.links
        control = nodes.new('ShaderNodeGroup'); control.node_tree = mask
        control.label = 'Hide above replay Z height'
        for output in [node for node in nodes if node.type == 'OUTPUT_MATERIAL']:
            for name in ('Surface', 'Volume'):
                socket = output.inputs[name]
                if not socket.is_linked:
                    continue
                original = socket.links[0].from_socket
                mix = nodes.new('ShaderNodeMixShader')
                links.new(control.outputs['Hidden'], mix.inputs[0])
                links.new(original, mix.inputs[1])
                if name == 'Surface':
                    transparent = nodes.new('ShaderNodeBsdfTransparent')
                    links.new(transparent.outputs[0], mix.inputs[2])
                links.new(mix.outputs[0], socket)
        if hasattr(material, 'surface_render_method'):
            material.surface_render_method = 'DITHERED'
    # Solid shading ignores materials. Open the saved scene with the mask visible.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
    return len(materials)
