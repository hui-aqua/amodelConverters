"""GUI job validation without Qt or Blender imports."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from sim2blender.gui.model_job import ModelJob, ReplayJob, PipelineJob, ModelInfo, inspect_model, find_blender, validate_blender


class ModelJobTests(unittest.TestCase):
    def test_linux_discovery_and_execute_permission(self):
        with tempfile.TemporaryDirectory(prefix='Linux Blender ') as folder:
            exe = Path(folder) / 'blender'
            exe.touch()
            with patch('sim2blender.gui.model_job.sys.platform', 'linux'), \
                 patch.dict(os.environ, {'BLENDER_PATH': str(exe)}), \
                 patch('sim2blender.gui.model_job.os.access', return_value=True):
                self.assertEqual(find_blender(), str(exe.absolute()))
                self.assertEqual(validate_blender(exe), str(exe.absolute()))
            with patch('sim2blender.gui.model_job.sys.platform', 'linux'), \
                 patch('sim2blender.gui.model_job.os.access', return_value=False):
                with self.assertRaisesRegex(ValueError, 'not executable'):
                    validate_blender(exe)

    def test_linux_snap_launcher_is_not_dereferenced(self):
        # Snap dispatches using argv[0]; resolving this to /usr/bin/snap breaks it.
        with patch('sim2blender.gui.model_job.sys.platform', 'linux'), \
             patch.dict(os.environ, {'BLENDER_PATH': ''}), \
             patch('sim2blender.gui.model_job.shutil.which', return_value='/snap/bin/blender'), \
             patch('sim2blender.gui.model_job.is_executable', return_value=True), \
             patch.object(Path, 'resolve', side_effect=AssertionError('Do not dereference executable')):
            self.assertEqual(find_blender(), str(Path('/snap/bin/blender').absolute()))

    def test_extensionless_executable_and_spaces(self):
        with tempfile.TemporaryDirectory(prefix='Linux paths ') as folder:
            base = Path(folder)
            exe = base / 'blender'
            exe.touch()
            exe.chmod(0o755)
            model = base / 'my cage.amodel'
            model.touch()
            for job in (ModelJob(exe, model, base/'scene.blend', [1]),
                        PipelineJob(exe, model, base/'scene.blend', [1])):
                with patch('sim2blender.gui.model_job.sys.platform', 'linux'):
                    program, args = job.command()
                self.assertEqual(program, str(exe.absolute()))
                self.assertIn('--background', args)

    def test_pipeline_job_command(self):
        with tempfile.TemporaryDirectory(prefix='Pipeline paths ') as folder:
            base = Path(folder)
            model = base / 'cage.amodel'
            model.touch()
            exe = base / 'blender.exe'
            exe.touch();exe.chmod(0o755)
            output = base / 'test_scene.blend'
            job = PipelineJob(
                blender=exe,
                model=model,
                output=output,
                membrane_ids=[1, 2],
                beam_ids=[1, 2, 3],
                truss_ids=[25, 26],
                replay={'enabled': True, 'results': str(model)},  # results must exist
                fish_schooling={'enabled': True, 'fish_count': 500},
                feed_animation={'enabled': True, 'rpm': -30.0},
                cinematic_camera={'enabled': True, 'focal_length_mm': 32.0},
            )
            program, args = job.command()
            self.assertEqual(program, str(exe))
            self.assertIn('pipeline', args)
            self.assertIn('--config', args)
            config_path = Path(args[args.index('--config') + 1])
            self.assertTrue(config_path.is_file())
            import json
            data = json.loads(config_path.read_text(encoding='utf-8'))
            self.assertEqual(data['membrane_ids'], [1, 2])
            self.assertEqual(data['beam_ids'], [1, 2, 3])
            self.assertEqual(data['truss_ids'], [25, 26])
            self.assertTrue(data['replay']['enabled'])
            self.assertEqual(data['fish_schooling']['fish_count'], 500)

    def test_replay_command_options(self):
        with tempfile.TemporaryDirectory(prefix='Replay paths ') as folder:
            base=Path(folder)
            model=base/'my cage.amodel';model.touch()
            results=base/'out & motion.txt';results.touch()
            exe=base/'blender.exe';exe.touch();exe.chmod(0o755)
            job=ReplayJob(exe,model,base/'replay.blend',[3,4],results=results,fps=30,step_seconds=.2)
            _,args=job.command()
            self.assertIn(str(results),args)
            self.assertIn('--add-fish',args)
            self.assertEqual(args[args.index('--fps')+1],'30')
            self.assertEqual(args[args.index('--step-seconds')+1],'0.2')
            self.assertNotIn('--frames',args)
            self.assertNotIn('--pin-top',args)
            job.add_fish=False;job.membrane_ids=[]
            _,args=job.command()
            self.assertNotIn('--add-fish',args)
            self.assertNotIn('--membrane-ids',args)
            job.step_seconds=0
            with self.assertRaisesRegex(ValueError,'positive'):job.command()
            job.step_seconds=.125;job.results=base/'missing.txt'
            with self.assertRaisesRegex(ValueError,'results text'):job.command()

    def test_paths_are_separate_arguments(self):
        with tempfile.TemporaryDirectory(prefix='GUI paths ') as folder:
            base=Path(folder)
            model=base/'square cage & fish.amodel';model.touch()
            exe=base/'blender.exe';exe.touch();exe.chmod(0o755)
            output=base/'salmon cage.blend'
            program,args=ModelJob(exe,model,output,[3,4]).command()
            self.assertEqual(program,str(exe))
            self.assertIn(str(model),args)
            self.assertEqual(args[args.index('--membrane-ids')+1:args.index('--fish-count')],['3','4'])
            self.assertEqual(args[args.index('--fish-length')+1],'0.775')
            self.assertEqual(args[args.index('-o')+1],str(output))
            self.assertTrue(Path(args[args.index('--python')+1]).is_file())
            with self.assertRaisesRegex(ValueError,'Select at least'):
                ModelJob(exe,model,output,[]).command()

    def test_selection_counts_faces_not_unique_components(self):
        info=ModelInfo(Path('test.amodel'),0,[],{(0,1):[4,4,5],(1,2):[3,4]})
        self.assertEqual(info.junctions([3,4,5]),(1,[4,5]))
        self.assertEqual(info.junctions([3,4]),(0,[]))

    def test_real_model_inspection(self):
        info=inspect_model(Path(__file__).resolve().parents[2]/'examples/models/winch_cage.amodel')
        self.assertGreater(info.node_count,0)
        self.assertTrue(info.components)
        self.assertTrue(all(c['faces']>0 for c in info.components))
        self.assertTrue(info.beam_components)
        self.assertTrue(all(c['elements']>0 for c in info.beam_components))
        self.assertTrue(info.truss_components)
        self.assertTrue(all(c['elements']>0 for c in info.truss_components))


if __name__=='__main__':unittest.main()
