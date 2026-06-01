# Runtime Hardening Director Brief

## 一句话结论

`LLM-Council-for-Trae` 已经从“做出一个可运行的本地 council CLI”进入“把 runtime 打磨到可靠可用”的阶段。当前最值得做的不是继续加新功能，而是治理运行期：并发互斥、Stage 2 超时、timeout 真值源、优雅退出、降级收场，以及更可信的状态与错误语义。

## 为什么现在要做

入口问题基本已经解决。repo 的 clone-to-run 路径、README、skill、自举方式、subagent profile 和基础验证命令都已经成型，另一个 workspace 的效果测试也说明用户可以直接从根目录能力触发 LCT。真正暴露出来的短板，已经不是“不会用”，而是“运行时在复杂场景下不够稳”。

触发这轮迭代的直接背景，是一份外部测试 workspace 的复盘文档：

`/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae/.trae/postmortem/2026-06-01-lct-run-failure.md`

这份复盘说明的问题集中在运行期治理层：多个 run 并发争抢同一批模型资源；Stage 2 没有超时闭环；`chairman_timeout` 暴露给用户却未真正生效；中断后缺少优雅清理；Stage 3 失败后也缺少足够体面的降级结果。

## 当前阶段判断

当前最合理的产品节奏不是“继续往上堆功能”，而是分层治理 runtime：

- `P0 防自爆`
- `P1 说真话`
- `P2 可收场`
- `P3 数据化优化`

这个顺序的意思很简单：先避免系统自己把自己拖死，再让错误和状态可信，再让失败后还能体面交付，最后再考虑更精细的优化。

## 建议的策略主线

并发问题不建议用一个粗暴的大锁一把梭。更合适的方向是三层控制：

- `run lease`：标识某个 run 的生命周期
- `global slot lease`：限制同时活跃的 live 模型查询数
- `model lease`：限制同一模型在同一时刻只被一个 live query 占用

这意味着 LCT 不是简单地“禁止并发”，而是把真正稀缺的资源约束起来：允许不同模型之间保留并行度，但阻止多个 run 同时争抢同一个模型，把成功率打穿。

同时，Stage 2 需要从现在的“可能静默挂住”转成“有超时、有退出、有状态”的闭环；timeout 字段也要统一真值源，避免配置与实际行为不一致；退出时的子进程清理、失败后的降级输出和结构化状态，都应该被纳入一个连续的 runtime 合同，而不是靠零散 patch 拼出来。

## 推荐的推进方式

这条线不适合短平快地“修一个 bug 提一个 PR”。更稳的做法是用长线程推进，和 `subagent-lead` 一起工作，以 `tdd` 为主线。先把设计方案和测试方案沉淀清楚，再动手实现；实现职责以“测试最终都通过”为准，而不是以“先写出来再说”为准。

实现过程中持续维护 `notes.md`，记录那些规范里没包含、但实现中不得不做出的判断、改动和权衡。这样新会话接手时，看到的不只是代码 diff，而是能理解背后的设计判断。

## 索引文档

建议新接手的人按这个顺序恢复上下文：

1. `README.md`
2. `docs/runtime-hardening-handoff-20260601.md`
3. `docs/runtime-hardening-director-brief-20260601.md`
4. `docs/design.md`
5. `docs/traecli-installation-and-paths.md`
6. `docs/traecli-subagents.md`
7. `docs/llm-council-parity.md`

## 交付预期

这轮完成之后，理想交付不只是代码变更和一轮测试通过，还应包含一份面向 PM director 的 md/html 简报。它应该能让一个很聪明、但暂时失忆的读者，在极短时间里重新理解当前状况、这轮为什么值得做、已经解决了什么，以及下一轮应继续看哪里。
