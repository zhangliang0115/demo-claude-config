"""Explicit subprocess execution and bounded, independently reparsed test receipts."""
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

CAP = 16 * 1024 * 1024
DISCLAIMER = '日志解析不等价业务覆盖或身份认证；本地文件可被有权限者伪造。'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def read_limited(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(CAP + 1)
    if len(raw) > CAP:
        raise ValueError('结果文件超过解析上限')
    return raw

def parse_result(fmt, raw, exit_code):
    counts = dict(total=0, passed=0, failed=0, errors=0, skipped=0)
    if fmt == 'unittest':
        text = raw.decode('utf-8', 'replace')
        runs = re.findall(r'^Ran (\d+) tests? in [^\n]+$', text, re.M)
        ends = re.findall(r'^(OK|FAILED)(?: \(([^\n]*)\))?\s*$', text, re.M)
        if len(runs) != 1 or len(ends) != 1:
            raise ValueError('缺少唯一 unittest 执行摘要')
        counts['total'] = int(runs[0])
        verdict, details = ends[0]
        if details and not re.fullmatch(r'(?:failures|errors|skipped|expected failures|unexpected successes)=\d+(?:, (?:failures|errors|skipped|expected failures|unexpected successes)=\d+)*', details):
            raise ValueError('unittest 摘要包含不支持字段')
        for key, field in [('failures','failed'), ('errors','errors'), ('skipped','skipped'), ('expected failures','skipped'), ('unexpected successes','failed')]:
            match = re.search(r'(?:^|, )' + key + r'=(\d+)(?:,|$)', details)
            if match:
                counts[field] += int(match[1])
        if verdict == 'FAILED' and not counts['failed'] and not counts['errors']:
            raise ValueError('FAILED 摘要没有可解析失败数量')
        if verdict == 'OK' and (counts['failed'] or counts['errors']):
            raise ValueError('unittest 摘要矛盾')
    elif fmt == 'junit':
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('JUnit 不允许 DTD/entity')
        doc = ET.fromstring(raw)
        if doc.tag not in {'testsuite','testsuites'}:
            raise ValueError('不支持的 JUnit 根元素')
        allowed_suite={'testsuite','testsuites','testcase','properties','system-out','system-err'}
        allowed_case={'failure','error','skipped','properties','system-out','system-err'}
        for node in doc.iter():
            allowed = allowed_suite if node.tag in {'testsuite','testsuites'} else (allowed_case if node.tag=='testcase' else None)
            if allowed is not None and any(child.tag not in allowed for child in node):
                raise ValueError('JUnit 包含不支持的结果元素')
        cases = list(doc.iter('testcase'))
        counts['total'] = len(cases)
        for case in cases:
            outcomes = [name for name in ('failure','error','skipped') if case.find(name) is not None]
            if len(outcomes) > 1:
                raise ValueError('JUnit testcase 结果冲突')
            if outcomes:
                counts[{'failure':'failed','error':'errors','skipped':'skipped'}[outcomes[0]]] += 1
        parents={child: parent for parent in doc.iter() for child in parent}
        for node, parent in parents.items():
            if node.tag in {'failure','error','skipped'} and parent.tag != 'testcase':
                raise ValueError('不支持的套件级失败或跳过结果')
        # Validate every aggregate, including root/nested testsuites.
        for suite in (node for node in doc.iter() if node.tag in {'testsuite','testsuites'}):
            descendants=list(suite.iter('testcase'))
            actual={'tests':len(descendants),'failures':sum(c.find('failure') is not None for c in descendants),'errors':sum(c.find('error') is not None for c in descendants),'skipped':sum(c.find('skipped') is not None for c in descendants)}
            for attr, value in actual.items():
                if attr in suite.attrib and int(suite.attrib[attr]) != value:
                    raise ValueError('JUnit 统计与 testcase 不符')
    else:
        raise ValueError('不支持的结果格式')
    counts['passed'] = counts['total'] - counts['failed'] - counts['errors'] - counts['skipped']
    if counts['passed'] < 0:
        raise ValueError('统计超出执行总数')
    status = 'failed' if exit_code != 0 or counts['failed'] or counts['errors'] else ('passed' if counts['passed'] > 0 and counts['skipped'] == 0 else 'not_run')
    return dict(format=fmt, counts=counts, status=status)

def utc():
    return datetime.now(timezone.utc).isoformat()

def execute(task_dir, project, fmt, behaviors, argv, result_file=None, timeout=120):
    import reviewable as api
    folder, project = Path(task_dir).resolve(), Path(project).resolve()
    raw = (folder/'task.json').read_bytes()
    task = api.validate(json.loads(raw))
    if not task.get('project_path') or Path(task['project_path']).resolve() != project:
        raise ValueError('任务绑定项目与 --project 不匹配')
    known = {b['id'] for b in task.get('behaviors',[])}
    if not behaviors or any(b not in known for b in behaviors):
        raise ValueError('verify 必须引用已有行为')
    if not argv or not math.isfinite(timeout) or timeout <= 0 or timeout > 3600:
        raise ValueError('必须提供显式 argv，timeout 范围 1..3600 秒')
    if fmt == 'junit' and not result_file:
        raise ValueError('JUnit 必须指定 --result-file')
    report = Path(result_file).expanduser() if result_file else None
    if report and not report.is_absolute():
        report = project/report
    # A pre-existing result cannot prove this command executed its tests.
    if report and report.exists():
        raise ValueError('JUnit 结果文件已存在；请为本次运行使用新路径')
    run_id = 'verify-' + uuid.uuid4().hex
    run = folder/'runs'/run_id
    run.mkdir(parents=True)
    receipt = dict(version=1, run_id=run_id, task_id=task['id'], task_dir=str(folder), project_path=str(project), behavior_ids=list(dict.fromkeys(behaviors)), argv=argv, cwd=str(project), started_at=utc(), task_revision_before=api.task_revision(raw), fingerprint_before=api.fingerprint(folder), format=fmt, disclaimer=DISCLAIMER)
    stdout, stderr = run/'stdout.log', run/'stderr.log'
    timed_out, code, execution_error = False, None, ''
    proc = None
    with stdout.open('wb') as out, stderr.open('wb') as err:
        try:
            proc = subprocess.Popen(argv, cwd=project, shell=False, stdout=out, stderr=err, start_new_session=(os.name=='posix'))
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True
                if os.name == 'posix':
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                    # Kill descendants even if group leader already exited.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                    if proc.poll() is None:
                        proc.kill()
                code=proc.wait()
        except OSError as exc:
            execution_error=type(exc).__name__ + ': ' + str(exc)
    try:
        after_revision=api.task_revision((folder/'task.json').read_bytes())
    except OSError:
        after_revision=None
    receipt.update(finished_at=utc(), exit_code=code, timed_out=timed_out, execution_error=execution_error, fingerprint_after=api.fingerprint(folder), task_revision_after=after_revision)
    logs={}
    for name in ('stdout','stderr'):
        path=run/(name+'.log')
        logs[name]=dict(path=path.name,sha256=file_sha(path))
    receipt['logs']=logs
    parsed=None
    try:
        if timed_out or execution_error:
            raise ValueError('执行超时或未启动')
        if fmt=='junit':
            result=read_limited(report)
            (run/'result.xml').write_bytes(result)
            receipt['result_file']=dict(path='result.xml',sha256=sha(result))
        else:
            result=read_limited(stdout)+b'\n'+read_limited(stderr)
        parsed=parse_result(fmt,result,code)
        receipt['parsed_result']=parsed
    except (ValueError,OSError,ET.ParseError) as exc:
        receipt['parse_error']=str(exc)
    stable = bool(receipt['fingerprint_before']) and receipt['fingerprint_before']==receipt['fingerprint_after'] and receipt['task_revision_before']==receipt['task_revision_after']
    receipt['version_stable']=stable
    receipt_path=run/'receipt.json'
    payload=(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode()
    receipt_path.write_bytes(payload)
    status=parsed['status'] if parsed else ('failed' if code not in (0,None) else 'not_run')
    appended=False
    error=''
    if stable:
        replacement=json.loads(raw)
        if parsed:
            counts=parsed['counts']
            summary=f"{fmt} 解析：总计 {counts['total']}，通过 {counts['passed']}，失败 {counts['failed']}，错误 {counts['errors']}，跳过 {counts['skipped']}；状态 {parsed['status']}。"
        else:
            summary='未能解析测试结果：'+receipt.get('parse_error','缺少可解析结果')+'。'
        replacement.setdefault('evidence',[]).append(dict(id=run_id,status=status,behavior_ids=receipt['behavior_ids'],revision=receipt['fingerprint_before'],summary=summary+DISCLAIMER,source=str(receipt_path),command=json.dumps(argv,ensure_ascii=False),actor='本地 verify 执行器（非人工核验）',executed_at=receipt['finished_at'],environment=f'cwd={project}; platform={platform.system()} {platform.release()}',verification_receipt=dict(path=str(receipt_path.relative_to(folder)),sha256=sha(payload))))
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.json',delete=False) as temp:
            json.dump(replacement,temp,ensure_ascii=False)
            source=Path(temp.name)
        try:
            api.update_task(folder,source,project,receipt['task_revision_before'],receipt['fingerprint_before'])
            appended=True
        except (OSError,ValueError) as exc:
            error=str(exc)
        finally:
            source.unlink(missing_ok=True)
    else:
        error='运行期间代码、验收约定或任务记录变化；只保留回执，未更新任务'
    return dict(receipt=str(receipt_path),parsed_result=parsed,version_stable=stable,evidence_appended=appended,error=error,disclaimer=DISCLAIMER), 0 if stable and appended and status=='passed' else 1

def inspect_receipt(task_dir, task, evidence):
    ref=evidence.get('verification_receipt')
    if 'verification_receipt' not in evidence:
        return dict(verification_source='claim')
    try:
        folder=Path(task_dir).resolve()
        if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not isinstance(ref['path'],str) or not isinstance(ref['sha256'],str):
            raise ValueError('回执引用无效')
        path=(folder/ref['path']).resolve()
        if not path.is_relative_to(folder/'runs'):
            raise ValueError('回执不在任务 runs 内')
        raw=read_limited(path)
        if sha(raw)!=ref['sha256']:
            raise ValueError('回执哈希不符')
        receipt=json.loads(raw)
        if not isinstance(receipt,dict):
            raise ValueError('回执必须为 JSON 对象')
        if not isinstance(receipt.get('logs'),dict) or receipt.get('version_stable') is not True or type(receipt.get('exit_code')) is not int or type(receipt.get('timed_out')) is not bool or not isinstance(receipt.get('execution_error'),str):
            raise ValueError('回执执行字段类型无效')
        if not isinstance(receipt.get('argv'),list) or not receipt['argv'] or any(not isinstance(arg,str) for arg in receipt['argv']) or receipt.get('cwd')!=task.get('project_path'):
            raise ValueError('回执 argv/cwd 无效')
        for field in ('fingerprint_before','fingerprint_after','task_revision_before','task_revision_after'):
            if not isinstance(receipt.get(field),str) or not re.fullmatch(r'[0-9a-f]{64}',receipt[field]):
                raise ValueError('回执版本字段无效')
        for field in ('started_at','finished_at'):
            if not isinstance(receipt.get(field),str):
                raise ValueError('回执时间字段无效')
            datetime.fromisoformat(receipt[field])
        if receipt.get('version')!=1 or receipt.get('task_id')!=task['id'] or receipt.get('task_dir')!=str(folder) or receipt.get('project_path')!=task.get('project_path') or receipt.get('run_id')!=evidence['id'] or receipt.get('behavior_ids')!=evidence.get('behavior_ids'):
            raise ValueError('回执任务或行为身份不符')
        if not receipt.get('version_stable') or not receipt.get('fingerprint_before') or receipt['fingerprint_before']!=receipt.get('fingerprint_after') or receipt['fingerprint_before']!=evidence.get('revision') or receipt.get('task_revision_before')!=receipt.get('task_revision_after'):
            raise ValueError('回执版本不稳定')
        logs={}
        for name in ('stdout','stderr'):
            item=receipt['logs'][name]
            if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not isinstance(item.get('sha256'),str):
                raise ValueError('日志引用类型无效')
            target=path.parent/item['path']
            if target.resolve().parent!=path.parent or target.is_symlink():
                raise ValueError('日志路径无效')
            logs[name]=read_limited(target)
            if sha(logs[name])!=item['sha256']:
                raise ValueError('原始日志哈希不符')
        if receipt.get('timed_out') or receipt.get('execution_error'):
            raise ValueError('运行未正常结束')
        if receipt['format']=='junit':
            item=receipt['result_file']
            if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not isinstance(item.get('sha256'),str):
                raise ValueError('结果引用类型无效')
            target=path.parent/item['path']
            if target.resolve().parent!=path.parent or target.is_symlink():
                raise ValueError('结果路径无效')
            result=read_limited(target)
            if sha(result)!=item['sha256']:
                raise ValueError('结果文件哈希不符')
        else:
            result=logs['stdout']+b'\n'+logs['stderr']
        parsed=parse_result(receipt['format'],result,receipt['exit_code'])
        if parsed!=receipt.get('parsed_result') or parsed['status']!=evidence.get('status'):
            raise ValueError('解析结果与回执/证据声明不符')
        return dict(verification_source='parsed_result',parsed_result=parsed)
    except (OSError,ValueError,KeyError,TypeError,ET.ParseError) as exc:
        return dict(verification_source='invalid',verification_error=str(exc))
