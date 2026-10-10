# 默认按需并行委派：候选策略与真实验证

**状态：候选已验证有限有效，未启用生产。不得称生产稳定。**

`default-parallel-delegation.txt` 是唯一策略文本。规则：复杂独立子任务用一次 `delegate_task(tasks=[...])` 并行调查；简单任务不委派；用户禁止优先；依赖串行；现有系统修改逐块串行；主 Agent 接完成回传、整合并验证。不部署永久监督，不增加重启权限。

## 真实结果

最终文本（含 CLI 兼容的普通文本前缀）在 `gpt-6.1-sol / dsh-mysub-oai` 下，五类场景各三轮，共 **15/15 通过**：复杂独立比较、简单问候、明确禁止子 Agent、依赖读取→判断→风险、仅解释不擅自监督。三个正例均真实批量派发三个子 Agent，子 Agent 真实读取 fixture 并完成，主 Agent 接真实 completion_queue 回传后整合。保留时间戳、调用参数、工具返回、子 Agent 输出与最终结果：[`../tests/results/default-delegation-live.json`](../tests/results/default-delegation-live.json)。

这是受限工具测试，不是完整生产稳定证明：父/子只暴露 `read_file` 和 `delegate_task`；隔离 HERMES_HOME、fixture cwd，不加载生产人格/记忆/上下文文件；凭据只在内存安全继承。无 terminal/write/cron/message 工具；测试不能部署或创建永久监督。生产配置与 fixture hash 在每例核对；生产 cron 调度器并发修改单独记录，不误归因给测试。

**step-5-preview / dsh-step 不稳定**：曾真实批量委派并完成三子任务，也出现复杂比较未委派；另有调用不存在的 terminal/search_files（执行器拒绝，不发生真实命令执行）。不得把这些失败算通过。当前本机 config 的默认模型是 step5（本次未改模型），因此不发布成“默认策略稳定已启用”。

## 分别定位的问题

- 策略加载：隔离 AIAgent 使用 `resolve_ephemeral_system_prompt_from_config(load_config())`；不是只发送策略后看模型自述。网关进程没有环境覆盖，未选 personality。
- 行为问题：step5 在加载候选后仍会不委派；这是真失败，不是策略 marker 验收可代替的结果。
- 框架问题：本 runtime 的顶层委派总是异步。早期 harness 在第一轮结束就验收，误认没有子 Agent；已改成有界等待真实完成队列，再启动主 Agent 整合轮。`action=spawn` 是合法派发，判据已修正；历史回传中的重复调用已去重，不能当成额外派发。
- CLI 问题：marker 开头会被 `hermes config set` 当成不合法结构，JSON/YAML scalar 引号又被按原文本存入。加普通文本前缀避开结构识别，最终版本重新完整跑三轮。
- 曾提前尝试生产安装，未通过准确值验收；已仅 unset 本次新增键，核对其他 YAML 键和准确之前配置完全相同。生产当前无新增策略键，未重启网关/主机。
- 两次长批次触及工具 420 秒上限，保留已完成输出，改为每批一轮。失败和超时不计通过。

## 复现（在 Hermes runtime 目录）

```bash
PYTHONPATH=. venv/bin/python <REPO>/tests/run_live_delegation.py \
  --production-home "$HOME/.hermes" \
  --policy <REPO>/policies/default-parallel-delegation.txt \
  --output "$TMPDIR/delegation-evidence.json" --rounds 1
# 重复三批，避免一次批次超过外层工具时限。
# step5: 加 --provider dsh-step --model step-5-preview
python3 -m unittest discover -s <REPO>/tests -p test_delegation_evidence.py
```

`run_live_delegation.py` 仅修改自身临时测试配置。结果中不存在工具的调用作为失败保留。`scripts/apply-default-delegation.py` 是显式安装入口，不自动调用；它拒绝覆盖已有 system_prompt/personality，私密备份，仅用官方 CLI 写一个键，检查解析前后只该键变化及 resolver 精确匹配。**当前不建议默认 step5 用户运行安装脚本；完整生产工具集/平台新会话仍未完成验收。**

未来启用前必须进一步验证生产等价工具集的安全隔离执行，以及 step5 或用户指定模型的连续通过。不通过则维持未启用，不能改模型绕过。新 Agent 会话才可载入；不保证当前缓存会话变化，不主动向飞书发送消息或重启网关。

回滚仅 `hermes config unset agent.system_prompt`（仅当它仍是本策略且之前键不存在），不得恢复整份旧配置覆盖并发修改。任何其他覆盖层必须人工合并，不复制策略至 SOUL/AGENTS/memory。
