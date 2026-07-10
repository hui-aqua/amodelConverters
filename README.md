# AquaSim AModel Converters

Lightweight Python utilities for reading, converting, and visualizing AquaSim `.amodel` structural files.

## Project Structure

```text
Sim2Blender/
├── amodelExamples/
│   ├── ENCC100323640.amodel
│   ├── riktig_amodel_ULS.amodel
│   └── testFile1.amodel
├── convertOutput/                      # Git-ignored output folder
│   ├── ENCC100323640.obj
│   └── ENCC100323640.vtp
├── amodel2matplot_showNodes.py
├── amodel2matplot_showNodesandtruss.py
├── amodel2obj.py
├── amodel2vtp.py
├── .gitignore
└── README.md
```

The conversion scripts are located in the project root directory. Example `.amodel` input files are stored inside [`amodelExamples`](file:///c:/Users/hcheng/GitHub/Sim2Blender/amodelExamples).

## Scripts

### 1. `amodel2matplot_showNodes.py`
Reads an `.amodel` file, plots all node coordinates in 3D using matplotlib, and saves the plot as:
- `nodes.png` (in the project root)

### 2. `amodel2matplot_showNodesandtruss.py`
High-performance 3D visualization script that plots:
- Nodes
- Beams
- Trusses
- Membranes (outlined loop edges)

**Performance Optimization:** Uses `Line3DCollection` from matplotlib to batch thousands of individual element lines into single draw calls, drastically speeding up rendering. Saves the resulting plot as:
- `nodes_and_components.png` (in the project root)

### 3. `amodel2obj.py`
Parses `.amodel` geometry and exports it as a standard Wavefront OBJ file inside the `convertOutput/` directory:
- `convertOutput/<model_name>.obj`

Beams and trusses are exported as line elements (`l`), and membranes are exported as polygon faces (`f`). This OBJ file can be imported directly into modeling tools like **Blender**.

### 4. `amodel2vtp.py`
Parses `.amodel` geometry and structural metadata, exporting a VTK PolyData file inside the `convertOutput/` directory:
- `convertOutput/<model_name>.vtp`

This file is optimized for scientific visualization in **ParaView** and preserves:
- Node coordinate positions
- Beam and truss line elements
- Membrane polygon elements
- Structured cell/point data arrays (such as `node_id`, `component_type`, `component_id`, and `element_id`)

---

## Requirements

Install the required Python packages:

```bash
pip install matplotlib numpy
```

*Note: `xml.etree.ElementTree`, `pathlib`, `os`, and `sys` are part of the Python standard library.*

---

## Usage

Each script has a hardcoded input model path at the top of the file (configured to `amodelExamples/ENCC100323640.amodel` by default). To process a different model, simply edit the `file_path` or `amodel_path` variable in the script.

Run any converter from the project root:

```bash
python amodel2matplot_showNodes.py
python amodel2matplot_showNodesandtruss.py
python amodel2obj.py
python amodel2vtp.py
```

All generated VTP and OBJ output files will automatically be placed in the `convertOutput/` directory, which is excluded from git tracking.
