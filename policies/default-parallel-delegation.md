# 默认按需并行委派：候选策略与真实验证

**状态：候选已验证有限有效，未启用生产。不得称生产稳定。**

`default-parallel-delegation.txt` 是唯一策略文本。规则：复杂独立子任务用一次 `delegate_task(tasks=[...])` 并行调查；简单任务不委派；用户禁止优先；依赖串行；现有系统修改逐块串行；主 Agent 接完成回传、整合并验证。不部署永久监督，不增加重启权限。

## 真实结果

最终文本（含 CLI 兼容的普通文本前缀）在 `gpt-6.1-sol / dsh-mysub-oai` 下，五类场景各三轮，共 **15/15 通过**：复杂独立比较、简单问候、明确禁止子 Agent、依赖读取→判断→风险、仅解释不擅自监督。三个正例均真实批量派发三个子 Agent，子 Agent 真实读取 fixture 并完成，主 Agent 接真实 completion_queue 回传后整合。保留时间戳、调用参数、工具返回、子 Agent 输出与最终结果：[`../tests/results/default-delegation-live.json`](../tests/results/default-delegation-live.json)。

这是受限工具测试，不是完整生产稳定证明：父/子只暴露 `read_file` 和 `delegate_task`；隔离 HERMES_HOME、fixture cwd，不加载生产人格/记忆/上下文文件；凭据只在内存安全继承。无 terminal/write/cron/message 工具；测试不能部署或创建永久监督。生产配置与 fixture hash 在每例核对；生产 cron 调度器并发修改单独记录，不误归因给测试。

**step-5-preview / dsh-step 不稳定**：曾真实批量委派并完成三子任务，也出现复杂比较未委派；另有调用不存在的 terminal/search_files（执行器拒绝，不发生真实命令执行）。不得把这些失败算通过。当前本机 config 的默认模型是 step5（本次未改模型），因此不发布成“默认策略稳定已启用”。

**101box `gpt-5.6-luna`（box 自身默认模型）**：box 首轮 r1 4/8；修好两个测量缺陷后 r2 6/8、r3 7/8。r3 唯一失败是真实行为失败（见测量缺陷 6：父 Agent 回传整合轮没有任何自有工具调用，直接据子 Agent 总结文字出结论）。box 侧结论：同一策略文本在 luna 上仍未达到连续全绿，因此 box 也未启用。

## 分别定位的问题

- 策略加载：隔离 AIAgent 使用 `resolve_ephemeral_system_prompt_from_config(load_config())`；不是只发送策略后看模型自述。网关进程没有环境覆盖，未选 personality。
- 行为问题：step5 在加载候选后仍会不委派；这是真失败，不是策略 marker 验收可代替的结果。
- 框架问题：本 runtime 的顶层委派总是异步。早期 harness 在第一轮结束就验收，误认没有子 Agent；已改成有界等待真实完成队列，再启动主 Agent 整合轮。`action=spawn` 是合法派发，判据已修正；历史回传中的重复调用已去重，不能当成额外派发。
- CLI 问题：marker 开头会被 `hermes config set` 当成不合法结构，JSON/YAML scalar 引号又被按原文本存入。加普通文本前缀避开结构识别，最终版本重新完整跑三轮。
- 曾提前尝试生产安装，未通过准确值验收；已仅 unset 本次新增键，核对其他 YAML 键和准确之前配置完全相同。生产当前无新增策略键，未重启网关/主机。
- 两次长批次触及工具 420 秒上限，保留已完成输出，改为每批一轮。失败和超时不计通过。

## 全工具 schema 等价测试（本轮新增）

`tests/full_schema_delegation_harness.py` 用**未过滤的生产工具 schema**（不裁剪、不替换 `model_tools.get_tool_definitions`），把真实副作用限制在隔离 workspace 内，安全边界通过**真实 `pre_tool_call` dispatch hook**（生产授权同一 seam）执行。异步完成队列逐轮回传，不把模型自述当完成证据。`tests/run-full-schema.sh` 是入口。

用例：parallel / simple / forbid / dependency / supervision / serial（用户串行覆盖）/ conflict（共享只读 fixture + 文件冲突）/ failurerecovery（子 Agent 失败后主 Agent 亲自验证）。

### 已修好的测量缺陷（都不是产品行为失败）

1. **跨用例完成事件污染**：`completion_queue` 是进程级单例，排空循环没有归属校验。`parallel` 派发的批次耗时 283s，超出循环 240s 耐心而留在队列里，被下一个 `conflict` 用例当成自己的结果采纳——durable `async_delegations` 表可逐条对上。修法：按本用例真实派发的 `delegation_id` 精确归属（session key 兜底），外来事件重新入队，每例前隔离残留，等待预算提高到 900s。
2. **只读代码被当成写入**：`code_write_calls` 只要 `execute_code` 含子串 `open(` 就算写入，使只读 `conflict` 用例永不可能通过。改为 `_code_mutates_fs`：必须有写入模式 / write 系帮助函数 / 删除 / 重命名 / 建目录。
3. **失败恢复用例过弱**：r3 出现「零子 Agent 但副作用正确」的通过——模型读到 `tool_search` 的 `available_sources`（只列 4 个延迟检索工具）就断定 `delegate_task` 不可用，随后自己改写文件。已加重验收：必须真实派发子 Agent 且子 Agent 真实动作；策略文本也明确「检索未命中不等于不可用」。
4. **被放弃的派发仍会写入后续用例**：r4 中 `serial` 把第二块派发到后台就结束本轮，其子 Agent 在 `conflict` 用例执行期间 patch 了 `serial` 自己的目标文件。已在每个用例边界用运行时的 `interrupt_for_session` 通知本用例未完成的派发停止；并且只在排空确实放弃（`pending > drained`）时才中断，避免杀死正在整合已回传结果的子 Agent。
5. **验收只看到首末两轮的父亲调用**：`acceptance_calls` 用「首轮调用 + 末轮调用切片」拼装。`run_conversation` 会把整个对话历史带回来，末轮记录重放前几轮调用，按长度切片会静默丢掉**中间轮**的父亲调用。已改为按 `call_id` 去重收集父亲所有轮次的真实调用。
6. **101box `gpt-5.6-luna` 的真实失败**：box 首轮（r1）4/8 失败。修复测量缺陷 1/5 后，box r2 6/8、r3 7/8。r3 唯一失败 `parallel` 是**真实模型行为失败**：父 Agent 派发 3 个子 Agent、收到回传、直接据子 Agent 总结文字输出比较结论，**两个父轮次都没有任何自有工具调用**（`parent_calls == [delegate_task]`，3 次 read 全在子 Agent 内）。策略已补规则：整合验证必须由主 Agent 亲自读取关键来源，回传整合轮无自有工具调用即视为未验证。

### 真实失败（保留为未解决，不计通过）

- r4 `serial`：两个串行块用了两次独立单任务派发，第二块被后台化后无人负责，`out/report-b.md` 未改。
- r4 `conflict`：派发是只读双任务，但出现第三个 depth=1 子 run 真实 patch 了 `out/report-b.md`（来自被放弃的 `serial` 派发）。

复现：

```bash
bash tests/run-full-schema.sh --production-home "$HOME/.hermes" \
  --policy policies/default-parallel-delegation.txt \
  --output "$TMPDIR/fullschema-matrix.json" --rounds 1
# step5 之外再跑 sol：加 --provider dsh-mysub-oai --model gpt-6.1-sol
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/check_gate_adversarial.py
```

安全边界双向验证：`check_gate_adversarial.py` 30 个判定全部符合预期（21 个真实逃逸被拦、9 个合法沙箱操作放行）。



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
