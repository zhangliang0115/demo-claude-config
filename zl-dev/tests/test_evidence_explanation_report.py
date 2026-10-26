"""Run the evidence explanation view with literal untrusted record text."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOM = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
class Node {constructor(tag){this.tag=tag;this.children=[];this._text='';this.open=false;}
append(...xs){this.children.push(...xs);} set textContent(v){this._text=String(v);this.children=[];}
get textContent(){return this._text+this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
set innerHTML(v){throw Error('untrusted HTML');}}
const root=new Node('root'),sandbox={root,evidence:input.evidence,el:(tag,text,cls)=>{const n=new Node(tag);if(text!==undefined)n.textContent=text;n.className=cls;return n;}};
vm.createContext(sandbox);vm.runInContext(input.source+'\nrenderEvidenceFreshnessDetails(root,evidence)',sandbox);
const nodes=[];function walk(n){nodes.push({tag:n.tag,text:n.textContent,open:n.open});n.children.forEach(x=>{if(typeof x!=='string')walk(x);});}walk(root);
process.stdout.write(JSON.stringify({text:root.textContent,nodes}));
'''

@unittest.skipUnless(shutil.which('node'), 'Node required for actual view execution')
class EvidenceExplanationReportTests(unittest.TestCase):
    def display(self, details=None, **extra):
        template=(ROOT/'assets/report.html').read_text()
        source='function renderEvidenceFreshnessDetails('+template.split('function renderEvidenceFreshnessDetails(',1)[1].split('function renderRoundChanges(',1)[0]
        evidence=dict(behavior_ids=['B1'],**extra)
        if details is not None:evidence['freshness_details']=details
        out=subprocess.run(['node','-e',DOM],input=json.dumps(dict(source=source,evidence=evidence)),capture_output=True,text=True)
        self.assertEqual(out.returncode,0,out.stderr)
        return json.loads(out.stdout)

    def test_source_changes_show_reason_original_scope_and_folded_paths(self):
        view=self.display(dict(state='stale',baseline='captured',reasons=['源码集合变化。'],changed_paths=['policy.py'],changed_path_count=1,paths_truncated=False,recheck='按原 B1 范围重验。'))
        for value in ['这条记录为何不能直接作为当前依据','源码集合变化','原证据关联行为','B1','不能据此归因于其他任务','不证明业务行为变化']:
            self.assertIn(value,view['text'])
        self.assertFalse(next(n for n in view['nodes'] if n['tag']=='details')['open'])
        self.assertNotIn('input',[n['tag'] for n in view['nodes']])

    def test_legacy_and_truncated_details_cannot_assert_safe_or_complete_diff(self):
        view=self.display(dict(state='stale',baseline='legacy_missing',reasons=['无法定位原因。'],changed_paths=['sample.py'],changed_path_count=None,paths_truncated=True))
        self.assertIn('无法反推具体变更原因',view['text'])
        self.assertIn('数量未知',view['text']);self.assertIn('不能据此缩小重验范围',view['text'])

    def test_invalid_receipt_is_visible_even_if_version_detail_claims_current(self):
        view=self.display(dict(state='current',baseline='captured',reasons=[]),verification_source='invalid')
        self.assertIn('代码版本匹配也不代表结果可信',view['text'])
        self.assertEqual(self.display(dict(state='current'))['text'],'')
        self.assertEqual(self.display()['text'],'')

    def test_untrusted_reason_and_paths_stay_literal_text(self):
        value='<img src=x onerror=alert(1)>'
        view=self.display(dict(state='unknown',baseline='invalid',reasons=[value],changed_paths=[value],changed_path_count=1))
        self.assertIn(value,view['text'])
        self.assertFalse(any(n['tag'] in ['img','script','iframe'] for n in view['nodes']))
        feature=(ROOT/'assets/views/feature.js').read_text()
        self.assertIn("renderEvidenceFreshnessDetails(r,e)",feature)
        for name in ['bugfix','incident','operations','engineering']:
            self.assertIn("typeof renderEvidenceFreshnessDetails==='function'", (ROOT/('assets/views/'+name+'.js')).read_text())

if __name__=='__main__':unittest.main()
