import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import sys
from pathlib import Path

# Keep the input file hardcoded to match the simple workflow used in the other scripts.
file_path = Path(__file__).resolve().parent / "amodelExamples" / "testFile1.amodel"
tree = ET.parse(file_path)
root = tree.getroot()

# Read all node coordinates so they can be plotted directly.
nodes = root.find('Nodes')

x = []
y = []
z = []
ids = []

for node in nodes:
    ids.append(node.get('id'))
    x.append(float(node.get('x')))
    y.append(float(node.get('y')))
    z.append(float(node.get('z')))

# Use one shared coordinate range so the 3D view is not visually distorted.
all_coords = x + y + z
min_val = min(all_coords)
max_val = max(all_coords)

fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.scatter(x, y, z, s=1)
ax.set_xlim(min_val, max_val)
ax.set_ylim(min_val, max_val)
ax.set_zlim(min_val, max_val)
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
# Save the static figure so the result can be reused without reopening matplotlib.
plt.savefig('nodes.png')
plt.show()
print("Plot saved as nodes.png")
