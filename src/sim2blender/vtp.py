"""Export active AModel geometry and metadata as VTK PolyData."""
import xml.etree.ElementTree as ET
from pathlib import Path


CELL_TYPE_MAP = {
    "beam": 1,
    "truss": 2,
    "membrane": 3,
}

def parse_amodel(file_path):
    from sim2blender.amodel import read_model
    return read_model(file_path).legacy()


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


def main():
    from sim2blender.amodel import cli, read_model
    args = cli("Export active AModel geometry and node constraints to VTP", ".vtp")
    model = read_model(args.input)
    data = build_piece_xml(*model.legacy())
    point_data = data.find(".//PointData")
    for axis, name in enumerate("xyz"):
        array = ET.SubElement(point_data, "DataArray", type="Int32", Name="translate_"+name, format="ascii")
        array.text = " ".join(str(int(n.translate[axis])) for n in model.nodes.values())
    tree = ET.ElementTree(data)
    ET.indent(tree, space="  ")
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
