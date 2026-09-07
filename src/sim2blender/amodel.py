"""Shared, validated AquaSim geometry reader. Coordinates remain in source XYZ."""
from dataclasses import dataclass
from pathlib import Path
import math
import xml.etree.ElementTree as ET

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = _SOURCE_ROOT if (_SOURCE_ROOT / 'pyproject.toml').is_file() else Path.cwd()
DEFAULT_INPUT = PROJECT_ROOT / 'examples' / 'models' / 'ENCC100323640.amodel'


def boolean(value):
    if value is None or value.strip().lower() not in {'true', 'false'}:
        raise ValueError(f'Expected true/false, got {value!r}')
    return value.strip().lower() == 'true'


def active(item, inherited=False):
    values = []
    if 'active' in item.attrib:
        values.append(boolean(item.get('active')))
    description = item.find('description')
    if description is not None and 'active' in description.attrib:
        values.append(boolean(description.get('active')))
    return all(values) if values else inherited


@dataclass
class Node:
    id: int
    point: tuple
    translate: tuple


@dataclass
class Model:
    nodes: dict
    cells: list

    def legacy(self):
        ids = list(self.nodes)
        indices = {nid: i for i, nid in enumerate(ids)}
        cells = [dict(c, points=[indices[n] for n in c['nodes']]) for c in self.cells]
        return ids, [n.point for n in self.nodes.values()], [c for c in cells if c['component_tag'] != 'membrane'], [c for c in cells if c['component_tag'] == 'membrane']


def read_model(path=DEFAULT_INPUT):
    root = ET.parse(path).getroot()
    if root.find('Nodes') is None or root.find('Components') is None:
        raise ValueError('AModel requires Nodes and Components sections')
    nodes = {}
    disabled = set()
    for item in root.find('Nodes'):
        if item.tag != 'node':
            continue
        nid = int(item.attrib['id'])
        if nid in nodes or nid in disabled:
            raise ValueError(f'Duplicate node {nid}')
        if not active(item, True):
            disabled.add(nid)
            continue
        point = tuple(float(item.attrib[a]) for a in 'xyz')
        if not all(map(math.isfinite, point)):
            raise ValueError(f'Nonfinite coordinates at node {nid}')
        dof = item.find('dof6')
        translation = tuple(boolean(dof.get('Translation' + a, 'true')) if dof is not None else True for a in 'XYZ')
        if 'translate' in item.attrib and not boolean(item.get('translate')):
            translation = (False,) * 3
        nodes[nid] = Node(nid, point, translation)
    cells = []
    for comp in root.find('Components'):
        if comp.tag not in {'beam', 'truss', 'membrane'}:
            continue
        enabled = active(comp)
        # A disabled component cannot be reactivated by one of its elements.
        if not enabled:
            continue
        from sim2blender.geometry import component_geometry
        geometry = component_geometry(comp)
        for ele in comp.findall('elements/element'):
            if not active(ele, enabled):
                continue
            attrs = ('nodeA', 'nodeB', 'nodeC', 'nodeD') if comp.tag == 'membrane' else ('StartNode_ID', 'EndNode_ID')
            ids = tuple(dict.fromkeys(int(ele.get(a)) for a in attrs if ele.get(a)))
            minimum = 3 if comp.tag == 'membrane' else 2
            if len(ids) < minimum:
                raise ValueError(f'Invalid {comp.tag} element {ele.get("id")}')
            if any(n in disabled for n in ids):
                continue
            missing = set(ids) - nodes.keys()
            if missing:
                raise ValueError(f'Element {ele.get("id")} references missing nodes {missing}')
            point3 = ele.find('point3')
            orientation = tuple(float(point3.get(a, 0)) for a in 'xyz') if point3 is not None else None
            if orientation is not None and not all(map(math.isfinite, orientation)):
                raise ValueError(f'Invalid point3 on element {ele.get("id")}')
            cells.append(dict(nodes=ids, component_tag=comp.tag, component_id=int(comp.get('id', 0)), component_name=comp.get('name', comp.tag), element_id=int(ele.get('id', 0)), geometry=geometry, point3=orientation))
    used = {n for c in cells for n in c['nodes']}
    return Model({n: v for n, v in nodes.items() if n in used}, cells)


def cli(description, suffix):
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('input', nargs='?', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    args.output = args.output or PROJECT_ROOT / 'output' / args.input.with_suffix(suffix).name
    args.output.parent.mkdir(parents=True, exist_ok=True)
    return args
