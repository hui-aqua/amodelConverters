import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import sys
from pathlib import Path

# Keep the input file hardcoded to match the simple workflow used in the other scripts.
file_path = Path(__file__).resolve().parent / "amodelExamples" / "testFile1.amodel"

tree = ET.parse(file_path)
root = tree.getroot()

# Build a node lookup table so element connectivity can be resolved quickly.
nodes = root.find('Nodes')
node_dict = {}
x = []
y = []
z = []

for node in nodes:
    nid = int(node.get('id'))
    nx = float(node.get('x'))
    ny = float(node.get('y'))
    nz = float(node.get('z'))
    node_dict[nid] = (nx, ny, nz)
    x.append(nx)
    y.append(ny)
    z.append(nz)

# Use one shared coordinate range so the 3D view is not visually distorted.
all_coords = x + y + z
min_val = min(all_coords)
max_val = max(all_coords)

fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.scatter(x, y, z, s=1, color='black', label='Nodes')

# Split components by type because each type is drawn differently.
components = root.find('Components')

beams = []
trusses = []
membranes = []

for comp in components:
    if comp.tag == 'beam':
        beams.append(comp)
    elif comp.tag == 'truss':
        trusses.append(comp)
    elif comp.tag == 'membrane':
        membranes.append(comp)

# Count elements up front so the script prints a quick model summary.
num_beams = len(beams)
num_trusses = len(trusses)
num_membranes = len(membranes)

beam_elements = 0
truss_elements = 0
membrane_elements = 0

for b in beams:
    elem_sec = b.find('elements')
    if elem_sec is not None:
        beam_elements += len(elem_sec)

for t in trusses:
    elem_sec = t.find('elements')
    if elem_sec is not None:
        truss_elements += len(elem_sec)

for m in membranes:
    elem_sec = m.find('elements')
    if elem_sec is not None:
        membrane_elements += len(elem_sec)

print(f"Number of nodes: {len(node_dict)}")
print(f"Number of beam components: {num_beams}, elements: {beam_elements}")
print(f"Number of truss components: {num_trusses}, elements: {truss_elements}")
print(f"Number of membrane components: {num_membranes}, elements: {membrane_elements}")

# Draw beam/truss members as lines and membranes as closed polygon edges.
def plot_elements(ax, elements, color, label, elem_type):
    for elem in elements:
        elem_sec = elem.find('elements')
        if elem_sec is not None:
            for el in elem_sec:
                if elem_type in ['beam', 'truss']:
                    start_id = el.get('StartNode_ID')
                    end_id = el.get('EndNode_ID')
                    if start_id and end_id:
                        start_id = int(start_id)
                        end_id = int(end_id)
                        if start_id in node_dict and end_id in node_dict:
                            sx, sy, sz = node_dict[start_id]
                            ex, ey, ez = node_dict[end_id]
                            ax.plot([sx, ex], [sy, ey], [sz, ez], color=color, linewidth=0.5)
                elif elem_type == 'membrane':
                    nodeA = el.get('nodeA')
                    nodeB = el.get('nodeB')
                    nodeC = el.get('nodeC')
                    nodeD = el.get('nodeD')
                    nodes_ids = [nodeA, nodeB, nodeC, nodeD, nodeA]  # close the loop
                    points = []
                    for nid in nodes_ids:
                        if nid and int(nid) in node_dict:
                            points.append(node_dict[int(nid)])
                        else:
                            break
                    else:
                        # Plot the membrane outline by connecting the element corner nodes.
                        xs = [p[0] for p in points]
                        ys = [p[1] for p in points]
                        zs = [p[2] for p in points]
                        ax.plot(xs, ys, zs, color=color, linewidth=0.5)

plot_elements(ax, beams, 'blue', 'Beams', 'beam')
plot_elements(ax, trusses, 'red', 'Trusses', 'truss')
plot_elements(ax, membranes, 'green', 'Membranes', 'membrane')

ax.set_xlim(min_val, max_val)
ax.set_ylim(min_val, max_val)
ax.set_zlim(min_val, max_val)
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
ax.legend()
# Save the static figure so the result can be reused without reopening matplotlib.
plt.savefig('nodes_and_components.png')
plt.show()
print("Plot saved as nodes_and_components.png")
