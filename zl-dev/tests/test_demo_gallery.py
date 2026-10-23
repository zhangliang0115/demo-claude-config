import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_demo_gallery

class GalleryTests(unittest.TestCase):
    def test_gallery_links_and_escaping(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            task=root/'example';task.mkdir()
            (task/'task.json').write_text(json.dumps(dict(version=1,id='example',title='</script><img onerror=bad()>',kind='bugfix',demo=dict(category='排障',purpose='找原因',simulation=True,read_order=['现象','复现']))))
            out=build_demo_gallery.build(root).read_text()
            self.assertTrue((task/'report.html').exists())
            self.assertNotIn('</script><img',out)
            self.assertIn('example/report.html',out)
            self.assertNotIn('__DEMO_DATA__',out)
    def test_guidance_by_type_and_phase(self):
        from workflow import reading_guide
        self.assertNotEqual(reading_guide('feature','requirements'),reading_guide('feature','acceptance'))
        self.assertNotEqual(reading_guide('incident','operations'),reading_guide('bugfix','testing'))
