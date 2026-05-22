# 新会话启动 Goal

把下面整段发给新会话：

```text
/goal 在当前 workspace 中推进 COCO-llm-council。目标是创建一个独立 council CLI，命令名为 coco-llm-council，内部调用 traecli，一比一复刻 references/llm-council 的核心 council protocol，但排除原 Web UI 和 OpenRouter API。必须优先复用 llm-council 中不冲突的已有资产和函数边界；必须使用 Codex 的 cli-creator 方法论创建 CLI；COCO 是默认 runtime；后续支持 COCO 自定义 subagent 作为固定 council 成员。先阅读 README.md、docs/design.md、docs/COCO_INSTALLATION_AND_PATHS.md 和 references/llm-council/README.md，再给出实现计划。交付必须完整包含：CLI skeleton、doctor/models、Stage 1/2/3 council run、artifact store、expected vs actual model 校验、HTML export、验证命令和结果。开发可以分阶段推进，但每阶段必须有明确测试。不要依赖旧 TR，不要引入 Web app，不要把 HTML 生成和主席综合混成一步。
```
