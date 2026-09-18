"""Procedural salmon, nominally 5 kg at 0.775 m total nose-to-tail length.

Body volume uses an explicit 1000 kg/m3 visualization assumption; this is
not a biological weight estimate or a hydrodynamic mass model. Fins are sheets.
Explicit length overrides scale the entire fish, including nominal mass cubically.
"""
import math


def salmon_mesh(length=.775):
    import bpy
    from mathutils import Vector
    # Tail peduncle to snout; elliptical cross sections give a tapered body.
    sections = [(-.36,.014,.023),(-.28,.026,.043),(-.16,.047,.071),
                (0,.060,.090),(.17,.052,.079),(.29,.036,.060),
                (.39,.022,.039),(.47,.010,.015)]
    sides = 16
    verts = [(x, w*math.cos(j*2*math.pi/sides), h*math.sin(j*2*math.pi/sides))
             for x,w,h in sections for j in range(sides)]
    faces = [tuple(reversed(range(sides)))]
    for ring in range(len(sections)-1):
        for j in range(sides):
            a=ring*sides+j
            b=ring*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
    faces.append(tuple(range((len(sections)-1)*sides,len(sections)*sides)))
    volume = 0.
    for face in faces:
        a=Vector(verts[face[0]])
        for i in range(1,len(face)-1):
            volume += a.dot(Vector(verts[face[i]]).cross(Vector(verts[face[i+1]])))/6
    # Include the nose cone added below in the body volume calibration.
    nose_area = sides*.5*sections[-1][1]*sections[-1][2]*math.sin(2*math.pi/sides)
    girth = math.sqrt((5/1000)/ ((abs(volume)+nose_area*.03/3)*.775**3))
    verts = [(x,y*girth,z*girth) for x,y,z in verts]
    body_faces = len(faces)
    # Forked vertical tail, dorsal and adipose fins, paired pectoral/pelvic fins.
    fins = [ [(-.36,0,0),(-.5,0,.13),(-.455,0,0),(-.5,0,-.13)],
             [(-.12,0,.08),(-.05,0,.19),(.12,0,.085)],
             [(-.29,0,.04),(-.26,0,.08),(-.20,0,.06)],
             [(-.27,0,-.04),(-.24,0,-.11),(-.12,0,-.07)] ]
    for sign in (-1,1):
        fins += [[(.22,sign*.035,-.025),(.04,sign*.12,-.085),(.12,sign*.03,-.05)],
                 [(-.08,sign*.03,-.065),(-.19,sign*.075,-.12),(-.19,sign*.02,-.05)]]
    for fin in fins:
        start=len(verts)
        verts.extend(fin)
        faces.append(tuple(range(start,len(verts))))
    # Nose closes at +0.5 so total length is exactly one before scaling.
    nose=len(verts)
    verts.append((.5,0,0))
    # Replace the flat snout cap with a short nose cone.
    cap=faces[body_faces-1]
    faces[body_faces-1:body_faces] = [(a,b,nose) for a,b in zip(cap,cap[1:]+cap[:1])]
    mesh=bpy.data.meshes.new('Shared Atlantic salmon geometry')
    mesh.from_pydata([(x*length,y*length,z*length) for x,y,z in verts],[],faces)
    for name,color in [('Salmon silver',(.48,.57,.61,1)),
                       ('Salmon dark back',(.065,.12,.14,1)),
                       ('Salmon pale belly',(.75,.79,.76,1))]:
        mat=bpy.data.materials.new(name)
        mat.diffuse_color=color
        mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth=True
        z=sum(mesh.vertices[i].co.z for i in poly.vertices)/len(poly.vertices)
        poly.material_index=1 if z>length*.035 else (2 if z < -length*.035 else 0)
    mesh['nominal_weight_kg']=5*(length/.775)**3
    mesh['total_length_m']=length
    mesh['mass_note']='Nominal body volume at assumed 1000 kg/m3; fins excluded'
    mesh.update()
    return mesh
