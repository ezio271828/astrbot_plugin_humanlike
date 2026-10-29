# -*- coding: utf-8 -*-
"""“去 AI 味”的文本规则与清洗函数。

这个模块刻意**不 import astrbot**，所以可以脱离 AstrBot 直接跑：

    python selftest.py

分成三块：
1. DEFAULT_PROMPT   —— 注入给大模型的“说话风格”硬规则（效果最大的一环）
2. clean_text()     —— 对已经生成好的回复做规则清洗（去套话 / 去 Markdown / 书面词换口语）
3. split_text()     —— 把一大段拆成几条短消息，模拟人“连发几条”的习惯
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# 1. 注入给模型的风格提示词
# --------------------------------------------------------------------------- #

DEFAULT_PROMPT = """【回复风格】
你现在是在手机上和对方聊天，不是写文章。严格遵守：
1. 一次只说 1~3 句，通常不超过 60 字；对方明确要求详细说明时才展开。
2. 开门见山给结论，不要“当然可以”“好的”“以下是”“我来帮你分析一下”这类开场。
3. 不要写结尾套话，例如“希望对你有所帮助”“如有疑问随时问我”“祝你顺利”。
4. 不分点、不列清单、不加小标题，不用 Markdown（* # - ` 这些符号都不要）。
5. 少用书面连接词：不要“首先/其次/因此/此外/综上所述/需要注意的是”，改用“然后/所以/还有/反正/不过”。
6. 允许口语：可以用“啊、吧、嘛、诶、哈、挺、有点、说实话”，偶尔反问一句。
7. 不要复述对方的问题，不要总结自己刚说过的话。
8. 不确定就直说“不确定”或“我记不清了”，不要编。
9. 不要每句都工整完整，可以把一句话拆成两三个短句。"""


# --------------------------------------------------------------------------- #
# 2. 规则表
# --------------------------------------------------------------------------- #
# 每条规则是 (正则, 替换内容, flags)。替换内容为 "" 表示删除。

#: 开头的 AI 套话。注意这类规则要“吃整句”，否则会留下“这个问题。”这种残句。
OPENING_RULES: tuple[tuple[str, str, int], ...] = (
    (r"^当然(?:可以|没问题|好啦|好啊|好呀|好的)?[\!！。，,\s:：]*", "", 0),
    (r"^好的(?:呢|呀|啊)?[\!！。，,\s:：]*", "", 0),
    (r"^没问题[\!！。，,\s:：]*", "", 0),
    (r"^OK(?:的)?[\!！。，,\s:：]*", "", 0),
    (r"^作为(?:一个|一名|一位)?(?:AI|人工智能|语言模型|智能助手|助手)[^。！？\n]*[。！？\n]?", "", 0),
    (r"^首先[，,]\s*", "", 0),
    (r"^让我(?:们)?[^。！？\n]*[。！？\n]", "", 0),
    (r"^以下是[^。！？\n]{0,20}[：:]\s*", "", 0),
    (r"^我(?:来|先)?(?:帮你|为您|给你)(?:分析|梳理|总结|解释|介绍|看看|看)(?:一下)?[^。！？\n]*[。！？\n]?", "", 0),
    (r"^这(?:个)?问题(?:其实)?(?:很|比较)?(?:简单|好回答|值得一说|不难)[，,：:]\s*", "", 0),
    (r"^嗯[，,]\s*", "", 0),
)

#: 结尾的 AI 套话
CLOSING_RULES: tuple[tuple[str, str, int], ...] = (
    (r"[，,、]?\s*希望(?:这|以上|这些|我的回答|这些信息)?(?:能|会)?(?:对你|对您)?(?:有所)?帮助[。！？!~～\s]*$", "", 0),
    (r"[，,、]?\s*(?:希望|但愿)(?:这|以上)[^。！？]{0,10}(?:有用|帮到你)[。！？!~～\s]*$", "", 0),
    (r"[，,、]?\s*如(?:有|果有)(?:任何)?[^。！？]{0,12}(?:问题|疑问|需要|不明白)[^。！？]{0,14}[。！？!~～\s]*$", "", 0),
    (r"[，,、]?\s*(?:欢迎|随时)(?:继续)?(?:随时)?(?:追问|提问|交流|联系我|告诉我|找我)[^。！？]{0,10}[。！？!~～\s]*$", "", 0),
    (r"[，,、]?\s*祝(?:你|您)?[^。！？]{0,8}(?:顺利|愉快|开心|有收获)[。！？!~～\s]*$", "", 0),
    (r"[，,、]?\s*(?:总之|总的来说)[，,]?[^。！？]{0,20}(?:就好|即可|就行)[。！？!~～\s]*$", "", 0),
    (r"[，,、]?\s*(?:还|如果)(?:有|需要)[^。！？]{0,10}(?:随时|尽管|可以)[^。！？]{0,10}[。！？!~～\s]*$", "", 0),
)

#: 套话被删掉后可能留下一个孤零零的转折词（例如“……，综上所述，” → “反正”），收尾清掉
DANGLING_MARKER_RULES: tuple[tuple[str, str, int], ...] = (
    (
        r"[，,、]?\s*(?:反正|另外|所以|但是|不过|然后|就是|就是说|同时|而且|因此|此外)\s*$",
        "",
        0,
    ),
)

#: 书面腔换口语。注意逗号：有的换完要补逗号，有的不要。
WORD_RULES: tuple[tuple[str, str, int], ...] = (
    (r"需要注意的是[，,]?", "另外，", 0),
    (r"值得注意的是[，,]?", "另外，", 0),
    (r"需要指出的是[，,]?", "另外，", 0),
    (r"需要说明的是[，,]?", "另外，", 0),
    (r"需要明确的是[，,]?", "另外，", 0),
    (r"综上所述[，,]?", "反正", 0),
    (r"总的来说[，,]?", "反正", 0),
    (r"总而言之[，,]?", "反正", 0),
    (r"换言之[，,]?", "就是说", 0),
    (r"也就是说[，,]?", "就是", 0),
    (r"与此同时[，,]?", "同时", 0),
    (r"因此[，,]?", "所以", 0),
    (r"此外[，,]?", "另外，", 0),
    (r"然而[，,]?", "但", 0),
    (r"首先[，,]?\s*", "", 0),
    (r"其次[，,]?\s*", "", 0),
    (r"再者[，,]?\s*", "", 0),
    (r"并且", "而且", 0),
    (r"以及", "和", 0),
    (r"使用", "用", 0),
    (r"由于", "因为", 0),
    (r"是否", "是不是", 0),
    (r"如何", "怎么", 0),
    (r"即可", "就行", 0),
    (r"非常", "挺", 0),
    (r"十分", "挺", 0),
    (r"极其", "超", 0),
    (r"目前", "现在", 0),
    (r"较为", "比较", 0),
)

#: 双音节凑数：把「进行讨论/加以说明/予以处理/做出决定」压回动词本身。
#: 依据 SEPIA `references/languages/zh.md` §2「Disyllabic padding where a monosyllable is idiomatic」，
#: 来源为 朱君輝 et al. CCL 2023 在 HC3-Chinese 上的实测（单音节词占比 人 0.483 vs 机器 0.379）。
#: 负向前瞻排除「进行中 / 进行时 / 进行了」这类合法用法。
PADDING_RULES: tuple[tuple[str, str, int], ...] = (
    (
        r"(?:进行|加以|予以|做出|作出)(?!(?:中|时|了|过|的|到))(?=[\u4e00-\u9fa5]{2})",
        "",
        0,
    ),
)

#: Markdown 清洗（聊天窗口里不该出现这些东西）
MARKDOWN_RULES: tuple[tuple[str, str, int], ...] = (
    (r"^[ \t]{0,3}#{1,6}[ \t]+.*$", "", re.MULTILINE),        # 整行标题直接删
    (r"^\s*\*\*[^*\n]{1,40}\*\*\s*$", "", re.MULTILINE),      # 整行加粗 = 伪标题，删
    (r"^\s*__[^_\n]{1,40}__\s*$", "", re.MULTILINE),
    (r"\*\*(.+?)\*\*", r"\1", 0),                             # 行内粗体
    (r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)", r"\1", 0),  # 斜体
    (r"__([^_\n]+?)__", r"\1", 0),
    (r"`{1,3}([^`\n]+)`{1,3}", r"\1", 0),                     # 行内代码 / 围栏
    (r"^[ \t]{0,3}[-*+][ \t]+", "", re.MULTILINE),            # 无序列表符号
    (r"^[ \t]{0,3}\d+[.)、][ \t]+", "", re.MULTILINE),        # 有序列表符号
    (r"^[ \t]{0,3}>\s?", "", re.MULTILINE),                   # 引用
    (r"^[ \t]{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$", "", re.MULTILINE),  # 分隔线
    (r"\[([^\]]+)\]\([^)]+\)", r"\1", 0),                     # 链接保留文字
)

#: 破折号规则：**默认关闭**，别当模型无关的特征用。
#: 依据 SEPIA `references/style-pass.md` §7 白名单：em dash 频次是「发布版本属性」而不是
#: 模型无关的 AI 特征（实测每千词 GPT-4.1 10.62 / Claude Opus 4.6 9.09 / GPT-5.4 1.43 /
#: Llama 3.x 0.00，人类均值 3.23）。`references/languages/zh.md` §1b 进一步指出，两格
#: 「──」是台湾教育部标点手册的规定形式，人类新闻里 61% 的文章都出现过。
#: 所以无条件把破折号换成逗号属于「过度矫正」，本身是另一种机器痕迹。
DASH_RULES: tuple[tuple[str, str, int], ...] = (
    (r"\s*—{2,}\s*", "，", 0),
    (r"\s*—\s*", "，", 0),
    (r"\s*--\s*", "，", 0),
)

#: emoji（可选删除）
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\uFE0F"
    "\u200D"
    "]+"
)

#: 空格与标点收尾
SPACE_RULES: tuple[tuple[str, str, int], ...] = (
    (r"[ \t]+([，。！？；：、）】」』!?])", r"\1", 0),
    (r"([（【「『])[ \t]+", r"\1", 0),
    (r"[，,]\s*\n", "\n", 0),
    (r"[ \t]{2,}", " ", 0),
    (r"\n{3,}", "\n\n", 0),
)

#: 受保护片段：引文、代码、URL、版本号、文件名一律原样返回，不做任何清洗。
#: 依据 SEPIA `SKILL.md`「Hard guardrails」——引用材料是承重的（load-bearing），
#: `references/languages/zh.md` §0 也明确「code spans, commands and flags, Markdown syntax,
#: URLs, file names and version strings are never touched」。
#: 上一版没有这层保护，清洗规则会把引号里的原话、代码和版本号一起改掉，这是真 bug。
PROTECT_RE = re.compile(
    r"("
    r"「[^」\n]{0,300}」|『[^』\n]{0,300}』|“[^”\n]{0,300}”|‘[^’\n]{0,300}’"
    r"|\"[^\"\n]{1,200}\""
    r"|`[^`\n]{1,200}`"
    r"|https?://[^\s，。！？；：、）】」』]+"
    r"|[\w./-]+\.(?:py|js|ts|json|ya?ml|toml|ini|md|txt|log|sh|cfg|conf)(?::\d+)?"
    r"|\bv?\d+\.\d+(?:\.\d+)*\b"
    r")"
)

_PLACEHOLDER = "\x00{}\x00"


def _protect(text: str) -> tuple[str, list[str]]:
    """把不该改的片段换成占位符，清洗完再换回来。"""
    kept: list[str] = []

    def _sub(match: re.Match) -> str:
        kept.append(match.group(0))
        return _PLACEHOLDER.format(len(kept) - 1)

    return PROTECT_RE.sub(_sub, text), kept


def _restore(text: str, kept: list[str]) -> str:
    for i, piece in enumerate(kept):
        text = text.replace(_PLACEHOLDER.format(i), piece)
    return text


_LEADING_JUNK_RE = re.compile(r"^[\s，,。、：:；;!！?？~～]+")
_TRAILING_JUNK_RE = re.compile(r"[\s，,、：:；;~～]+$")
_SENTENCE_RE = re.compile(r"[^。！？!?~～\n…]+[。！？!?~～…]*|\n+")
_HAS_TERMINAL_PUNCT = re.compile(r"[。！？!?~～…]$")
_HAS_SOFT_PUNCT = re.compile(r"[：:，,、]$")


# --------------------------------------------------------------------------- #
# 3. 清洗
# --------------------------------------------------------------------------- #


def _apply_rules(text: str, rules: tuple[tuple[str, str, int], ...]) -> str:
    for pattern, repl, flags in rules:
        text = re.sub(pattern, repl, text, flags=flags)
    return text


def _apply_until_stable(
    text: str, rules: tuple[tuple[str, str, int], ...], times: int = 3
) -> str:
    """反复应用，直到不再变化（删掉一层套话后可能露出下一层）。"""
    for _ in range(times):
        new = _apply_rules(text, rules)
        if new == text:
            break
        text = new
    return text


def _join_soft_lines(text: str) -> str:
    """把被删掉列表符号后剩下的碎行接成一句话，避免一条条占一行。

    段内（空行隔开）的连续短行会被“、”连起来；上一行已经以句号结尾则保留换行。
    """
    blocks = re.split(r"\n{2,}", text)
    merged_blocks: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        merged = lines[0]
        for line in lines[1:]:
            if _HAS_TERMINAL_PUNCT.search(merged):
                merged += "\n" + line
            elif _HAS_SOFT_PUNCT.search(merged):
                merged += line
            else:
                merged += "、" + line
        merged_blocks.append(merged)
    return "\n\n".join(merged_blocks)


def _parse_custom(custom_replace: list[str] | None) -> tuple[tuple[str, str, int], ...]:
    """把 ["进行=>做", "或许=>也许"] 解析成规则元组。"""
    rules: list[tuple[str, str, int]] = []
    for item in custom_replace or []:
        if not isinstance(item, str):
            continue
        for sep in ("=>", "->", "＝>", "→"):
            if sep in item:
                old, new = item.split(sep, 1)
                old, new = old.strip(), new.strip()
                if old:
                    rules.append((re.escape(old), new, 0))
                break
    return tuple(rules)


def clean_text(
    text: str,
    *,
    strip_openings: bool = True,
    strip_closings: bool = True,
    replace_words: bool = True,
    clean_markdown: bool = True,
    strip_emoji: bool = False,
    custom_replace: list[str] | None = None,
    strip_dash: bool = False,
    protect: bool = True,
) -> str:
    """对一段模型回复做“去 AI 味”清洗。

    顺序很重要：先清 Markdown（否则符号会卡住后面的匹配），
    再换词，再砍开头结尾的套话，最后统一空格标点。
    """
    if not text or not text.strip():
        return text

    original = text.strip()
    text = original.replace("\r\n", "\n").replace("\r", "\n").strip()

    # 先把引文/代码/URL/版本号换成占位符，避免被后面的规则误伤
    kept: list[str] = []
    if protect:
        text, kept = _protect(text)

    # 破折号默认不动：见 DASH_RULES 上方的依据。需要时在配置里显式打开。
    if strip_dash:
        text = _apply_rules(text, DASH_RULES)

    if clean_markdown:
        text = _apply_rules(text, MARKDOWN_RULES)
        text = _join_soft_lines(text)

    if replace_words:
        text = _apply_rules(text, PADDING_RULES)
        text = _apply_rules(text, WORD_RULES)

    custom = _parse_custom(custom_replace)
    if custom:
        text = _apply_rules(text, custom)

    if strip_openings:
        text = _apply_until_stable(text, OPENING_RULES)

    if strip_closings:
        text = _apply_until_stable(text, CLOSING_RULES)

    # 砍完套话后可能剩下“反正”这种孤立转折词，一并清掉
    text = _apply_until_stable(text, DANGLING_MARKER_RULES)

    if strip_emoji:
        text = EMOJI_RE.sub("", text)

    text = _apply_rules(text, SPACE_RULES)

    # 占位符放回原样（这一步必须在收尾去空白之前，否则占位符可能被误当空白处理）
    if kept:
        text = _restore(text, kept)

    text = _LEADING_JUNK_RE.sub("", text)
    text = _TRAILING_JUNK_RE.sub("", text)
    text = text.strip()

    # 全被删空了说明规则太激进，退回原文 —— 宁可不改，也别把消息弄没
    return text or original


def split_text(text: str, max_len: int = 60, max_parts: int = 3) -> list[str]:
    """把长回复拆成最多 max_parts 条短消息，尽量在句号处断开。"""
    text = (text or "").strip()
    if not text or max_parts <= 1 or len(text) <= max_len:
        return [text] if text else []

    sentences = [s for s in _SENTENCE_RE.findall(text) if s.strip()]
    if not sentences:
        return [text]

    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if buf and len(buf) + len(sentence) > max_len and len(chunks) < max_parts - 1:
            chunks.append(buf)
            buf = sentence
        else:
            buf += sentence
    if buf:
        chunks.append(buf)

    if len(chunks) > max_parts:
        chunks = chunks[: max_parts - 1] + ["".join(chunks[max_parts - 1 :])]

    out = [c.strip() for c in chunks if c.strip()]
    return out or [text]


def looks_ai(text: str) -> bool:
    """粗略判断一段文本是否“AI 味重”，可用于日志统计 / 自检。"""
    if not text:
        return False
    score = 0
    for pattern in (
        r"^\s*当然",
        r"^\s*好的[，,]",
        r"作为(?:一个)?(?:AI|人工智能)",
        r"\*\*",
        r"—",
        r"首先",
        r"综上所述",
        r"希望[^。]{0,6}帮助",
        r"^\s*#{1,6}\s",
        r"^\s*\d+[.)]\s",
    ):
        if re.search(pattern, text, re.MULTILINE):
            score += 1
    if len(text) > 150:
        score += 1
    return score >= 2


# --------------------------------------------------------------------------- #
# 4. Skill 文件解析
# --------------------------------------------------------------------------- #
# AstrBot 的 Skill 是给 Agent 按需加载的「任务手册」，格式为
#   <plugin>/skills/<skill_name>/SKILL.md
# 文件开头是 YAML frontmatter，正文是给模型看的说明。
#
# 这里做「融合」的关键：同一份 SKILL.md 里用一个标记段划出「每轮都要生效的常驻规则」，
# 插件只取这一段注入；没有标记就退化为整篇。这样 Skill 和插件共用一份事实来源，
# 不会出现「skill 改了、插件内置提示词还是旧的」这种漂移。

_FRONTMATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n?", re.DOTALL)
_ALWAYS_ON_RE = re.compile(
    r"<!--\s*always-on:begin\s*-->(.*?)<!--\s*always-on:end\s*-->",
    re.DOTALL | re.IGNORECASE,
)


def strip_frontmatter(text: str) -> str:
    """去掉 SKILL.md 开头的 YAML frontmatter。"""
    return _FRONTMATTER_RE.sub("", text or "", count=1).strip()


def extract_always_on(text: str, max_chars: int = 0) -> str:
    """取出 SKILL.md 中需要「每轮注入」的常驻规则段。

    - 有 `<!-- always-on:begin/end -->` 标记：只取标记之间
    - 没有标记：退化为整篇正文
    - max_chars > 0 时按段落边界截断，避免把一条规则切成半句
    """
    body = strip_frontmatter(text)
    match = _ALWAYS_ON_RE.search(body)
    out = (match.group(1) if match else body).strip()
    if max_chars and len(out) > max_chars:
        cut = out[:max_chars]
        for sep in ("\n\n", "\n", "。"):
            idx = cut.rfind(sep)
            if idx > max_chars * 0.6:
                cut = cut[: idx + len(sep)]
                break
        out = cut.rstrip() + "\n…（规则过长已截断）"
    return out
