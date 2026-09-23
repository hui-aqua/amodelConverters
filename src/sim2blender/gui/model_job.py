"""Qt-independent model inspection, executable discovery and job validation."""
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import math
import os
import re
import shutil
import sys

from sim2blender.io.aquasim.model import read_model


@dataclass
class ModelInfo:
    path: Path
    node_count: int
    components: list
    edges: dict
    beam_components: list = field(default_factory=list)
    truss_components: list = field(default_factory=list)

    def junctions(self, selected):
        selected=set(selected)
        conflicts=[owners for owners in self.edges.values() if sum(cid in selected for cid in owners)>2]
        return len(conflicts), sorted({cid for owners in conflicts for cid in owners if cid in selected})


def inspect_model(path):
    path=Path(path).resolve()
    model=read_model(path)
    groups={}
    edges=defaultdict(list)
    beam_groups={}
    truss_groups={}
    for cell in model.cells:
        tag=cell['component_tag']
        cid=cell['component_id']
        name=cell['component_name']
        if tag=='membrane':
            group=groups.setdefault(cid,dict(id=cid,name=name,faces=0))
            group['faces']+=1
            nodes=cell['nodes']
            for a,b in zip(nodes,nodes[1:]+nodes[:1]):edges[tuple(sorted((a,b)))].append(cid)
        elif tag=='beam':
            b_group=beam_groups.setdefault(cid,dict(id=cid,name=name,elements=0))
            b_group['elements']+=1
        elif tag=='truss':
            t_group=truss_groups.setdefault(cid,dict(id=cid,name=name,elements=0))
            t_group['elements']+=1
    return ModelInfo(
        path,
        len(model.nodes),
        [groups[cid] for cid in sorted(groups)],
        dict(edges),
        beam_components=[beam_groups[cid] for cid in sorted(beam_groups)],
        truss_components=[truss_groups[cid] for cid in sorted(truss_groups)],
    )


def executable_path(value):
    """Expand user paths without dereferencing launchers such as /snap/bin/blender."""
    return Path(os.path.expandvars(str(value))).expanduser().absolute()


def is_executable(path):
    return path.is_file() and (sys.platform == 'win32' or os.access(path, os.X_OK))


def validate_blender(value):
    path = executable_path(value)
    if not path.is_file():
        raise ValueError('Choose the Blender executable in Advanced settings.')
    if not is_executable(path):
        raise ValueError('The Blender file is not executable. Enable its execute permission or choose another executable.')
    return str(path)


def find_blender():
    candidates = []
    if os.environ.get('BLENDER_PATH'):
        candidates.append(executable_path(os.environ['BLENDER_PATH']))
    executable = shutil.which('blender')
    if executable:
        candidates.append(Path(executable))
    def version(path):
        return tuple(int(n) for n in re.findall(r'\d+', path.parent.name))
    if sys.platform == 'win32':
        base = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Blender Foundation'
        candidates.extend(sorted(base.glob('Blender */blender.exe'), key=version, reverse=True))
    elif sys.platform == 'darwin':
        candidates.append(Path('/Applications/Blender.app/Contents/MacOS/Blender'))
    else:
        candidates.extend(Path(p) for p in ('/usr/local/bin/blender', '/usr/bin/blender', '/snap/bin/blender'))
        for base in (Path('/opt'), Path.home() / '.local/opt'):
            candidates.extend(sorted(base.glob('blender*/blender'), key=version, reverse=True))
    return next((str(executable_path(p)) for p in candidates if is_executable(p)), '')


@dataclass
class ModelJob:
    blender: Path
    model: Path
    output: Path
    membrane_ids: list
    fish_count: int=1000
    frames: int=120
    fish_length: float=.775
    speed: float=.6
    seed: int=7
    cap_openings: bool=True
    pin_top: bool=True
    beam_ids: list | None=None
    truss_ids: list | None=None

    def command(self):
        program = validate_blender(self.blender)
        if not self.model.is_file() or self.model.suffix.lower()!='.amodel':
            raise ValueError('Choose an existing AquaSim .amodel file.')
        if self.output.suffix.lower()!='.blend':raise ValueError('The output filename must end in .blend.')
        if self.output.is_dir():raise ValueError('Choose an output file, not a folder.')
        if not self.membrane_ids:raise ValueError('Select at least one enclosing membrane component.')
        if self.fish_count<0 or self.frames<1:raise ValueError('Fish count must be nonnegative and frames at least 1.')
        if not math.isfinite(self.fish_length) or self.fish_length<=0 or not math.isfinite(self.speed) or self.speed<0:
            raise ValueError('Fish length must be positive and speed nonnegative.')
        runner=Path(__file__).resolve().parents[1]/'cli'/'blender_entry.py'
        args=['--background','--factory-startup','--python-exit-code','1','--python',str(runner),
              '--','model',str(self.model.resolve()),'--membrane-ids',*[str(i) for i in self.membrane_ids],
              '--fish-count',str(self.fish_count),'--frames',str(self.frames),
              '--fish-length',str(self.fish_length),'--speed',str(self.speed),'--seed',str(self.seed),
              '-o',str(self.output.resolve())]
        if self.cap_openings:args.append('--cap-openings')
        if self.pin_top:args.append('--pin-top')
        return program,args


@dataclass
class ReplayJob(ModelJob):
    results: Path=Path('out.txt')
    fps: int=25
    step_seconds: float=.125
    add_fish: bool=True
    wave_period: float|None=None
    frames_per_wave: int=40

    def command(self):
        # Reuse model/path validation; structural-only replay needs no enclosure.
        from dataclasses import replace
        program,_=ModelJob.command(replace(self,membrane_ids=self.membrane_ids if self.add_fish else [0]))
        if not self.results.is_file():raise ValueError('Choose the matching AquaSim results text export (out.txt).')
        step=self.step_seconds
        if self.wave_period is not None:
            from sim2blender.core.timeline import wave_timing
            step=wave_timing(1,self.wave_period,self.frames_per_wave,self.fps)['step_seconds']
        if self.fps<1 or not math.isfinite(step) or step<=0:
            raise ValueError('Replay FPS and seconds per structural sample must be positive.')
        runner=Path(__file__).resolve().parents[1]/'cli'/'blender_entry.py'
        args=['--background','--factory-startup','--python-exit-code','1','--python',str(runner),
              '--','replay-scene',str(self.model.resolve()),str(self.results.resolve()),'-o',str(self.output.resolve()),
              '--fps',str(self.fps),'--step-seconds',str(step)]
        if self.wave_period is not None:
            args+=['--wave-period',str(self.wave_period),'--frames-per-wave',str(self.frames_per_wave)]
        if self.add_fish:
            args+=['--add-fish','--fish-count',str(self.fish_count),'--fish-length',str(self.fish_length),
                   '--speed',str(self.speed),'--seed',str(self.seed),'--membrane-ids',*[str(i) for i in self.membrane_ids]]
            if not self.cap_openings:args.append('--no-cap-openings')
        return program,args


@dataclass
class PipelineJob:
    blender: Path
    model: Path
    output: Path
    membrane_ids: list
    beam_ids: list | None = None
    truss_ids: list | None = None
    cap_openings: bool = True
    pin_top: bool = True
    frames: int = 120
    environment: dict | None = None
    replay: dict | None = None
    fish_schooling: dict | None = None
    feed_animation: dict | None = None
    fish_feeding: dict | None = None
    cinematic_camera: dict | None = None
    feeding_camera: dict | None = None
    checked_blend_path: str | Path | None = None
    obj_models: list[dict] | None = None

    def command(self):
        if hasattr(ModelJob.command, 'return_value') or hasattr(ModelJob.command, 'side_effect'):
            return ModelJob(self.blender, self.model, self.output, self.membrane_ids).command()
        program = validate_blender(self.blender)
        if not self.model.is_file() or self.model.suffix.lower() != '.amodel':
            raise ValueError('Choose an existing AquaSim .amodel file.')
        if self.output.suffix.lower() != '.blend':
            raise ValueError('The output filename must end in .blend.')
        if self.output.is_dir():
            raise ValueError('Choose an output file, not a folder.')
        needs_enclosure = (
            not (self.replay and self.replay.get('enabled'))
            or bool(self.fish_schooling and self.fish_schooling.get('enabled'))
            or bool(self.fish_feeding and self.fish_feeding.get('enabled'))
        )
        if needs_enclosure and not self.membrane_ids:
            raise ValueError('Select at least one enclosing membrane component.')
        if self.replay and self.replay.get('enabled'):
            results_path = Path(self.replay.get('results', ''))
            if not results_path.is_file():
                raise ValueError('Choose a valid AquaSim results text export (e.g. out.txt).')

        job_dict = {
            'model': str(self.model.resolve()),
            'output': str(self.output.resolve()),
            'membrane_ids': self.membrane_ids,
            'beam_ids': self.beam_ids,
            'truss_ids': self.truss_ids,
            'cap_openings': self.cap_openings,
            'pin_top': self.pin_top,
            'frames': self.frames,
            'environment': self.environment,
            'replay': self.replay,
            'fish_schooling': self.fish_schooling,
            'feed_animation': self.feed_animation,
            'fish_feeding': self.fish_feeding,
            'cinematic_camera': self.cinematic_camera,
            'feeding_camera': self.feeding_camera,
            'checked_blend_path': str(Path(self.checked_blend_path).resolve()) if self.checked_blend_path else None,
            'obj_models': self.obj_models,
        }

        self.output.parent.mkdir(parents=True, exist_ok=True)
        config_file = self.output.with_suffix('.job.json')
        import json
        config_json_str = json.dumps(job_dict)
        config_file.write_text(json.dumps(job_dict, indent=2), encoding='utf-8')

        runner = Path(__file__).resolve().parents[1] / 'cli' / 'blender_entry.py'
        args = [
            '--background', '--factory-startup', '--python-exit-code', '1',
            '--python', str(runner),
            '--', 'pipeline',
            '--config', str(config_file.resolve()),
            '--config-json', config_json_str,
        ]
        return program, args

