import sys
import xml.etree.ElementTree as ET
from pathlib import Path


CELL_TYPE_MAP = {
    "beam": 1,
    "truss": 2,
    "membrane": 3,
}

# Keep the input file hardcoded to match the simple workflow used in the other scripts.
file_path = Path(__file__).resolve().parent / "amodelExamples" / "testFile1.amodel"


def parse_amodel(file_path: Path):
    # Parse the AModel file into point coordinates plus element connectivity.
    tree = ET.parse(file_path)
    root = tree.getroot()

    nodes_section = root.find("Nodes")
    components_section = root.find("Components")

    if nodes_section is None:
        raise ValueError("Missing <Nodes> section in amodel file.")
    if components_section is None:
        raise ValueError("Missing <Components> section in amodel file.")

    node_ids = []
    node_points = []
    node_index_by_id = {}

    for node in nodes_section:
        node_id = int(node.get("id"))
        x = float(node.get("x"))
        y = float(node.get("y"))
        z = float(node.get("z"))

        node_index_by_id[node_id] = len(node_ids)
        node_ids.append(node_id)
        node_points.append((x, y, z))

    line_cells = []
    poly_cells = []

    for component in components_section:
        component_tag = component.tag
        if component_tag not in {"beam", "truss", "membrane"}:
            continue

        component_id = int(component.get("id", "0"))
        component_name = component.get("name", f"{component_tag}_{component_id}")
        elements_section = component.find("elements")
        if elements_section is None:
            continue

        for element in elements_section:
            element_id = int(element.get("id", "0"))

            if component_tag in {"beam", "truss"}:
                # ParaView stores beam and truss members as PolyData line cells.
                start_node_id = element.get("StartNode_ID")
                end_node_id = element.get("EndNode_ID")
                if not start_node_id or not end_node_id:
                    continue

                start_node_id = int(start_node_id)
                end_node_id = int(end_node_id)
                if start_node_id not in node_index_by_id or end_node_id not in node_index_by_id:
                    continue

                line_cells.append(
                    {
                        "points": [
                            node_index_by_id[start_node_id],
                            node_index_by_id[end_node_id],
                        ],
                        "component_tag": component_tag,
                        "component_id": component_id,
                        "component_name": component_name,
                        "element_id": element_id,
                    }
                )

            elif component_tag == "membrane":
                # Membranes are exported as polygon cells using their corner nodes.
                membrane_node_ids = []
                for attr in ("nodeA", "nodeB", "nodeC", "nodeD"):
                    node_id = element.get(attr)
                    if not node_id:
                        continue
                    membrane_node_ids.append(int(node_id))

                if len(membrane_node_ids) < 3:
                    continue
                if any(node_id not in node_index_by_id for node_id in membrane_node_ids):
                    continue

                poly_cells.append(
                    {
                        "points": [node_index_by_id[node_id] for node_id in membrane_node_ids],
                        "component_tag": component_tag,
                        "component_id": component_id,
                        "component_name": component_name,
                        "element_id": element_id,
                    }
                )

    return node_ids, node_points, line_cells, poly_cells


def format_points(points):
    values = []
    for x, y, z in points:
        values.append(f"{x:.12g} {y:.12g} {z:.12g}")
    return " ".join(values)


def format_connectivity(cells):
    return " ".join(" ".join(str(index) for index in cell["points"]) for cell in cells)


def format_offsets(cells):
    offsets = []
    running = 0
    for cell in cells:
        running += len(cell["points"])
        offsets.append(str(running))
    return " ".join(offsets)


def format_int_cell_data(cells, key):
    return " ".join(str(cell[key]) for cell in cells)


def build_piece_xml(node_ids, node_points, line_cells, poly_cells):
    # Build one VTK PolyData piece containing nodes, line elements, and membranes.
    polydata = ET.Element("VTKFile", type="PolyData", version="1.0", byte_order="LittleEndian")
    poly_data = ET.SubElement(polydata, "PolyData")
    piece = ET.SubElement(
        poly_data,
        "Piece",
        NumberOfPoints=str(len(node_points)),
        NumberOfVerts=str(len(node_points)),
        NumberOfLines=str(len(line_cells)),
        NumberOfStrips="0",
        NumberOfPolys=str(len(poly_cells)),
    )

    points = ET.SubElement(piece, "Points")
    points_array = ET.SubElement(
        points,
        "DataArray",
        type="Float64",
        NumberOfComponents="3",
        format="ascii",
    )
    points_array.text = "\n" + format_points(node_points) + "\n"

    point_data = ET.SubElement(piece, "PointData")
    node_id_array = ET.SubElement(point_data, "DataArray", type="Int64", Name="node_id", format="ascii")
    node_id_array.text = "\n" + " ".join(str(node_id) for node_id in node_ids) + "\n"

    # Add vertex cells so ParaView can display standalone nodes as points.
    verts = ET.SubElement(piece, "Verts")
    vert_connectivity = ET.SubElement(verts, "DataArray", type="Int64", Name="connectivity", format="ascii")
    vert_connectivity.text = "\n" + " ".join(str(index) for index in range(len(node_points))) + "\n"
    vert_offsets = ET.SubElement(verts, "DataArray", type="Int64", Name="offsets", format="ascii")
    vert_offsets.text = "\n" + " ".join(str(index + 1) for index in range(len(node_points))) + "\n"

    cell_data = ET.SubElement(piece, "CellData")
    vert_cells = [
        {
            "component_tag": "vertex",
            "component_id": 0,
            "element_id": node_id,
            "component_type": 0,
        }
        for node_id in node_ids
    ]
    all_cells = vert_cells + line_cells + poly_cells

    # Store compact numeric metadata that can be used for coloring and filtering in ParaView.
    component_type_array = ET.SubElement(
        cell_data, "DataArray", type="Int32", Name="component_type", format="ascii"
    )
    component_type_cells = []
    for cell in all_cells:
        component_type_cells.append(
            {
                **cell,
                "component_type": cell["component_type"]
                if "component_type" in cell
                else CELL_TYPE_MAP[cell["component_tag"]],
            }
        )
    component_type_array.text = (
        "\n" + format_int_cell_data(component_type_cells, "component_type")
        + "\n"
    )

    component_id_array = ET.SubElement(cell_data, "DataArray", type="Int32", Name="component_id", format="ascii")
    component_id_array.text = "\n" + format_int_cell_data(all_cells, "component_id") + "\n"

    element_id_array = ET.SubElement(cell_data, "DataArray", type="Int32", Name="element_id", format="ascii")
    element_id_array.text = "\n" + format_int_cell_data(all_cells, "element_id") + "\n"

    lines = ET.SubElement(piece, "Lines")
    line_connectivity = ET.SubElement(lines, "DataArray", type="Int64", Name="connectivity", format="ascii")
    line_connectivity.text = "\n" + format_connectivity(line_cells) + "\n"
    line_offsets = ET.SubElement(lines, "DataArray", type="Int64", Name="offsets", format="ascii")
    line_offsets.text = "\n" + format_offsets(line_cells) + "\n"

    polys = ET.SubElement(piece, "Polys")
    poly_connectivity = ET.SubElement(polys, "DataArray", type="Int64", Name="connectivity", format="ascii")
    poly_connectivity.text = "\n" + format_connectivity(poly_cells) + "\n"
    poly_offsets = ET.SubElement(polys, "DataArray", type="Int64", Name="offsets", format="ascii")
    poly_offsets.text = "\n" + format_offsets(poly_cells) + "\n"

    return polydata


def write_vtp(output_path: Path, node_ids, node_points, line_cells, poly_cells):
    # Write the XML-based VTK PolyData file in ASCII form for easy inspection.
    vtk_tree = ET.ElementTree(build_piece_xml(node_ids, node_points, line_cells, poly_cells))
    ET.indent(vtk_tree, space="  ")
    vtk_tree.write(output_path, encoding="utf-8", xml_declaration=True)


def default_output_path(input_path: Path):
    return input_path.with_suffix(".vtp")


def main():
    input_path = Path(file_path)
    output_path = default_output_path(input_path)

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    node_ids, node_points, line_cells, poly_cells = parse_amodel(input_path)
    write_vtp(output_path, node_ids, node_points, line_cells, poly_cells)

    print(f"Saved: {output_path}")
    print(f"Nodes: {len(node_points)}")
    print(f"Line cells (beam + truss): {len(line_cells)}")
    print(f"Polygon cells (membrane): {len(poly_cells)}")


if __name__ == "__main__":
    main()
