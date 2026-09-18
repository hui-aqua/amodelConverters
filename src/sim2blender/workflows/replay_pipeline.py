"""Compose structural replay and optional schooling for both desktop and CLI use."""
import argparse
from pathlib import Path
import shutil
import sys
import tempfile



def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('model',type=Path)
    parser.add_argument('results',type=Path)
    parser.add_argument('-o','--output',type=Path,required=True)
    parser.add_argument('--fps',type=int,default=25)
    parser.add_argument('--step-seconds',type=float,default=.125)
    parser.add_argument('--wave-period',type=float)
    parser.add_argument('--frames-per-wave',type=int,default=40)
    parser.add_argument('--add-fish',action='store_true')
    parser.add_argument('--fish-count',type=int,default=1000)
    parser.add_argument('--fish-length',type=float,default=.775)
    parser.add_argument('--speed',type=float,default=.6)
    parser.add_argument('--seed',type=int,default=7)
    parser.add_argument('--membrane-ids',type=int,nargs='+')
    parser.add_argument('--no-cap-openings',action='store_true')
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    from sim2blender.workflows import replay_geometry,replay_fish
    if args.wave_period is not None:
        from sim2blender.core.timeline import wave_timing
        args.step_seconds=wave_timing(1,args.wave_period,args.frames_per_wave,args.fps)['step_seconds']
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sim2blender-replay-') as folder:
        raw=Path(folder)/'replay.blend' if args.add_fish else args.output
        print('GUI_STAGE: Replaying AquaSim structural motion',flush=True)
        timing_options=['--wave-period',str(args.wave_period),'--frames-per-wave',str(args.frames_per_wave)] if args.wave_period is not None else []
        replay_geometry.main([str(args.model),str(args.results),'-o',str(raw),
                              '--fps',str(args.fps),'--step-seconds',str(args.step_seconds),'--skip-render',*timing_options])
        if args.add_fish:
            print('GUI_STAGE: Adding salmon to the replay',flush=True)
            options=['-o',str(args.output),'--skip-render','--fish-count',str(args.fish_count),
                     '--fish-length',str(args.fish_length),'--speed',str(args.speed),'--seed',str(args.seed)]
            if args.membrane_ids:options+=['--membrane-ids',*[str(i) for i in args.membrane_ids]]
            if args.no_cap_openings:options.append('--no-cap-openings')
            replay_fish.main(options)
            shutil.copyfile(raw.with_suffix('.json'),args.output.with_suffix('.replay.json'))
        print('GUI_STAGE: Replay complete',flush=True)


if __name__=='__main__':main()
