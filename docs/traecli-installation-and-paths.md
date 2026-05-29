# Trae CLI 安装、登录与核心路径记录

本文记录本机 Trae CLI 的安装依据、实际安装过程、SSO 登录方式、核心文件路径和后续研究时最值得看的官方文档入口。读者默认是后续要研究 Trae CLI、做配套开发或排障的 Agent / 开发者。

## 当前结论

- 本文件记录 2026-05-22 安装与首次 smoke test 事实；不要把这里的历史成功直接当成当前可用性结论。
- 2026-05-22 阶段收尾时，用户确认 Trae CLI 当前暂不可用；CLC 本轮只复验了不依赖 live Trae CLI 的测试。
- Trae CLI 安装曾成功，版本为 `0.120.32`。
- `coco`、`traecli`、`trae-agent`、`ta` 是同一套内部二进制的不同入口。
- 本机曾通过字节 SSO 完成鉴权，插件曾下载成功，模型列表曾可用。
- 当前用户级配置文件是 `/Users/bytedance/.trae/traecli.yaml`。
- 安装 smoke test 时的有效模型为 `GPT-5.4`，并通过最小问答验证。

验证命令：

```bash
traecli --version
traecli doctor
traecli models --json
traecli -p "只回复 OK" --query-timeout 60s
```

2026-05-22 安装 smoke test 返回：

```text
OK
```

如果这些命令当前失败，先按本文“本次踩坑记录”排查鉴权、插件和模型列表；在 Trae CLI 恢复前，不要声称 `llm-council-for-trae` 完成了新的 live model run。

## 安装参考

安装命令来自 Trae CLI 官方 wiki 及相关内部文档。原始入口是：

```text
https://cloud.bytedance.net/docs/wikiagent/wiki/Er28whaTUiRgMekHLvDcISWmnXc?x-resource-account=public&x-bc-region-id=bytedance
```

本次实际用 Lark CLI 检索并参考了以下相关文档：

- `Coco CLI + OpenSpec 快速起步（菜鸡入门版）`
- `Coco 使用速记指南`
- `如何在DCarClaw上安装使用coco`
- Trae CLI 内置文档：`traecli doc`
- Trae CLI 内置 FAQ：`traecli doc faq`
- Trae CLI 内置配置参考：`traecli doc settings`
- Trae CLI 内置权限参考：`traecli doc permissions`
- Trae CLI 内置模型配置参考：`traecli doc model-config`

说明：原始 cloud wiki URL 在 Lark CLI 下没有直接读取权限；因此实际安装依据是通过 Lark CLI 搜索到的关联文档，以及安装后 Trae CLI 自带的 `traecli doc` 文档体系交叉确认。

## 安装过程

安装命令：

```bash
sh -c "$(curl -L https://code.byted.org/api/tos-proxy/download/adopt_coco.sh)" \
  && export PATH=~/.local/bin:$PATH
```

安装脚本做的核心事情：

- 下载内部版 Trae CLI 二进制。
- 放置真实二进制到 `~/.local/share/coco/coco`。
- 在 `~/.local/bin` 下创建多个入口 symlink。
- 确保 `~/.local/bin` 在 shell PATH 中可用。

本机安装后的版本信息：

```text
coco version 0.120.32
build date: 2026-05-18T10:01:36Z
build commit: 1066fe26cab49cbcea6cf9d4c257cda74e6437bb
commit date: 2026-05-18T08:55:40Z
```

## 登录与 SSO 过程

安装完成后，最初 `traecli doctor` 报错：

```text
model: no effective model configured
```

同时插件下载出现 401，模型列表为空：

```text
download failed with HTTP 401
traecli models --json => []
```

根因不是二进制没装上，而是鉴权没有完成，导致内置插件 tar 拉不下来。插件没有拉下来时，模型定义也不会出现。

尝试过 Git 登录路径：

```text
Login via Git (Recommended)
```

但当前环境没有可用 Kerberos / Git 凭据，表现为：

```text
Cannot access ByteDance git credentials in the current environment.
```

随后改走字节 SSO：

1. 执行 `coco` 进入交互界面。
2. 在认证选择里选 `Login via SSO`。
3. Trae CLI 展示设备授权链接，形式类似：

```text
https://sso.bytedance.com/device?usercode=XXXX-XXXX
```

4. 用浏览器打开链接，完成字节员工 SSO 授权。
5. 授权完成后，Trae CLI 回到主界面。
6. 重新执行插件和模型验证。

SSO 成功后的关键验证：

```bash
traecli plugin validate v2/api/2022-06-01/coco-plugin
traecli plugin validate v2/api/2022-06-01/coco-instance-plugin
traecli models --json
```

其中 `coco-instance-plugin` 提供了 23 个模型和 2 个 skills。

## 核心文件路径

### 二进制入口

| 路径 | 作用 |
|---|---|
| `/Users/bytedance/.local/bin/coco` | 主要 CLI 入口，symlink |
| `/Users/bytedance/.local/bin/traecli` | 同一二进制的 TraeCLI 入口，symlink |
| `/Users/bytedance/.local/bin/trae-agent` | 同一二进制入口，symlink |
| `/Users/bytedance/.local/bin/ta` | 同一二进制入口，symlink |
| `/Users/bytedance/.local/share/coco/coco` | 真实核心二进制 |

当前 symlink 指向关系：

```text
/Users/bytedance/.local/bin/coco -> /Users/bytedance/.local/share/coco/coco
/Users/bytedance/.local/bin/traecli -> /Users/bytedance/.local/share/coco/coco
```

### 用户级配置

| 路径 | 作用 |
|---|---|
| `/Users/bytedance/.trae/traecli.yaml` | 用户级主配置文件 |
| `/Users/bytedance/.trae/skills/` | 用户级 skills，若后续创建或安装会出现在这里 |
| `/Users/bytedance/.trae/commands/` | 用户级 prompt commands，若后续创建或安装会出现在这里 |
| `/Users/bytedance/.trae/agents/` | 用户级 subagents，若后续创建或安装会出现在这里 |

当前用户级配置内容：

```yaml
model:
    name: GPT-5.4
```

注意：安装过程中曾先写入 `GPT-5.2`，这是参考文档里对后端场景的推荐；后续使用 `/model` 切换后，当前有效配置变成了 `GPT-5.4`。

### 项目级配置

Trae CLI / TraeCLI 会从当前目录向上查找项目级配置。主路径是：

```text
<project>/.trae/traecli.yaml
```

兼容只读路径包括：

```text
<project>/.coco/coco.yaml
<project>/.agents/coco.yaml
```

项目级配置优先级高于用户级配置。后续如果研究某个具体 repo 的 Trae CLI 行为，必须先检查该 repo 下有没有这些文件。

### 缓存、插件和日志

| 路径 | 作用 |
|---|---|
| `/Users/bytedance/Library/Caches/coco/` | Trae CLI 缓存根目录 |
| `/Users/bytedance/Library/Caches/coco/plugins/` | 插件实际展开目录 |
| `/Users/bytedance/Library/Caches/coco/log/root.log` | 主日志文件，排查鉴权、插件下载、模型问题最有用 |
| `/Users/bytedance/Library/Caches/coco/sessions/` | 本机会话缓存 |
| `/Users/bytedance/Library/Caches/coco/ripgrep/rg` | Trae CLI 自带 ripgrep |

当前已下载插件：

```text
/Users/bytedance/Library/Caches/coco/plugins/v2-api-2022-06-01-coco-plugin
/Users/bytedance/Library/Caches/coco/plugins/v2-api-2022-06-01-coco-instance-plugin
```

`coco-instance-plugin` 是关键插件之一，当前提供：

- 23 个模型
- 2 个 skills：`findbugs`、`simplify`

## 常用命令

基础检查：

```bash
traecli --version
traecli doctor
traecli models --json
traecli plugin list
```

查看内置文档：

```bash
traecli doc
traecli doc faq
traecli doc settings
traecli doc permissions
traecli doc model-config
traecli doc search model
```

启动交互模式：

```bash
coco
```

非交互问答：

```bash
traecli -p "只回复 OK" --query-timeout 60s
```

YOLO / Accept All 模式：

```bash
traecli -y
traecli --yolo
```

在交互界面里可用 `shift+tab` 循环切换：

```text
Default -> Accept All -> Plan -> Default
```

## 重要官方文档入口

### 外部 / wiki 入口

Trae CLI 官方 wiki：

```text
https://cloud.bytedance.net/docs/wikiagent/wiki/Er28whaTUiRgMekHLvDcISWmnXc?x-resource-account=public&x-bc-region-id=bytedance
```

Trae CLI WebUI 本地环境文档在 WebUI 报错页里出现过：

```text
https://bytedance.larkoffice.com/docx/ZECMd2kAQoglGrxzsJ0cDbMrnSb
```

说明：上述 WebUI 修复文档当前 Lark CLI 账号没有读取权限，后续需要用有权限的账号或在浏览器里打开查看。

### 本机内置文档

安装后最稳定的官方文档入口是本机命令：

```bash
traecli doc
```

重点 topic：

| topic | 作用 |
|---|---|
| `quickstart` | 安装、首次问答、首次代码修改 |
| `faq` | 安装、认证、模型 401、keyring、上下文超限等排障 |
| `settings` | 配置文件位置、优先级、字段语法 |
| `permissions` | Default / Accept All / Plan、allowed_tools、disallowed_tools |
| `model-config` | 模型 provider、自定义模型、failover |
| `plugins` | 插件安装、市场、插件提供的 skills / commands / models |
| `mcp` | MCP server 配置和接入 |
| `skills` | skills 机制和项目级扩展 |
| `commands` | slash commands 列表 |
| `cloud-web` | WebUI / Cloud 相关入口 |
| `doctor` | 环境体检说明 |

示例：

```bash
traecli doc faq
traecli doc settings
traecli doc permissions
traecli doc plugins
```

## 本次踩坑记录

### 1. 原始 wiki 不等于当前账号可读

原始 URL 可以在浏览器里打开，但 Lark CLI 直接读取时遇到权限问题。解决方式是用 Lark CLI 搜索相关文档，再结合 `traecli doc` 内置文档确认安装和排障步骤。

### 2. 模型列表为空通常不是模型配置小问题

本次 `traecli models --json` 一开始返回 `[]`，`traecli web` 也因为模型列表为空崩溃。根因是插件 tar 下载 401，模型定义没有加载进来。

判断命令：

```bash
traecli plugin validate v2/api/2022-06-01/coco-instance-plugin
```

如果提示插件文件未下载，就先解决鉴权，不要只改 `model.name`。

### 3. Git 登录依赖 Kerberos / Git 凭据

`Login via Git` 是推荐路径，但本机最初没有 Kerberos 票据，Git 访问 `code.byted.org` 也拿不到用户名，因此失败。可用命令检查：

```bash
klist
git ls-remote https://code.byted.org/<some/repo>
```

如果 Git 路径不通，可以改走 Trae CLI 交互界面里的 `Login via SSO`。

### 4. SSO 成功后要复查插件和模型

不要只看 traecli 进入主界面。真正的完成标准是：

```bash
traecli plugin validate v2/api/2022-06-01/coco-instance-plugin
traecli models --json
traecli doctor
traecli -p "只回复 OK" --query-timeout 60s
```

本次这四步都已跑通。

### 5. `traecli doctor` 的 MCP warning 可先区别看待

当前 `doctor` 仍可能出现：

```text
mcp: 3 MCP server(s) still connecting (0 ok)
```

这不是安装失败；本次 `doctor` summary 是：

```text
7 ok / 1 warn / 0 error
```

并且真实模型问答已返回 `OK`。

## 后续研究建议

优先从这几条线展开：

1. 配置体系：先读 `traecli doc settings`，搞清用户级、项目级、插件配置和合并优先级。
2. 插件体系：读 `traecli doc plugins`，重点看插件如何提供 models、skills、commands、MCP servers。
3. 权限体系：读 `traecli doc permissions`，研究 `permission_mode`、`allowed_tools`、`disallowed_tools`。
4. 模型体系：读 `traecli doc model-config`，理解内置模型、自定义 provider 和 failover。
5. 项目扩展：读 `traecli doc agents-md`、`traecli doc skills`、`traecli doc prompt-commands`。
6. Web / Cloud：读 `traecli doc cloud-web`，再结合有权限的 WebUI 文档补全。
