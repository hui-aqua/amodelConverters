"""Source cross-section interpretation, independent of Blender.

AModel profile coordinates and load-model widths are in metres. Beam wizard
sizes are in millimetres in the supplied AquaEdit files. Retain provenance.
"""
import math


def number(attrs, key, default=0):
    value = float(attrs.get(key, default))
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'Invalid geometry {key}={value}')
    return value


def component_geometry(comp):
    def attrs(tag):
        item = comp.find(tag)
        return dict(item.attrib) if item is not None else {}
    result = dict(source_attributes=dict(comp.attrib), cross_section=attrs('crossection'), wizard=attrs('wizard'), materials=attrs('materials'), mooring=attrs('mooring'), loadmodel=attrs('loadmodel'), warnings=[])
    if comp.tag == 'membrane':
        result.update(kind='net', diameter=number(comp.attrib,'diameter'), mesh_width_y=number(comp.attrib,'maskwidthy'), mesh_width_z=number(comp.attrib,'maskwidthz'), mask_type=comp.get('maskType',''), source='membrane diameter and maskwidth attributes')
        return result
    if comp.tag == 'truss':
        area = number(result['mooring'], 'areal')
        equivalent = math.sqrt(4*area/math.pi)
        wy = number(result['loadmodel'], 'dragArealy')
        wz = number(result['loadmodel'], 'dragArealyz')
        # Hydrodynamic width can be an effective area. Use it as nominal diameter
        # only when both axes and the section area independently agree.
        if wy and abs(wy-wz) < wy*.001 and equivalent and abs(wy-equivalent) < equivalent*.02:
            diameter, source = wy, 'loadmodel widths, corroborated by mooring area'
        else:
            diameter, source = equivalent, 'equivalent circular diameter from mooring areal'
            if diameter:
                result['warnings'].append('Rope nominal diameter inferred from area; construction/lay is illustrative.')
        result.update(kind='rope', diameter=diameter, area=area, source=source)
        if not diameter:
            result['warnings'].append('No positive rope cross-section size: centerline only.')
        return result
    section = result['cross_section']
    points = [(float(p.get('x')),float(p.get('y'))) for p in comp.findall('crossection/points/point')]
    if any(not math.isfinite(v) for p in points for v in p):
        raise ValueError('Nonfinite cross-section profile')
    if section.get('symmetry','false').lower() == 'true':
        # Source stores the right half of a section, reflected about local z.
        points += [(-x,y) for x,y in reversed(points) if abs(x)>1e-12]
    clean = []
    for p in points:
        if not clean or p != clean[-1]: clean.append(p)
    if len(clean)>1 and clean[0]==clean[-1]: clean.pop()
    points=clean
    wizard = result['wizard']
    radius = max((math.hypot(*p) for p in points), default=0)
    angles=sorted(math.atan2(y,x) % math.tau for x,y in points)
    gaps=[(angles[(i+1)%len(angles)]-a) % math.tau for i,a in enumerate(angles)]
    circular = len(set(points))>=8 and radius>0 and max(gaps)<math.pi/3 and all(abs(math.hypot(*p)-radius) < radius*.003 for p in points)
    if circular:
        # Axis-aligned samples provide exact nominal radius despite rounded
        # intermediate profile coordinates.
        radius = max(max(abs(x),abs(y)) for x,y in points)
        diameter = 2*radius
        wall = 0
        source='crossection points (symmetric half-profile expanded)'
        if wizard.get('type')=='circular':
            wd = number(wizard,'outerDiameter')*.001
            if abs(wd-diameter) <= diameter*.005:
                diameter=wd
                radius=wd/2
                wall=number(wizard,'thickness')*.001
                source='crossection profile + circular wizard (mm converted to m)'
            else:
                result['warnings'].append('Wizard diameter disagrees with visual profile; profile takes precedence.')
        if not wall:
            area=number(result['materials'],'crossectionareal')
            if 0<area<math.pi*radius**2:
                wall=radius-math.sqrt(radius**2-area/math.pi)
                result['warnings'].append('Tube wall inferred from section area assuming a concentric annulus.')
        if wall>radius:
            raise ValueError('Tube wall exceeds radius')
        points=[(radius*math.cos(i*math.tau/32),radius*math.sin(i*math.tau/32)) for i in range(32)]
        result.update(kind='tube',diameter=diameter,wall_thickness=wall,profile=points,source=source)
    elif len(points)>=3:
        result.update(kind='profile',profile=points,source='explicit crossection polygon, preserving offsets and symmetry')
    else:
        result.update(kind='missing',profile=[],source='no usable cross-section')
        result['warnings'].append('No beam profile: centerline only, no invented diameter.')
    if points:
        result['width']=max(p[0] for p in points)-min(p[0] for p in points)
        result['height']=max(p[1] for p in points)-min(p[1] for p in points)
    return result
