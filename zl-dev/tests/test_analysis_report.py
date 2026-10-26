"""Run the source-analysis view against a strict local DOM; no network or business actions."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
DOM = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
let markupExecuted=false,networkCalls=0;
class Element {
 constructor(tag){this.tag=tag;this.className='';this.children=[];this.attributes={};this.dataset={};this.classList={add:cls=>{this.addedClass=cls;}};this._text='';}
 append(...xs){this.children.push(...xs);}
 setAttribute(k,v){this.attributes[k]=v;}
 get textContent(){return this._text+this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
 set textContent(x){this._text=String(x);this.children=[];}
 set innerHTML(x){markupExecuted=true;throw new Error('Markup is forbidden');}
 scrollIntoView(){this.scrolled=true;}
}
const ui={el:(tag,value,cls)=>{const e=new Element(tag);if(value!==undefined)e.textContent=value;if(cls)e.className=cls;return e;},text:value=>value===undefined||value===null||value===''?'尚未记录':typeof value==='string'?value:JSON.stringify(value)};
const root=new Element('root'),sandbox={Map,encodeURIComponent,fetch:()=>{networkCalls++;throw new Error('Network forbidden');},XMLHttpRequest:()=>{networkCalls++;throw new Error('Network forbidden');},console};
vm.createContext(sandbox);vm.runInContext(input.source,sandbox);sandbox.root=root;sandbox.task=input.task;sandbox.ui=ui;vm.runInContext('renderAnalysisView(root,task,ui)',sandbox);
let flat=[];function walk(n){if(typeof n==='string')return;flat.push(n);n.children.forEach(walk);}walk(root);
if(input.openRef){const a=flat.find(n=>n.tag==='a'&&n.textContent===input.openRef);if(a)a.onclick({preventDefault(){}});}
process.stdout.write(JSON.stringify({text:root.textContent,layout:root.dataset.layout,markupExecuted,networkCalls,nodes:flat.map(n=>({tag:n.tag,text:n.textContent,className:n.className,id:n.id,href:n.href,open:!!n.open,scrolled:!!n.scrolled}))}));
'''


@unittest.skipUnless(shutil.which('node'), 'Node required for analysis presentation tests')
class AnalysisReportTests(unittest.TestCase):
    def task(self, mode='business_logic'):
        source=dict(id='S1',project_path='/workspace/orders',path='src/orders.py',line_start=10,line_end=20,sha256='a'*64)
        return dict(kind='analysis',title='理解订单取消',summary='分析摘要',scope='只分析订单取消源码',analysis=dict(
            mode=mode,question='订单什么时候可以取消？',conclusion='未支付订单可以取消，已支付分支拒绝。',sources=[source],
            steps=[dict(id='N1',title='取消入口',description='控制器接收订单编号。',source_ids=['S1'])],
            rules=[dict(id='R1',condition='订单已支付',outcome='拒绝取消，不释放库存。',source_ids=['S1'])],
            mappings=[dict(id='M1',**{'from':'order.amount_cent','to':'view.paidAmount'},transformation='除以100，保留两位。',source_ids=['S1'])],
            findings=[dict(id='F1',classification='fact',statement='状态检查先于库存更新。',source_ids=['S1']),dict(id='F2',classification='inference',statement='推断重试可能走相同入口。',source_ids=['S1']),dict(id='F3',classification='unknown',statement='未读取消息消费者。',source_ids=[])],
            gaps=[dict(id='G1',description='消息消费者仓库尚未提供。',next_action='补充消费者项目后继续追踪。')]),analysis_assessment=dict(sources=[dict(source,status='current',reason='内容与范围匹配')]))

    def run_ui(self, task, open_ref=None):
        result=subprocess.run(['node','-e',DOM],input=json.dumps(dict(source=(ASSETS/'views/analysis.js').read_text(encoding='utf-8'),task=task,openRef=open_ref)),text=True, encoding='utf-8',capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def test_logic_has_rule_and_entry_structure_without_development_or_acceptance(self):
        view=self.run_ui(self.task())
        self.assertEqual(view['layout'],'analysis-business_logic')
        for text in ('业务入口与主流程','条件规则与异常分支','订单已支付','拒绝取消，不释放库存。','只读追踪源码','未执行项目'):
            self.assertIn(text,view['text'])
        self.assertTrue(any(n['className']=='analysis-rule' for n in view['nodes']))
        self.assertFalse(any(n['tag']=='table' for n in view['nodes']))
        for text in ('按这些步骤验收','本轮实际完成的内容','停用与恢复','填写通过'):
            self.assertNotIn(text,view['text'])

    def test_data_flow_is_field_mapping_table_and_trace_sequence(self):
        view=self.run_ui(self.task('data_flow'))
        self.assertEqual(view['layout'],'analysis-data_flow')
        for text in ('已追到的数据流转','字段映射与转换','order.amount_cent','view.paidAmount','除以100，保留两位。'):
            self.assertIn(text,view['text'])
        self.assertTrue(any(n['tag']=='table' for n in view['nodes']))
        self.assertFalse(any(n['className']=='analysis-rule' for n in view['nodes']))
        self.assertNotIn('条件规则与异常分支',view['text'])

    def test_facts_inferences_unknown_and_gaps_remain_distinct(self):
        view=self.run_ui(self.task())
        for label in ('源码事实','推断','未知','链路断点与未覆盖范围','补充消费者项目后继续追踪。'):
            self.assertIn(label,view['text'])
        groups=[n['className'] for n in view['nodes'] if n['className'] and n['className'].startswith('analysis-finding-group')]
        self.assertEqual(groups,['analysis-finding-group analysis-findings-fact','analysis-finding-group analysis-findings-inference','analysis-finding-group analysis-findings-unknown'])
        self.assertNotIn('链路已跑通',view['text'])

    def test_stale_or_unavailable_sources_do_not_present_current_facts(self):
        for state,label in [('stale','源码已变化'),('unavailable','来源不可读取'),('invalid','来源无效')]:
            with self.subTest(state=state):
                task=self.task();task['analysis_assessment']['sources'][0].update(status=state,reason='请核对源文件')
                view=self.run_ui(task)
                self.assertIn(label,view['text']);self.assertIn('依据待复核',view['text'])
                self.assertNotIn('当前源码匹配',view['text'])
                self.assertIn('请核对源文件',view['text'])
                self.assertNotIn('源码事实',view['text'])

    def test_gap_dispositions_explain_work_without_acceptance_controls(self):
        task=self.task();task['analysis']['gaps']=[
            dict(id='G1',description='本地分支待查',next_action='继续查源码'),
            dict(id='G2',description='缺少下游源码',next_action='补充项目路径',disposition='needs_input'),
            dict(id='G3',description='运行时数据',next_action='另行确定范围',disposition='out_of_scope')]
        view=self.run_ui(task)
        for label in ('G1 · 待继续查证','G2 · 需要补充材料','G3 · 本轮范围外'):
            self.assertIn(label,view['text'])
        self.assertFalse(any(n['tag'] in {'button','select','input'} for n in view['nodes']))

    def test_recorded_and_current_source_versions_are_separate(self):
        task=self.task();source=task['analysis_assessment']['sources'][0]
        source.update(status='stale',current_sha256='b'*64,current_line_count=25)
        view=self.run_ui(task,open_ref='S1')
        self.assertIn('记录时 SHA256',view['text']);self.assertIn('本次观察 SHA256',view['text'])
        self.assertIn('a'*64,view['text']);self.assertIn('b'*64,view['text'])
        self.assertIn('不证明解释正确',view['text'])

    def test_unknown_source_status_is_not_assumed_current(self):
        task=self.task();task.pop('analysis_assessment')
        view=self.run_ui(task)
        self.assertIn('来源未核对',view['text']);self.assertIn('依据待复核',view['text'])
        self.assertNotIn('当前源码匹配',view['text'])

    def test_source_reference_expands_only_local_evidence_detail(self):
        view=self.run_ui(self.task(),open_ref='S1')
        source=next(n for n in view['nodes'] if n['className']=='analysis-source')
        self.assertTrue(source['open']);self.assertTrue(source['scrolled'])
        self.assertIn('src/orders.py',source['text']);self.assertIn('10–20',source['text'])
        links=[n for n in view['nodes'] if n['tag']=='a']
        self.assertTrue(links);self.assertTrue(all(n['href'].startswith('#analysis-source-') for n in links))
        self.assertEqual(view['networkCalls'],0)

    def test_missing_analysis_material_has_clear_empty_states(self):
        view=self.run_ui(dict(kind='analysis',analysis={}))
        for text in ('尚未形成分析结论','尚未记录可追溯的入口','本轮未单列条件规则','尚无源码引用','这不表示不存在未发现的分支'):
            self.assertIn(text,view['text'])
        self.assertFalse(any(n['tag'] in {'button','input','select','textarea'} for n in view['nodes']))

    def test_untrusted_analysis_values_are_literal_text_with_no_markup_or_requests(self):
        task=self.task();payload='<img src="https://example.invalid/x" onerror="markupExecuted=true"><script>markupExecuted=true</script>'
        task['analysis']['question']=payload;task['analysis']['findings'][0]['statement']=payload
        task['analysis_assessment']['sources'][0]['path']=payload
        view=self.run_ui(task)
        self.assertIn(payload,view['text']);self.assertFalse(view['markupExecuted']);self.assertEqual(view['networkCalls'],0)
        self.assertFalse(any(n['tag'] in {'img','script','iframe'} for n in view['nodes']))

    def test_report_shell_routes_analysis_and_suppresses_generic_stage_materials(self):
        template=(ASSETS/'report.html').read_text(encoding='utf-8')
        self.assertIn("const isAnalysis=task.kind==='analysis'",template)
        self.assertIn('const renderView=isAnalysis?renderAnalysisView:',template)
        self.assertIn("if(!stageInline&&!isAnalysis)renderStages",template)
        self.assertIn("tabs.filter(([key])=>!isAnalysis",template)
        self.assertIn('if(!isAnalysis)story.append(checks)',template)
        self.assertIn("(task.analysis||{}).conclusion||task.summary",template)
        self.assertIn('补充线索或纠正理解（选填）',template)
        self.assertIn('const pendingDecisions=(isAnalysis?[]:',template)
