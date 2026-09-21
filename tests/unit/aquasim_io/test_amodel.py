import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sim2blender.amodel import read_model
from sim2blender.obj import write_obj
from sim2blender.vtp import build_piece_xml


class ReaderTests(unittest.TestCase):
    def read(self, body):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sample.amodel'
            path.write_text(body)
            return read_model(path)

    def fixture(self, elements='', component='active="true"', nodes=''):
        return f'''<model><Nodes>
        <node id="1" x="1" y="2" z="3"><dof6 TranslationX="false" TranslationY="true" TranslationZ="false"/></node>
        <node id="2" x="0" y="1" z="0" translate="false"/>
        <node id="3" x="0" y="0" z="1"/>{nodes}
        </Nodes><Components><membrane id="8"><description {component}/>
        <elements><element id="4" nodeA="1" nodeB="2" nodeC="3"/>{elements}</elements>
        </membrane></Components></model>'''

    def test_activity_dof_xyz(self):
        m = self.read(self.fixture('<element id="9" active="false" nodeA="99"/>'))
        self.assertEqual(len(m.cells), 1)
        self.assertEqual(m.nodes[1].point, (1,2,3))
        self.assertEqual(m.nodes[1].translate, (False,True,False))
        self.assertEqual(m.nodes[2].translate, (False,False,False))
        self.assertEqual(self.read(self.fixture(component='active="false"')).cells, [])
        self.assertEqual(self.read(self.fixture(component='')).cells, [])

    def test_invalid_reference_and_duplicate(self):
        with self.assertRaisesRegex(ValueError, 'missing nodes'):
            self.read(self.fixture('<element id="9" nodeA="1" nodeB="2" nodeC="99"/>'))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.read(self.fixture(nodes='<node id="1"/>'))

    def test_exports(self):
        m = self.read(self.fixture())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'out.obj'
            write_obj(path,m)
            self.assertIn('v 1.0 2.0 3.0', path.read_text())
            self.assertIn('f 1 2 3', path.read_text())
        piece = build_piece_xml(*m.legacy()).find('.//Piece')
        self.assertEqual(piece.get('NumberOfPolys'), '1')
        self.assertEqual(piece.find("Polys/DataArray[@Name='connectivity']").text.strip(), '0 1 2')


if __name__ == '__main__':
    unittest.main()
