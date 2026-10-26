# 报告复用与模板时效评测 · 2026-10-26

## 范围与实现

ZL-10 覆盖 task report.html 与 feature feature.html。同事实、业务评估、展示版本及实际页面时复用已有文件；时间不作为更新理由。HTML provenance.template_revision 单独保存展示依赖，不写入 task/feature，不加入子任务业务评估，不改绑证据。

实际 HTML/CSS/JS 以捕获的同份字节计算哈希并渲染；依赖清单按报告种类区分。渲染变换用 per-kind protocol 标明，维护者改拼接/替换逻辑时须升级；不把整个 Python 源文件或安装绝对目录当作模板身份。旧页无模板版本时 unknown，素材变化时 stale，状态查询不写文件。

仅有内嵌模板号不足以证明页面未改：当前页面必须与其记录、实际素材重建出的规范字节一致。比较只容许生成时间不同，业务日期不被忽略。发布保留事实锁、HTML CAS、原子替换及最后核对；复用也在返回前重新检查事实、模板及 HTML。

## 审查与失败处理

独立探针发现 P2：模板可能在复用的规范比对期间变化，导致旧实现仍返回成功。修复为两处复用返回前都再次核对 source/template 和 actual HTML。独立复现确认会明确拒绝、旧 HTML 保留；CSS 变化不改变业务 assessment，业务日期保留。

第一次全量运行 321 项有一项旧测试失败：feature 替换失败测试在无变化 render 时期待 os.replace 被调用，幂等后会正确短路。将该测试先产生真实 title 变化，再保留 PermissionError、旧字节和临时文件清理断言。原发布竞态测试同样改为明确需要写入的状态；读取 hook 从 read_text 调整为真实 asset read_bytes，没有删除原保护断言。

## 真实 Claude Code 与控制器分工

控制器建立私有插件副本、隔离 Git 仓库、analysis 报告及一份单独开发子任务关联的 feature 总览。总览仍未完成开发/接受，评测仅针对报告行为。没有启动业务、执行项目测试、查询数据库或请求业务接口。未修改工作区源插件和已安装插件的素材。

先由真实 Python CLI 分别连续 render task 与 feature，核对字节哈希、mtime 和生成时间保持。真实 Claude Code 使用用户已有模型配置，通过 --plugin-dir 加载私有副本，流式原始记录保留 Read/Bash 调用，未覆盖模型。allowedTools 不是硬沙箱，行为以轨迹和独立文件核对为依据。

第一轮请求现有当前报告：Claude 返回 success，原始 num_turns=5、permission_denials 为空。实际 locate 后复用原路径，没有调用 render，控制器确认报告字节和 mtime 不变。仍额外列目录和读任务；最终答复把任务类型误称为 report_reuse，实际记录为 analysis。此措辞错误不当作身份依据，以 CLI 与记录校验为准。

随后控制器仅在私有副本共享 CSS 追加测试注释。task/feature 状态均变 template stale，二者业务 assessment_revision 保持。第二轮 resume 同一真实 Claude 会话，请求仅更新展示：success，原始 num_turns=5、无 permission_denials；实际 locate → render → locate，未调用 update/verify。Claude 更新的是 task 报告；feature 重生由控制器单独完成，不混称模型操作。

控制器独立核对：两份报告重新 current、模板字节已更新；业务源码、task.json、feature.json 精确字节未变，业务评估未变；再次 CLI render 两类报告均保持新文件字节与 mtime。业务验证未运行，也没有新增运行成功或接受结论。

## 局限

代码不可核对时仍 unknown，不因模板一致变成可信当前报告。空 feature 保持原有仅记录时效语义，不据此认为开发就绪。模板变化不自动产生新的人工核验、接受或发布授权；HANDOFF 模板版本管理不在本轮范围。

检查只针对当时可观察版本，不能锁住外部编辑器、子仓库或未来修改。旧版客户端不认识展示版本，应重载插件；不承诺长进程热替换或版本身份认证。本轮没有测算 token 节省，文件复用次数不能换算模型成本。

## 最终回归

321 项全量回归通过（71.241s），包含新增 17 项复用/模板检查；原 provenance 17 项与 publish 16 项定向回归通过。安装版另跑新增定向项并比对完整文件。manifest 校验与可安装性不等于官方目录认证；既有 LICENSE/icon 目录提示未由本轮改变。
