# Sim2Blender

Utilities for reading AquaSim `.amodel` files and exporting or visualizing their geometry.

## Project Structure

```text
Sim2Blender/
├── amodelExamples/
│   ├── testFile1.amodel
│   ├── riktig_amodel_ULS.amodel
│   └── 693 ENCC 100 323640 36_SLS.amodel
├── amodel2matplot_showNodes.py
├── amodel2matplot_showNodesandtruss.py
├── amodel2obj.py
├── amodel2vtp.py
└── README.md
```

The scripts are stored in the project root. Example `.amodel` files are stored in [`amodelExamples`](e:\GitProject\Sim2Blender\amodelExamples).

## Scripts

### `amodel2matplot_showNodes.py`

Reads `amodelExamples/testFile1.amodel`, plots all nodes in 3D with matplotlib, and saves:

- `nodes.png`

### `amodel2matplot_showNodesandtruss.py`

Reads `amodelExamples/testFile1.amodel`, plots:

- nodes
- beams
- trusses
- membranes

and saves:

- `nodes_and_components.png`

### `amodel2obj.py`

Reads `amodelExamples/testFile1.amodel` and exports geometry as:

- `aquasim_geometry.obj`

This OBJ file can be opened in tools such as Blender and ParaView.

### `amodel2vtp.py`

Reads `amodelExamples/testFile1.amodel` and exports VTK PolyData as:

- `amodelExamples/testFile1.vtp`

The generated `.vtp` file can be opened directly in ParaView. It preserves:

- node positions
- beam and truss line elements
- membrane polygon elements
- metadata arrays such as `node_id`, `component_type`, `component_id`, and `element_id`

## Requirements

Install the Python packages used by the scripts:

```bash
pip install matplotlib numpy
```

Notes:

- `xml.etree.ElementTree`, `pathlib`, `os`, and `sys` are part of the Python standard library.
- ParaView is only needed for viewing `.vtp`.

## Usage

Run any script from the project root:

```bash
python amodel2matplot_showNodes.py
python amodel2matplot_showNodesandtruss.py
python amodel2obj.py
python amodel2vtp.py
```

Each script currently uses the hardcoded input model:

```python
amodelExamples/testFile1.amodel
```

If you want to process another example file, update the hardcoded path in the corresponding script.

## Output Formats

### OBJ

- General-purpose geometry exchange format
- Good for mesh and line geometry
- Common in Blender and other modeling tools

### VTP

- VTK PolyData format
- Better for ParaView and scientific visualization
- Supports geometry plus structured metadata arrays

For ParaView workflows, `amodel2vtp.py` is usually the better choice.
