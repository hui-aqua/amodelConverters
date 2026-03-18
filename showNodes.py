import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import sys

file_path = "testFile1.amodel"   
tree = ET.parse(file_path)
root = tree.getroot()

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

# Set same aspect ratio for x, y, z axes
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
plt.savefig('nodes.png')
plt.show()
print("Plot saved as nodes.png")