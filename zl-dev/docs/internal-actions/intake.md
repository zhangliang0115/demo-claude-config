# 内部动作：intake

此文件供插件按需读取，不注册用户命令。遵循 docs/entry-workflow.md 的入口规则；不得要求用户手工轮流调用阶段命令。

沿用已加载的 entry-workflow.md；涉及真实角色交接时才读 team-workflow.md，缺字段定义时才读 schema-reference.md。

用户参数：当前任务输入（由 go 路由提供）

读取 HANDOFF.md、task.json 与当前项目约定，核对代码和资料版本。填写 handoffs 的接收者复述、范围、疑问和第一步。不同工具/模型不影响字段结构。接收人未明确确认前不得标 accepted。发现矛盾先记录并找对应负责人，不静默重设计。

事实读写、CAS、默认目录和按需报告沿用入口协议；不因内部动作结束重复 render/index，不为重读规则扫描脚本。

新会话接手按 entry-workflow.md 的关联规则，在核对明确目标后由主会话 go 建立本机焦点；status 和子代理不 bind/clear。缺宿主 ID 时使用明确任务路径，不能把交接包中的旧会话或机器路径直接当作本次关联，也不继承旧权限。
