"""GUI job validation without Qt or Blender imports."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sim2blender.gui.model_job import ModelJob, ReplayJob, ModelInfo, inspect_model


class ModelJobTests(unittest.TestCase):
    def test_replay_command_options(self):
        with tempfile.TemporaryDirectory(prefix='Replay paths ') as folder:
            base=Path(folder)
            model=base/'my cage.amodel';model.touch()
            results=base/'out & motion.txt';results.touch()
            exe=base/'blender.exe';exe.touch()
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
            exe=base/'blender.exe';exe.touch()
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
        info=inspect_model(Path(__file__).resolve().parents[1]/'examples/models/winch_cage.amodel')
        self.assertGreater(info.node_count,0)
        self.assertTrue(info.components)
        self.assertTrue(all(c['faces']>0 for c in info.components))


if __name__=='__main__':unittest.main()
