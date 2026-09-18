"""Shading-only corrections for AquaSim's independently swept rope segments."""
import json
from collections import defaultdict


def smooth_generated_rope(group):
    """Insert one shading node chain into this project's Rope surface group."""
    if group.nodes.get('AquaSim rope smooth walls'):
        return
    mesh=next((n for n in group.nodes if n.bl_idname=='GeometryNodeCurveToMesh'),None)
    if mesh is None:
        return
    n,l=group.nodes,group.links
    destinations=[link.to_socket for link in mesh.outputs['Mesh'].links]
    smooth=n.new('GeometryNodeSetShadeSmooth');smooth.domain='FACE'
    smooth.name='AquaSim rope smooth walls'
    corners=n.new('GeometryNodeInputMeshFaceNeighbors')
    sides=n.new('FunctionNodeCompare');sides.data_type='INT';sides.operation='EQUAL'
    integer_inputs=[socket for socket in sides.inputs if socket.type=='INT']
    integer_inputs[1].default_value=4
    l.new(corners.outputs['Vertex Count'],integer_inputs[0])
    l.new(sides.outputs['Result'],smooth.inputs['Shade Smooth'])
    l.new(mesh.outputs['Mesh'],smooth.inputs['Geometry'])
    for socket in destinations:l.new(smooth.outputs['Geometry'],socket)


def preprocess_rope_segments(objects=None):
    """Use cylindrical side normals on tagged, static swept truss meshes.

    Independent helical sweeps restart at every element. Radial corner normals
    suppress those lighting restarts without changing their lobed geometry.
    End caps retain face normals. Requires the importer's two polygonal caps
    per connected segment; unsupported meshes and authored normals are skipped.
    Generated cloth surfaces are handled by rope_surface's shading nodes.
    """
    import bpy
    from mathutils import Vector
    objects=list(dict.fromkeys(bpy.context.scene.objects if objects is None else objects))
    selected=set(objects)
    def eligible(obj):
        try:
            return (obj.type=='MESH' and obj.get('component_type')=='truss'
                    and json.loads(obj.get('source_geometry_json','{}')).get('kind')=='rope')
        except (ValueError,TypeError,AttributeError):
            return False
    users=defaultdict(list)
    for obj in bpy.data.objects:
        if obj.type=='MESH':users[obj.data].append(obj)
    report=dict(processed=0,skipped=0,meshes_processed=0,modifiers_added=0)
    done=set()
    for obj in objects:
        if not eligible(obj):
            report['skipped']+=1
            continue
        mesh=obj.data
        surface=obj.modifiers.get('Rope surface')
        if (not mesh.polygons and surface and surface.type=='NODES' and surface.node_group
                and not obj.library and not mesh.library and not surface.node_group.library):
            smooth_generated_rope(surface.node_group)
            report['processed']+=1
            continue
        if (obj.library or mesh.library or mesh.is_editmode or not mesh.polygons or mesh.shape_keys
                or any(u not in selected or not eligible(u) or u.library for u in users[mesh])
                or (mesh.has_custom_normals and not mesh.get('aquasim_radial_rope_normals'))):
            report['skipped']+=1
            continue
        if mesh in done:
            report['processed']+=1
            continue
        parent=list(range(len(mesh.vertices)))
        def root(i):
            while parent[i]!=i:
                parent[i]=parent[parent[i]]
                i=parent[i]
            return i
        for edge in mesh.edges:
            a,b=edge.vertices
            parent[root(b)]=root(a)
        groups=defaultdict(list)
        for face in mesh.polygons:groups[root(face.vertices[0])].append(face)
        normals=[None]*len(mesh.loops)
        smooth=[False]*len(mesh.polygons)
        valid=True
        for faces in groups.values():
            caps=[f for f in faces if len(f.vertices)>4]
            if len(caps)!=2:
                valid=False
                break
            centers=[sum((mesh.vertices[i].co for i in f.vertices),Vector())/len(f.vertices) for f in caps]
            origin=centers[0];axis=centers[1]-origin
            if axis.length<1e-8:
                valid=False
                break
            axis.normalize()
            for face in faces:
                cap=face.index in (caps[0].index,caps[1].index)
                smooth[face.index]=not cap
                for loop in face.loop_indices:
                    offset=mesh.vertices[mesh.loops[loop].vertex_index].co-origin
                    normal=face.normal.copy() if cap else (offset-axis*offset.dot(axis)).normalized()
                    normals[loop]=tuple(normal)
        if not valid:
            report['skipped']+=1
            continue
        mesh.polygons.foreach_set('use_smooth',smooth)
        if hasattr(mesh,'use_auto_smooth'):mesh.use_auto_smooth=True
        mesh.normals_split_custom_set(normals)
        mesh['aquasim_radial_rope_normals']=True
        mesh.update()
        done.add(mesh)
        report['processed']+=1
        report['meshes_processed']+=1
    print(f"Rope shading: {report['processed']} processed, {report['skipped']} skipped, "
          f"{report['meshes_processed']} meshes, 0 modifiers added",flush=True)
    return report
