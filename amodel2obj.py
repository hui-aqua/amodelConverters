import xml.etree.ElementTree as ET
import numpy as np
import os

# Keep the input file hardcoded to match the simple workflow used in the other scripts.
amodel_path = os.path.join(os.path.dirname(__file__), "amodelExamples", "ENCC100323640.amodel")
tree = ET.parse(amodel_path)
root = tree.getroot()

# Map each AModel node id to its 3D coordinates for later edge/face export.
node_dict = {}
for node in root.findall(".//node"):
    node_id = node.get("id")
    x = float(node.get("x"))
    y = float(node.get("y"))
    z = float(node.get("z"))
    node_dict[node_id] = (x, y, z)

# Collect element connectivity grouped by OBJ primitive type.
edges = []
faces = []
# Beams and trusses are exported as OBJ line segments.
for comp in root.findall(".//Components//beam"):
    elements = comp.find("elements")
    if elements is not None:
        for ele in elements.findall("element"):
            start_id = ele.get("StartNode_ID")
            end_id = ele.get("EndNode_ID")
            if start_id and end_id:
                node_ids = [start_id, end_id]
                edges.append(tuple(node_ids))
                
for comp in root.findall(".//Components//truss"):
    elements = comp.find("elements")
    if elements is not None:
        for ele in elements.findall("element"):
            start_id = ele.get("StartNode_ID")
            end_id = ele.get("EndNode_ID")
            if start_id and end_id:
                node_ids = [start_id, end_id]
                edges.append(tuple(node_ids))
                
# Membranes are exported as OBJ polygon faces.
for comp in root.findall(".//Components//membrane"):
    elements = comp.find("elements")
    if elements is not None:
        for ele in elements.findall("element"):
            p1 = ele.get("nodeA")
            p2 = ele.get("nodeB")
            p3 = ele.get("nodeC")
            p4 = ele.get("nodeD")
            if p1 and p2 and p3 and p4:
                node_ids = [p1, p2, p3, p4]
                faces.append(tuple(node_ids))

# Convert AModel node ids to OBJ vertex indices.
vertex_list = list(node_dict.values())
id_to_index = {node_id: idx for idx, node_id in enumerate(node_dict.keys())}
edge_indices = [(id_to_index[start], id_to_index[end]) for start, end in edges if start in id_to_index and end in id_to_index]

face_indices = [
    tuple(id_to_index[nid] for nid in face if all(nid in id_to_index for nid in face))
    for face in faces
]

# Write vertices, line elements, and membrane faces to a single OBJ file.
output_dir = os.path.join(os.path.dirname(__file__), "convertOutput")
os.makedirs(output_dir, exist_ok=True)
output_filename = os.path.splitext(os.path.basename(amodel_path))[0] + ".obj"
output_path_with_edges = os.path.join(output_dir, output_filename)
with open(output_path_with_edges, "w") as f:
    # OBJ vertices are written first and referenced later by 1-based index.
    for v in vertex_list:
        f.write(f"v {v[0]} {v[1]} {v[2]}\n")
    # Export beam/truss members as OBJ lines.
    for e in edge_indices:
        f.write(f"l {e[0]+1} {e[1]+1}\n")
    # Export membranes as OBJ faces.
    for face in face_indices:
        f.write("f " + " ".join(str(idx + 1) for idx in face) + "\n")

print(f"Geometry exported to {output_path_with_edges}")
