# astrbot_plugin_humanlike · 去 AI 味

让机器人说话不像 AI。三层手段，各自独立开关，可以只用一层，也可以叠加。

```
main.py                   插件主逻辑：两个钩子 + 调试指令 + 规则文件加载
deai_rules.py             纯文本规则（不依赖 astrbot，可单独运行/测试）
_conf_schema.json         WebUI 配置表单（23 项）
always_on.md              每轮注入的常驻规则（从 SEPIA 规则提取的群聊版）
skills/                   SEPIA 技能包，逐字节原文，6 个 Skill
NOTICE.md                 SEPIA 来源、版本、commit 与 MIT 许可
selftest.py               脱离 AstrBot 直接看清洗效果
```

## 安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/ezio271828/astrbot_plugin_humanlike
# 或者直接把整个目录复制进去
```

启动 AstrBot → WebUI「插件」页找到 **去 AI 味** → 需要配置就去插件配置页改。
改代码后点插件卡片上的刷新图标热重载，不用重启。

要求 AstrBot >= 4.5.7（`metadata.yaml` 里可放宽）。

## 和 SEPIA 融合

`skills/` 里放的是 [SEPIA](https://github.com/Nanako0129/sepia) v0.12.4 的技能包，
**逐字节原样、未做任何修改**（`diff -r skills <上游>/skills` 可校验）。
所以这里有两个消费方，分工不同：

| 消费方 | 读什么 | 什么时候生效 |
|---|---|---|
| AstrBot 的 Agent | `skills/sepia/SKILL.md` 及其 `references/` | 用户明确要求「评估这段文字像不像 AI」「把这篇改成人话」时 |
| 插件钩子 | `always_on.md`（699 字） | 每一条回复 |

为什么不直接把 `skills/sepia/SKILL.md` 当常驻提示词：它是给 Agent 的**路由手册**
（write/review/refactor/recreate + 按文本类型加载不同 references），整篇 72 行还带一堆
给 Agent 的操作约定，塞进每轮请求既浪费 token 又会让模型去「选操作」而不是正常聊天。
所以常驻层是 `always_on.md` —— 按 SEPIA 的实测结论重写的群聊短回复版，出处写在它的
frontmatter 里，注入前会被剥离。

### ⚠️ SEPIA 要真能读完，必须开「电脑能力」

AstrBot 的 Skill 只有名称和 `description` 会先给模型，完整说明和 `references/` 要靠文件读取。
所以在 `配置 → AI → 能力 → 使用电脑能力` 里选「本机环境」或「沙箱环境」，并在
`人格设定 → 人格能力` 里勾选要用的技能。选「无」时模型只看得到一句话简介，读了也读不全。

> 也就是说：**插件层保证每条回复都去 AI 味，SEPIA 层负责你明确要求时的高质量改写。**
> 两层都开才有完整效果；只开插件层也能用，只是拿不到 SEPIA 的完整判据。

### SEPIA 纠正了本插件上一版的三处问题

融合不是把文案拼一起，读它的 `style-pass.md` / `zh.md` 之后，我改了自己的规则：

| 上一版做法 | SEPIA 的依据 | 现在的做法 |
|---|---|---|
| 无条件把 `——` 换成逗号 | `style-pass.md §7`：em dash 频次是**版本属性**不是模型无关特征（GPT-4.1 每千词 10.62，Llama 3.x 0.00，人类均值 3.23）；`zh.md §1b`：两格「──」是台湾教育部手册的规定形式，人类新闻 61% 的文章出现过 | 默认**不动**，`strip_dash` 默认 false，要替换得自己开 |
| 清洗规则对全文无差别生效 | `SKILL.md` Hard guardrails：引用材料是承重的；`zh.md §0`：代码、命令、URL、文件名、版本号一律不动 | 新增**受保护片段**：引号内原话、行内代码、URL、`file:line`、版本号先换占位符再放回。这原本是个真 bug——旧版会把引用里的原话一起改掉 |
| 只做了「首先/其次/因此」这类换词 | `zh.md §2`：双音节凑数（「进行讨论」「加以说明」「予以处理」「做出决定」）是实测形状，该压回动词 | 新增凑数规则；`首先/其次/再次`这类枚举脚手架直接删掉而不是换词 |

还有三条**没能用正则做**、只写进 `always_on.md` 的，因为它们是判断而不是模式匹配：

- **语气词**：中文人话里「啊/吧/呢/嘛/喔/啦/呀」的出现率约为模型的 5 倍（`zh.md §1`）。加语气词要贴语境，正则加不出来。
- **连词**：模型连词密度是人类 3 倍（`zh.md §1`），但 SEPIA 的修法是**删**（中文靠意合）而不是换。删「但是」「不过」会改意思，这属于判断，交给模型。
- **句子节奏**：连续三句差不多长才是机器节奏（`style-pass.md §5`），单句长短不是信号。规则层只能拆条，判断不了节奏。

### 换成别的 skill / 别的规则

- 常驻规则：改 `always_on.md` 即可，或配置 `always_on_file` 指到你的文件（frontmatter 会被剥离）
- 想直接读某个 Skill 全文：`style_source=skill` + `skill_name=<目录名>`，并注意 `skill_max_chars`
- 升级 SEPIA：把上游 `skills/` 覆盖进来即可，不用改代码

## 工作原理

### 第 1 层：提示词层（最重要，效果占七成以上）

`@filter.on_llm_request` 在模型生成之前，把一套「聊天风格」硬规则塞进请求。
默认写进 `system_prompt`（风格规则是固定文本，不会破坏提示词缓存，遵守度也更高）；
也可以在配置里切成 `extra`，改用 `req.extra_user_content_parts` 追加。

想改成自己的风格，直接把内置 `DEFAULT_PROMPT`（见 `deai_rules.py`）改掉，
或者填在配置的「自定义风格提示词」里。**这一层比后面两层加起来都重要。**

### 第 2 层：后处理层

`@filter.on_decorating_result` 在回复发出前对纯文本做规则清洗：

- 砍开头套话：`当然可以！` `好的，我来帮你分析一下这个问题。` `作为一个AI语言模型，……`
- 砍结尾套话：`希望对你有所帮助` `如有疑问随时提问` `祝你顺利`
- 去 Markdown：`#` 标题、`**加粗**`、列表符号、代码反引号、分隔线、链接语法
- 破折号 `——` → 逗号（破折号是 AI 写作最典型的标点）
- 书面词换口语：首先/其次/因此/此外/综上所述 → 然后/所以/另外/反正；非常→挺；由于→因为；是否→是不是
- 被删剩的孤立转折词（“反正”）会被收尾清掉
- 可选：删 emoji、按配置做自定义替换（`原词=>新词`）
- 可选：长回复按句号拆成最多 N 条短消息，条间加随机延迟，像人连发几条

规则全部在 `deai_rules.py` 顶部，想加就直接往元组里加一条 `(正则, 替换, flags)`。

### 第 3 层：重写层（可选，默认关）

把清洗后的回复再交给当前会话的模型改写一遍，然后二次清洗。
效果最好，代价是**每条回复多一次 LLM 请求**，延迟和费用都明显上升。对延迟敏感的场景别开。

## 指令

| 指令 | 作用 |
|---|---|
| `/deai status` | 看当前开关状态 |
| `/deai on` / `/deai off` | 临时开关（只影响进程，不改配置文件） |
| `/deai test 一段文本` | 当场预览清洗效果，调规则时最好用 |
| `/deai reload` | 重新读取 SKILL.md，改完 skill 不用重启实例 |

## 推荐调试流程

1. 先只开提示词层，把人设/风格提示词调顺，大部分问题在这一步就没了
2. 再开后处理层，用 `/deai test` 拿真实输出试，发现被改坏就关掉对应那条规则
3. 只有前两层都不够，才考虑开重写层

调规则时把配置里的「日志记录 AI 味判断」打开，日志里会打印每条回复的
`AI味=True/False` 和清洗前后字数。

## 别过度去 AI 味

几个反例，值得先想清楚再动手：

- 把所有标点都删、所有句子都截断 —— 变成另一个刻板印象，人不是这么说话的
- 强行加“哈哈哈”“www”“草” —— 人格不匹配时比 AI 味更假
- emoji 全删 —— 很多人聊天反而爱用 emoji
- 把技术内容也口语化到失准 —— 该讲清楚的地方要讲清楚

目标是“像个正常人聊天”，不是“像个小混混聊天”。

## 自测

```bash
cd data/plugins/astrbot_plugin_humanlike
python3 selftest.py     # 看规则清洗前后的对比 + SKILL.md 常驻段抽取，不需要装 AstrBot
```

## 已知局限

- 规则层是“治标”的：它能砍掉 AI 的**腔调**，改不了内容的空泛。内容质量靠提示词和人设。
- 对多段 Markdown 文章类输出，规则清洗只能拼成一段；要真正像人写，得靠重写层或提示词层让它别列表。
- 拆条只对纯文本回复生效；图片、语音等富媒体消息不拆。
- 二次重写用的是当前会话的模型，如果模型本身很“AI 味”，重写也会一样。

## ⚠️ 流式输出会让后处理层失效

AstrBot 在流式回复时**仍然会调用** `on_decorating_result`，但此时文本已经边生成边发出去了，
钩子里的修改不会影响用户看到的内容。这不是本插件的 bug，是框架行为
（`astrbot/core/pipeline/result_decorate/stage.py` 里流式分支直接 `return`，框架自己也会打一行 warning）。

所以：

| 平台设置 | 提示词层 | 后处理层（清洗/拆条） |
|---|---|---|
| 关闭流式输出 | 生效 | **生效** |
| 开启流式输出 | 生效 | **不生效** |

v1.2.1 起插件会检测这种情况，跳过清洗并打印一次告警，而不是「假装清洗成功」。
想要后处理生效，就在 `配置 → 服务提供商 / 平台` 里关掉流式输出；
如果就是要流式，那就把风格完全交给 `always_on.md` —— 实战里提示词层的收益本来就占七成。

## 验证状态

### 已在真实实例上跑通（AstrBot 4.29.1）

| 项目 | 结果 |
|---|---|
| 安装 | 通过 WebUI 上传接口安装成功，`activated=true`，不在「加载失败插件」列表 |
| 注册内容 | `command: deai` 1 个 + `hook: inject_style / humanize_result` 2 个 + `skill` 6 个 |
| 技能登记 | 6 个 SEPIA 技能全部以 `astrbot_plugin_humanlike` 为来源出现，路径解析到 `data/plugins/.../skills/<名>/SKILL.md` |
| 配置表单 | 23 项 schema 正常读取，可通过 API 读写并触发热重载 |
| 规则文件 | 日志确认 `always_on.md（699 字）` 被读取 |
| 提示词层 | 实测有效：模型 reasoning 里明确引用 always_on.md 的规则并据此克制分点 |
| 后处理层 | 非流式生效；流式下按框架行为不生效，v1.2.1 已改为检测+告警 |
| 实机效果 | 「什么是死锁」→ 59 字一句话 + 类比，无 `**`、无「希望对你有所帮助」、无「首先」 |

### 代码层面对照源码核对过

| 检查项 | 结论 |
|---|---|
| `from astrbot.api.event import filter, AstrMessageEvent` | ✓ `filter` 是子模块，不在 `__all__` 里但可正常导入 |
| `Comp.Plain` 与 `comp.text = ...` | ✓ `Plain` 是普通 pydantic `BaseModel`，字段 `text` 可写 |
| `await event.send(event.plain_result(...))` | ✓ `MessageEventResult` 继承 `MessageChain` |
| `req.system_prompt` / `extra_user_content_parts` | ✓ 字段存在 |
| `get_current_chat_provider_id(umo=)` / `llm_generate(...)` | ✓ 签名一致 |
| `@filter.command_group` + `@group.command` | ✓ 通过实例绑定传成 `sub_command`，实机已注册 |

### 仍需你确认

1. 真实 QQ / TG 等群聊通道下的效果（本次是用 WebUI 的 webchat 通道验证的）
2. 关掉流式输出后，后处理层的实际观感是否比流式时更好
3. `metadata.yaml` 里的 `author` / `repo` 还是占位符，发布前要改成你自己的
