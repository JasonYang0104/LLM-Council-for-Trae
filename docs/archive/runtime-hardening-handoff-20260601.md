# Runtime Hardening Handoff

这份交接文档服务于一个新的会话。默认读者很聪明，理解能力强，但对这条线已经失忆，因此这里不重复堆砌历史聊天，而是把当前局面、为什么会提出这一轮迭代、应该从哪些文档开始恢复上下文、以及下一步应该以什么姿态推进，说到够用为止。

当前代码库已经不是“从零做一个 LCT”。`LLM-Council-for-Trae` 作为本地 council CLI 已经成立：`README.md` 能解释它是什么，`src/llm_council_for_trae/` 已经实现 Stage 1 / 2 / 3、artifact store、validate 和 HTML export，`.trae/agents/` 与 `profiles/subagents.json` 也已经对齐到 6 成员 + Kimi-K2.6 主席。用户在另一个 workspace clone GitHub 后，已经能够通过根目录能力直接触发 LCT 运行；这条“能启动、能跑起来”的主链路，基本已经打通。

这轮迭代之所以被提出来，不是因为入口不清楚，而是因为一次真实的效果测试把运行期问题暴露了出来。外部证据不在当前 repo，而在测试 workspace：

`/Users/bytedance/Documents/AI Coder/test/LLM-Council-for-Trae/.trae/postmortem/2026-06-01-lct-run-failure.md`

那份复盘的价值不在“某一次 run 失败了”，而在于它证明当前问题已经从“功能缺失”转成“运行期鲁棒性不足”。并发 run 会相互抢模型资源；Stage 2 缺少超时保护；`chairman_timeout` 暴露给用户却没有真正接入控制流；中断退出后的子进程清理和降级收场也不够稳。这些都不是 README 能修复的事，而是 runtime 本身需要进入下一阶段治理的信号。

恢复上下文时，不建议直接从源码开看。最稳的阅读顺序如下：

1. `README.md`
2. `docs/runtime-hardening-director-brief-20260601.md`
3. `docs/runtime-hardening-handoff-20260601.md`
4. `docs/design.md`
5. `docs/traecli-installation-and-paths.md`
6. `docs/traecli-subagents.md`
7. `docs/llm-council-parity.md`
8. 上面的外部 postmortem 路径

如果你只想先建立“这条线为什么存在”的心智模型，前 3 份文档就够了；如果你要开始实现，再补读 design、installation、subagents 和 postmortem。

当前工作分支是：

`plan/runtime-hardening-scheme-20260601`

这个分支现在承载的是“方案收敛”，不是 runtime 代码实现。已经完成的事情是：问题归因被重新梳理过一轮；并发控制策略不再停留在“加个锁”的粗线条层面，而是被拆成了 `run lease + global slot lease + model lease` 的三层思路；排期也不再是补丁式的 bug list，而是 `P0 防自爆 -> P1 说真话 -> P2 可收场 -> P3 数据化优化` 的运行时治理主线。

下一会话适合采用长线程推进。你不需要把自己当成一个只会执行 checklist 的脚本，更适合把自己当成一个带着背景判断力的实现负责人：先对齐目标，再设计约束，再把测试和实现一起压实。推进方式应该是和 `subagent-lead` 一起工作，并以 `tdd` 为主线。文档应该先沉淀到位，尤其是设计方案和测试方案；代码实现是后一步的事。实现责任并不是“尽快把功能写出来”，而是“让测试都通过，并且让 runtime 的行为说真话”。

实现过程中，`notes.md` 不该被当成废纸篓，也不该被当成流水账。它更像一个运行中的判断记录：那些规范里没提前写明、但你在实现时不得不做出的决定，那些你不得不更改的内容，那些你不得不接受的权衡，以及任何产品负责人应该知道的事实，都应该持续记进去。这样下一次会话不是只接手代码，而是能接手你的判断轨迹。

这轮实现不需要回头重新发明 LCT，也不应该把 scope 漫出去。当前合理的目标是把 runtime 从“能跑”提升到“可靠、可解释、可恢复”。更具体地说，P0 处理并发互斥、Stage 2 超时和进程清理，先防止系统自爆；P1 清理 timeout 真值源、错误分类和状态机，让系统说真话；P2 再做 Stage 3 降级和更体面的失败收场；P3 才轮到重试退避、数据画像、回归套件等优化项。

这条线的边界同样重要。不要重引 Web UI，不要接 OpenRouter，不要把 HTML export 和 chairman synthesis 混成一步，不要把 fake runtime 结果说成 live traecli 结果，也不要在 `traecli` 已知 pipe hang 的环境约束下假装可以轻易摆脱 `os.system + 临时文件重定向` 的现实。当前要解决的是 runtime 治理，而不是改写项目定位。

完成整轮实现之后，交付不应只是一批通过的测试和一串 commit。还应额外生成一份面向 PM director 的简报，保留 md/html 两种形态。那份简报不需要写成长篇文档，它应该帮助一个很聪明、但已经忘了前因后果的人，在几分钟内重新理解：当前 LCT 处在什么阶段、为什么会提出 runtime hardening、这轮到底解决了什么、还有什么没有解决。

推荐技能：

- `subagent-lead`
- `tdd`
- `verification-before-completion`
- `handoff`

如果新的会话需要一句足够自然的起步描述，可以这样理解这条任务：这不是再做一遍 LCT，而是在现有 LCT 已经可用的前提下，把运行期从容易误用、容易卡住、容易误判，推进到更稳、更可信、更方便后续 Agent 接手的状态。
