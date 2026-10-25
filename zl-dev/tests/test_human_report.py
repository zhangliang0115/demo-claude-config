"""Execute presentation logic with a small DOM to check action and feedback semantics."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
DOM = r'''
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.value='';this.dataset={};this.classList={add(){}};this._text='';}
 append(...xs){this.children.push(...xs);}
 insertBefore(node,target){const i=this.children.indexOf(target);this.children.splice(i<0?this.children.length:i,0,node);}
 replaceChildren(...xs){this.children=xs;this._text='';}
 setAttribute(k,v){this.attributes[k]=v;}
 set innerHTML(value){throw new Error('Task content must not be parsed as markup');}
 get textContent(){return this._text+this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
 set textContent(x){this._text=String(x);this.children=[];}
 focus(){} select(){} setSelectionRange(){}
}
const ids={},composers=[];let copied='';
const document={createElement:t=>new Element(t),getElementById:id=>ids[id]||(ids[id]=new Element(id)),createTextNode:x=>String(x),querySelector:()=>new Element('footer')};
const sandbox={document,URL,navigator:{clipboard:{writeText:async value=>{copied=value;}}},formatTimes:x=>String(x),console};
sandbox.feedbackComposer=(parent,task,stage,body)=>{composers.push(body);return ()=>{};};
vm.createContext(sandbox);
if(input.kind==='changes'){
 vm.runInContext(input.source,sandbox);sandbox.task=input.task;sandbox.root=new Element('section');sandbox.changesExecuted=false;
 vm.runInContext('renderRoundChanges(root,task.changes)',sandbox);
 const flat=[];function walk(n){if(typeof n==='string')return;flat.push(n);n.children.forEach(walk);}walk(sandbox.root);
 process.stdout.write(JSON.stringify({text:sandbox.root.textContent,hidden:sandbox.root.hidden,executed:sandbox.changesExecuted,nodes:flat.map(n=>({tag:n.tag,text:n.textContent,className:n.className,open:!!n.open}))}));
}else if(input.kind==='composer'){
 vm.runInContext(input.source,sandbox);sandbox.task=input.task;sandbox.root=new Element('root');sandbox.body=input.body;
 vm.runInContext("feedbackComposer(root,task,'人工核验',()=>body)",sandbox);
 const flat=[];function walk(n){if(typeof n==='string')return;flat.push(n);n.children.forEach(walk);}walk(sandbox.root);
 const preview=flat.find(n=>n.tag==='textarea'),button=flat.find(n=>n.tag==='button');
 button.onclick().then(()=>process.stdout.write(JSON.stringify({text:sandbox.root.textContent,preview:preview.value,copied,disabled:button.disabled})));
}else if(input.kind==='evidence'){vm.runInContext(input.source,sandbox);sandbox.evidence=input.task;process.stdout.write(JSON.stringify({text:vm.runInContext('evidenceOrigin(evidence)',sandbox)}));
}else if(input.kind.startsWith('scene-')){
 vm.runInContext(input.source,sandbox);sandbox.task=input.task;sandbox.root=new Element('root');
 sandbox.ui={el:(tag,text,cls)=>{const n=new Element(tag);if(text!==undefined)n.textContent=text;return n;},text:x=>x===undefined?'尚未记录':typeof x==='string'?x:JSON.stringify(x),show:()=>{},card:(parent,title,body)=>{const n=new Element('article');n.textContent=title+' '+(body||'');parent.append(n);return n;},list:(parent,title,items)=>{if(items.length){const n=new Element('section');n.textContent=title+' '+items.join('；');parent.append(n);}}};
 vm.runInContext(input.function+'(root,task,ui)',sandbox);process.stdout.write(JSON.stringify({text:sandbox.root.textContent}));
}else if(input.kind==='stage'){
 vm.runInContext(input.source,sandbox);sandbox.task=input.task;sandbox.root=new Element('root');vm.runInContext('renderStages(root,task)',sandbox);
 const flat=[];const walk=n=>{if(typeof n==='string')return;flat.push(n);n.children.forEach(walk);};walk(sandbox.root);
 if(input.draft){const select=flat.find(n=>n.tag==='select'&&n.children.some(c=>c.value==='fail'));select.value='fail';select.onchange();const area=flat.find(n=>n.tag==='textarea'&&!n.readOnly);area.value='本次发现仍有错误';area.oninput();}
 process.stdout.write(JSON.stringify({text:sandbox.root.textContent,nodes:flat.map(n=>({tag:n.tag,text:n.textContent,value:n.value,href:n.href,readOnly:n.readOnly,open:!!n.open,className:n.className})),feedback:composers.map(f=>f())}));
}else{
 ids['task-data']=new Element('script');ids['task-data'].textContent=JSON.stringify(input.task);
 vm.runInContext(input.source,sandbox);const all=[];function walk(n){if(typeof n==='string')return;all.push(n);n.children.forEach(walk);}walk(ids.overview);process.stdout.write(JSON.stringify({text:ids.overview.textContent,owner:ids.overview.children[1].children[0].dataset.actionOwner,blockerText:all.filter(n=>n.className==='current-blockers').map(n=>n.textContent).join(' ')}));
}
'''

@unittest.skipUnless(shutil.which('node'), 'Node required for presentation execution')
class HumanReportTests(unittest.TestCase):
    def run_ui(self, task, kind='stage', draft=False, body='本次意见'):
        if kind == 'changes':
            template=(ASSETS / 'report.html').read_text()
            helpers='function el(tag,text,cls){'+template.split('function el(tag,text,cls){',1)[1].split('function feedbackComposer(',1)[0]
            source=helpers+'function renderRoundChanges(parent, changes){'+template.split('function renderRoundChanges(parent, changes){',1)[1].split("renderRoundChanges($('round-changes'),task.changes);",1)[0]
        elif kind == 'composer':
            source=(ASSETS / 'report.html').read_text().split('function el(tag,text,cls){',1)[1].split('function evidenceOrigin(e){',1)[0]
            source='function el(tag,text,cls){'+source
        elif kind == 'evidence':
            source=(ASSETS / 'report.html').read_text().split('function evidenceOrigin(e){',1)[1].split('function card(',1)[0]
            source='function evidenceOrigin(e){'+source
        elif kind.startswith('scene-'):
            name = kind.removeprefix('scene-')
            helper=(ASSETS / 'report.html').read_text().split('function evidenceOrigin(e){',1)[1].split('function card(',1)[0]
            source='function evidenceOrigin(e){'+helper+'\n'+(ASSETS / 'views' / (name+'.js')).read_text()
        elif kind == 'stage':
            source = (ASSETS / 'stages.js').read_text()
        else:
            source = (ASSETS / 'report.html').read_text().split("'use strict';", 1)[1].split('// VIEW_SCRIPT', 1)[0]
        result = subprocess.run(['node', '-e', DOM], input=json.dumps(dict(source=source, task=task, kind=kind, draft=draft, body=body, function={'scene-bugfix':'renderBugfixView','scene-incident':'renderIncidentView','scene-operations':'renderOperationsView','scene-engineering':'renderEngineeringView'}.get(kind,''))), text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def task(self):
        return dict(id='T1', title='名额调整', focus_stage='acceptance',current_fingerprint='current', stage_catalog={'acceptance':{'title':'人工验收','fields':[['scenario','场景'],['instruction','操作'],['expected','预期'],['actual','观察'],['reviewer','核验人'],['result','结果'],['reviewed_revision','版本'],['verification_mode','核验方式']]}}, stage_details={'acceptance':{'summary':'核验关键路径','items':[dict(id='AC1',scenario='保存',instruction='填写3并保存',expected='显示3',actual='显示旧值',reviewer='张三',result='退回',reviewed_revision='old',verification_mode='assisted')]}})

    def test_round_changes_empty_values_hide_the_entire_region(self):
        for changes in [None, [], ['', '  ', None]]:
            with self.subTest(changes=changes):
                result=self.run_ui({'changes':changes},'changes')
                self.assertTrue(result['hidden'])
                self.assertEqual('',result['text'])
                self.assertFalse(any(n['tag'] in {'h2','select','button'} for n in result['nodes']))

    def test_round_changes_single_item_is_direct_without_material_selection(self):
        result=self.run_ui({'changes':['审核期间继续公开旧版本']},'changes')
        self.assertFalse(result['hidden'])
        self.assertIn('本轮变化',result['text'])
        rows=[n for n in result['nodes'] if n['tag']=='li']
        self.assertEqual(['审核期间继续公开旧版本'],[n['text'] for n in rows])
        self.assertFalse(any(n['tag'] in {'details','select','button'} for n in result['nodes']))

    def test_round_changes_five_items_show_three_and_fold_two_without_duplicates(self):
        changes=['变化'+str(i) for i in range(1,6)]
        result=self.run_ui({'changes':changes+[changes[0],'  '+changes[1]+'  ']},'changes')
        visible=next(n for n in result['nodes'] if n.get('className')=='round-change-list')
        remaining=next(n for n in result['nodes'] if n.get('className')=='round-change-more-list')
        fold=next(n for n in result['nodes'] if n.get('className')=='round-change-more')
        self.assertEqual('变化1 变化2 变化3',visible['text'])
        self.assertEqual('变化4 变化5',remaining['text'])
        self.assertFalse(fold['open'])
        self.assertIn('还有 2 项变化',fold['text'])
        for change in changes:self.assertEqual(1,result['text'].count(change))
        template=(ASSETS / 'report.html').read_text()
        self.assertNotIn("list(checks,'自上次更新后的变化'",template)
        self.assertLess(template.index('id="round-changes"'),template.index('id="overview"'))

    def test_round_changes_task_markup_stays_literal_text(self):
        markup='<img src=x onerror="changesExecuted=true"><script>changesExecuted=true</script>'
        result=self.run_ui({'changes':[markup]},'changes')
        self.assertFalse(result['executed'])
        self.assertEqual([markup],[n['text'] for n in result['nodes'] if n['tag']=='li'])
        self.assertFalse(any(n['tag'] in {'script','img','iframe'} for n in result['nodes']))

    def test_real_feedback_composer_copies_record_assessment_and_code_versions(self):
        task=self.task();task.update(task_revision='record-v2',assessment_revision='assessment-v3')
        result=self.run_ui(task,'composer',body='result_status=fail\n本次观察不符')
        for text in ['代码/行为版本：current','页面记录版本：record-v2','页面评估版本：assessment-v3','result_status=fail','任一不同或未知']:
            self.assertIn(text,result['copied'])
        self.assertEqual(result['preview'],result['copied'])
        self.assertNotIn('页面版本：',result['copied'])

    def test_old_page_copied_versions_are_explicitly_unknown(self):
        result=self.run_ui(self.task(),'composer')
        self.assertIn('页面记录版本：未知（旧页面未记录）',result['copied'])
        self.assertIn('页面评估版本：未知（旧页面未记录）',result['copied'])

    def test_automated_mode_is_not_presented_as_manual_or_a_pass(self):
        task=self.task();task['stage_details']['acceptance']['items'][0]['verification_mode']='automated'
        result=self.run_ui(task)
        self.assertIn('自动化专项：由 AI 执行并核对证据',result['text'])
        self.assertNotIn('人工核验：按操作步骤亲自观察',result['text'])
        self.assertEqual([''],result['feedback'])

    def test_backend_human_review_completion_is_stage_specific_and_draft_optional(self):
        task=self.task();task['workflow_summary']={'focus_stage':'acceptance','human_verification':{'stage':'acceptance','all_current_passed':True,'by_stage':{'acceptance':{'all_current_passed':True},'release':{'all_current_passed':False}}}}
        result=self.run_ui(task)
        self.assertIn('查看本版核验结果',result['text'])
        self.assertNotIn('请逐项核验本次交付',result['text'])
        corrections=[n for n in result['nodes'] if n.get('className')=='review-correction']
        self.assertEqual(1,len(corrections))
        self.assertFalse(corrections[0]['open'])
        self.assertIn('补充或更正（选填）',corrections[0]['text'])
        self.assertIn('仅用于补充或更正',result['text'])
        self.assertIn('不自动放行',result['text'])
        self.assertEqual([''],result['feedback'])
        task['workflow_summary']['human_verification']['by_stage']['acceptance']['all_current_passed']=False
        self.assertNotIn('人工核验已记录完成',self.run_ui(task)['text'])

    def test_delegated_completion_is_read_only_without_personal_recheck_or_signature(self):
        task=self.task();item=task['stage_details']['acceptance']['items'][0]
        item.update(result_status='pass',reviewer_kind='ai',reviewer='AI',reviewed_revision='current',verification_mode='manual')
        item['acceptance_delegation']=dict(kind='acceptance',revision='current',source='请按标准替我验收',criteria='保存后刷新保持')
        task['workflow_summary']={'focus_stage':'acceptance','primary_action':{'owner':'none','kind':'delegated_reviewed','title':'本版受托验收完成'},'acceptance_verification':{'all_current_passed':True,'delegated_ids':['AC1']}}
        result=self.run_ui(task)
        for expected in ['查看本版核验结果','请按标准替我验收','保存后刷新保持','不包含发布授权','不等于真实人的签字']:
            self.assertIn(expected,result['text'])
        self.assertNotIn('亲自观察',result['text'])
        self.assertNotIn('请逐项核验',result['text'])
        self.assertFalse(next(n for n in result['nodes'] if n.get('className')=='review-correction')['open'])
        self.assertFalse(next(n for n in result['nodes'] if n.get('className')=='delegation-basis')['open'])
        overview=self.run_ui(task,'overview')
        self.assertIn('当前无需你处理',overview['text'])
        self.assertNotIn('AI 继续处理',overview['text'])
        self.assertNotIn('AI 需先处理当前阻塞',overview['text'])

    def test_pending_delegated_acceptance_does_not_request_personal_observation(self):
        task=self.task();task['workflow_summary']={'focus_stage':'acceptance','primary_action':{'owner':'AI','kind':'delegated_accept'},'acceptance_verification':{'delegated_ids':['AC1']}}
        task['stage_details']['acceptance']['items'][0]['acceptance_delegation']=dict(kind='acceptance',revision='current',source='按标准代我验收',criteria='刷新保持')
        result=self.run_ui(task)
        self.assertIn('AI 按委托继续验收',result['text'])
        self.assertIn('无需人重复操作',result['text'])
        self.assertNotIn('亲自观察',result['text'])

    def test_result_status_display_does_not_turn_ai_record_into_human_acceptance(self):
        task=self.task();task['stage_details']['acceptance']['items'][0].update(result_status='pass',reviewer_kind='ai',reviewed_revision='current')
        result=self.run_ui(task)
        self.assertIn('结果状态：符合预期（pass）',result['text'])
        self.assertIn('不等于真实人的签字',result['text'])
        self.assertEqual([''],result['feedback'])

    def test_completed_review_folds_setup_and_empty_stage_intro_is_omitted(self):
        task=self.task();task['stage_details']['acceptance']['summary']=''
        task['workflow_summary']={'focus_stage':'acceptance','human_verification':{'by_stage':{'acceptance':{'all_current_passed':True}}}}
        result=self.run_ui(task)
        folds=[n for n in result['nodes'] if n.get('className')=='review-environment']
        self.assertEqual(1,len(folds))
        self.assertFalse(folds[0]['open'])
        self.assertIn('复核环境（需要重查时展开）',folds[0]['text'])
        self.assertFalse(any(n['tag']=='p' and n['text']=='尚未记录' for n in result['nodes']))
        task['workflow_summary']['human_verification']['by_stage']['acceptance']['all_current_passed']=False
        result=self.run_ui(task)
        self.assertFalse(any(n.get('className')=='review-environment' for n in result['nodes']))
        self.assertIn('开始核验前',result['text'])

    def test_human_feedback_heading_waits_for_ai_instead_of_requesting_reverification(self):
        task=self.task();task['workflow_summary']={'focus_stage':'acceptance','primary_action':{'owner':'AI','kind':'human_feedback','title':'处理人工退回'}}
        result=self.run_ui(task)
        self.assertIn('查看退回项，等待 AI 处理',result['text'])
        self.assertNotIn('请逐项核验本次交付',result['text'])
        self.assertFalse(any(n.get('className')=='review-correction' for n in result['nodes']))
        task['workflow_summary']['primary_action']['kind']='human_reviewed'
        self.assertIn('查看本版核验结果',self.run_ui(task)['text'])

    def test_not_checked_is_normal_and_does_not_create_an_empty_record(self):
        task=self.task();item=task['stage_details']['acceptance']['items'][0]
        item.update(result_status='not_checked',actual='',reviewer='',result='')
        result=self.run_ui(task)
        self.assertNotIn('已记录的核验结果（只读）',result['text'])
        self.assertNotIn('未知（not_checked）',result['text'])
        item['actual']='已有观察，尚未形成结论'
        result=self.run_ui(task)
        self.assertIn('结果状态：尚未核验（not_checked）',result['text'])
        self.assertIn('已有观察，尚未形成结论',result['text'])
        self.assertEqual([''],result['feedback'])

    def test_recorded_result_is_visible_but_new_draft_remains_unchecked(self):
        result=self.run_ui(self.task())
        for value in ['张三','显示旧值','退回','历史版本核验记录','需要 AI 协助']:
            self.assertIn(value,result['text'])
        drafts=[n for n in result['nodes'] if n['tag']=='select']
        self.assertEqual('pending',drafts[-1]['value'])
        self.assertEqual([''],result['feedback'])

    def test_new_feedback_does_not_copy_old_human_observation(self):
        result=self.run_ui(self.task(),draft=True)
        self.assertIn('本次发现仍有错误',result['feedback'][0])
        self.assertIn('result_status=fail',result['feedback'][0])
        self.assertNotIn('显示旧值',result['feedback'][0])
        self.assertNotIn('张三',result['feedback'][0])

    def test_missing_preparation_and_unbound_review_are_explicit(self):
        task=self.task();del task['stage_details']['acceptance']['items'][0]['reviewed_revision']
        result=self.run_ui(task)
        self.assertIn('准备未记录',result['text'])
        self.assertIn('核验版本未绑定',result['text'])
        self.assertIn('AI 或测试角色记录不等于',result['text'])

    def test_setup_commands_only_copy_and_links_use_safe_protocols(self):
        task=self.task();task['acceptance_setup']=dict(entry_url='javascript:alert(1)',prepare_command='python preview.py')
        result=self.run_ui(task)
        self.assertFalse(any(n.get('href') for n in result['nodes']))
        self.assertTrue(any(n.get('readOnly') and n['value']=='python preview.py' for n in result['nodes']))
        task['acceptance_setup']['entry_url']='http://127.0.0.1:18922/'
        result=self.run_ui(task)
        self.assertTrue(any(n.get('href')=='http://127.0.0.1:18922/' for n in result['nodes']))

    def test_setup_visible_even_before_acceptance_items_exist(self):
        task=self.task();task['stage_details']['acceptance']['items']=[]
        self.assertIn('开始核验前',self.run_ui(task)['text'])

    def test_result_data_without_backend_source_is_still_a_claim(self):
        evidence=dict(parsed_result={'counts':{'passed':99}},status='passed')
        self.assertIn('模型记录',self.run_ui(evidence,'evidence')['text'])
        evidence['verification_source']='parsed_result'
        self.assertIn('结构化结果已解析',self.run_ui(evidence,'evidence')['text'])
        evidence['verification_source']='invalid'
        self.assertIn('不可采信',self.run_ui(evidence,'evidence')['text'])

    def test_human_decision_displays_recommendation_only_once(self):
        task=self.task();task.update(summary='可调整名额',decisions=[dict(id='D1',question='允许导出哪些客户？',status='pending',recommendation='仅导出本人权限范围',options=['本人权限范围','全部'])],workflow_summary=dict(focus_stage='solution',primary_action=dict(owner='你',kind='decide',title='请确认：允许导出哪些客户？；建议：仅导出本人权限范围',reason='业务边界需要确认')))
        result=self.run_ui(task,'report')
        self.assertEqual(1,result['text'].count('允许导出哪些客户？'))
        self.assertEqual(1,result['text'].count('仅导出本人权限范围'))
        self.assertIn('现在需要你',result['text'])

    def test_ai_primary_action_wins_over_unrelated_pending_decision(self):
        task=self.task();task.update(summary='可调整名额',decisions=[dict(id='D1',question='选哪个布局',status='pending',options=['A','B'])],workflow_summary=dict(focus_stage='acceptance',primary_action=dict(owner='AI',title='修复并发重复提交',reason='P1 未解决'),blockers=[dict(type='review',summary='重复扣款',severity='P1'),dict(type='decision',summary='选哪个布局')],verification=dict(missing_behavior_ids=['B1'],current_unresolved_evidence_ids=['E1'],historical_evidence_count=2)))
        result=self.run_ui(task,'report')
        self.assertIn('AI 继续处理',result['text'])
        self.assertIn('修复并发重复提交',result['text'])
        self.assertIn('P1 未解决',result['text'])
        self.assertIn('其他待决与反馈（AI 需先处理当前阻塞）',result['text'])
        self.assertNotIn('待你确认',result['text'])
        self.assertEqual('AI',result['owner'])
        self.assertIn('重复扣款',result['blockerText'])
        self.assertNotIn('选哪个布局',result['blockerText'])
        self.assertIn('选哪个布局',result['text'])

    def test_effective_review_wins_over_raw_acceptance_in_stage_materials(self):
        task=self.task();task['workflow_summary']={'focus_stage':'review'}
        task['stage_catalog']['review']={'title':'风险审查','fields':[['finding','问题']]}
        task['stage_details']['review']={'items':[dict(id='R1',status='pending',severity='P0',finding='需要先修复')]}
        result=self.run_ui(task)
        self.assertIn('需要先修复',result['text'])
        self.assertNotIn('开始核验前',result['text'])
        self.assertNotIn('填写3并保存',result['text'])

    def test_scene_views_distinguish_parsed_claim_and_invalid_evidence(self):
        for scene in ['bugfix','incident','operations','engineering']:
            for source,label in [('parsed_result','结构化结果已解析'),('claim','模型记录'),('invalid','不可采信')]:
                with self.subTest(scene=scene,source=source):
                    task=dict(kind='refactor',focus_stage='review',evidence=[dict(id='E1',status='passed',summary='检查记录',verification_source=source)],workflow_summary={'focus_stage':'review'})
                    self.assertIn(label,self.run_ui(task,'scene-'+scene)['text'])

    def test_incident_uses_backend_current_counts_and_old_payload_stays_unknown(self):
        task=dict(focus_stage='acceptance',evidence=[dict(id='old',status='passed',freshness='过期或未绑定：需重新验证')],workflow_summary=dict(focus_stage='review',verification=dict(current_status_counts={'passed':0},historical_evidence_count=1)))
        result=self.run_ui(task,'scene-incident')['text']
        self.assertIn('当前标记通过 0 条',result)
        self.assertIn('历史记录 1 条',result)
        self.assertNotIn('人工恢复核验',result)
        del task['workflow_summary']['verification']
        self.assertIn('当前通过与历史数量尚未核对',self.run_ui(task,'scene-incident')['text'])

    def test_specialized_acceptance_uses_structured_items_only_in_relevant_phase(self):
        for scene in ['bugfix','engineering','operations','incident']:
            task=self.task();task.update(kind='refactor',acceptance=['旧版兼容不应覆盖结构化'])
            task['workflow_summary']={'focus_stage':'review'}
            result=self.run_ui(task,'scene-'+scene)['text']
            self.assertNotIn('旧版兼容不应覆盖结构化',result)
            self.assertNotIn('填写3并保存',result)
            task['workflow_summary']['focus_stage']='acceptance'
            result=self.run_ui(task,'scene-'+scene)['text']
            self.assertIn('填写3并保存',result)
            self.assertNotIn('旧版兼容不应覆盖结构化',result)

if __name__=='__main__':unittest.main()
