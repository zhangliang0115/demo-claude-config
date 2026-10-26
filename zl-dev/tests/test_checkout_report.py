"""Run the shared offline footer with inert DOM nodes; no Git or registry access."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

TEMPLATE = Path(__file__).resolve().parents[1] / 'assets' / 'report.html'
DOM = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){this.tag=tag;this.children=[];this._text='';}
 append(...items){this.children.push(...items);}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(x=>x.textContent).join(' ');}
 set innerHTML(value){throw Error('Markup parsing forbidden');}
}
const footer=new Element('footer'),sandbox={document:{createElement:tag=>new Element(tag)},formatTimes:x=>String(x),task:input.task,footer};
vm.createContext(sandbox);vm.runInContext(input.source+'\nrenderCheckoutLocation(footer,task)',sandbox);
const nodes=[];function walk(n){nodes.push({tag:n.tag,text:n.textContent,open:!!n.open});n.children.forEach(walk);}walk(footer);
process.stdout.write(JSON.stringify({text:footer.textContent,nodes}));
'''

@unittest.skipUnless(shutil.which('node'), 'Node needed for presentation execution')
class CheckoutReportTests(unittest.TestCase):
    def display(self, task):
        template=TEMPLATE.read_text()
        helper='function el(tag,text,cls){'+template.split('function el(tag,text,cls){',1)[1].split('function feedbackComposer(',1)[0]
        result=subprocess.run(['node','-e',DOM],input=json.dumps({'source':helper,'task':task}),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_shared_footer_is_wired_after_analysis_specific_notice(self):
        source=TEMPLATE.read_text()
        call="renderCheckoutLocation(document.querySelector('footer'),task);"
        self.assertEqual(source.count(call),1)
        self.assertGreater(source.index(call),source.index("if(isAnalysis)document.querySelector('footer').textContent="))
        # All task types use this unconditional call; no analysis or phase guard encloses it.
        self.assertIn("task.generated_at));"+call,source)
        for kind in ['feature','analysis','change','bugfix','incident','operations','refactor','performance','migration','upgrade']:
            with self.subTest(kind=kind):
                view=self.display(dict(kind=kind,project_path='/workspace/api',current_fingerprint='a'*64))
                self.assertIn('/workspace/api',view['text']);self.assertIn('a'*64,view['text'])
                self.assertFalse(next(n for n in view['nodes'] if n['tag']=='details')['open'])

    def test_unknown_values_stay_unknown_without_fabricating_git_identity(self):
        view=self.display({})
        self.assertIn('未记录，需核对实际代码位置',view['text'])
        self.assertIn('未知，不能据此认定版本一致',view['text'])
        for phrase in ['生成时的快照','不是 Git 提交 ID','不证明业务已运行','数据已隔离','不会实时监控']:
            self.assertIn(phrase,view['text'])
        self.assertFalse(any(n['tag'] in ['a','script','iframe','input','button'] for n in view['nodes']))

    def test_path_and_fingerprint_are_literal_text(self):
        path='/workspace/<img src=x onerror=alert(1)>'
        fingerprint='<script>fetch("https://example.invalid")</script>'
        view=self.display(dict(project_path=path,current_fingerprint=fingerprint))
        self.assertIn(path,view['text']);self.assertIn(fingerprint,view['text'])
        self.assertFalse(any(n['tag'] in ['img','script'] for n in view['nodes']))

if __name__=='__main__':unittest.main()
