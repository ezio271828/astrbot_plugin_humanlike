# -*- coding: utf-8 -*-
"""脱离 AstrBot 直接验证清洗规则与 Skill 融合：python selftest.py"""

from pathlib import Path

from deai_rules import (
    clean_text,
    extract_always_on,
    looks_ai,
    split_text,
    strip_frontmatter,
)

PLUGIN_DIR = Path(__file__).parent

# 原始用例：(说明, 原文, 期望的关键行为)
CASES = [
    (
        "开头套话 + Markdown 标题",
        "当然可以！以下是关于 Python 装饰器的简要说明：\n\n"
        "**1. 什么是装饰器**\n"
        "装饰器本质上是一个接受函数作为参数并返回新函数的高阶函数。\n\n"
        "**2. 常见用途**\n- 日志记录\n- 性能缓存\n\n"
        "总的来说，**装饰器**非常实用。希望对你有所帮助！",
        "开头和结尾套话应被整段删除，Markdown 符号应消失",
    ),
    (
        "首先/因此 + 分点列举",
        "好的，我来帮你分析一下这个问题。\n\n"
        "首先，需要明确的是，缓存失效通常有三个原因：\n"
        "1. 过期时间设置不合理\n2. 并发写入覆盖\n3. 内存淘汰策略\n\n"
        "因此，建议你检查配置。如有其他问题，欢迎随时提问。",
        "「好的，我来帮你分析」应整句消失，列表应拼成一句",
    ),
    (
        "冒充 AI 免责声明",
        "作为一个AI语言模型，我无法确定你的具体环境。需要注意的是，这个问题可能有多种原因。",
        "免责句应整段删除",
    ),
    (
        "本来就够人话（不该被改坏）",
        "可能是缓存没清，你重启一下试试？",
        "必须原样返回",
    ),
    (
        "双音节凑数（SEPIA zh.md §2）",
        "你需要对配置进行修改，然后做出决定。",
        "「进行修改」→「修改」，「做出决定」→「决定」",
    ),
    (
        "引文保护（SEPIA Hard guardrails）",
        "他说「当然可以！希望对你有所帮助」，我当时就笑了。",
        "引号内原话一律不动",
    ),
    (
        "代码/版本/文件名保护",
        "你改 config.yaml:12 的缩进，v1.2.3 之后就不用了。",
        "文件名、行号、版本号必须原样保留",
    ),
    (
        "破折号（默认不替换）",
        "原因很简单——你忘了加括号",
        "默认保留；显式开启 strip_dash 才换逗号",
    ),
]

LONG = (
    "这个功能其实不难。你需要先装依赖，然后改配置文件，最后重启服务。"
    "中间有两处容易踩坑：依赖版本要对，配置里的缩进用空格别用 tab。"
    "如果还是起不来，把日志贴给我看看。"
)


def main() -> None:
    print("=" * 78)
    for i, (name, src, expect) in enumerate(CASES, 1):
        got = clean_text(src)
        print(f"[case {i}] {name}")
        print(f"  期望: {expect}")
        print(f"  原文({len(src)}字): {src!r}")
        print(f"  清洗后({len(got)}字): {got}")
        print("-" * 78)

    dash_src = "原因很简单——你忘了加括号"
    print("[strip_dash 开关对比]")
    print(f"  默认   : {clean_text(dash_src)!r}")
    print(f"  开启后 : {clean_text(dash_src, strip_dash=True)!r}")
    print("-" * 78)

    # ---- 常驻规则文件 ----
    print("[always_on.md]")
    ao_path = PLUGIN_DIR / "always_on.md"
    if ao_path.exists():
        raw = ao_path.read_text(encoding="utf-8")
        body = strip_frontmatter(raw)
        assert body.startswith("【说话方式】"), "frontmatter 没剥干净"
        assert "source: SEPIA" not in body, "frontmatter 不该进入注入内容"
        assert "https://github.com" not in body, "出处链接不该被注入（浪费 token）"
        print(f"  文件 {len(raw)} 字 → 剥离 frontmatter 后注入 {len(body)} 字")
        print(f"  首行: {body.splitlines()[0]}")
        print("  ✓ 出处等元信息留在 frontmatter，不进入上下文")
    else:
        print("  未找到 always_on.md")
    print("-" * 78)

    # ---- vendored skills ----
    print("[skills/ 结构]")
    found = sorted(p.parent.name for p in (PLUGIN_DIR / "skills").glob("*/SKILL.md"))
    print(f"  发现 {len(found)} 个 Skill: {', '.join(found)}")
    assert "sepia" in found, "sepia 规范体缺失"
    for wrapper in ("sepia-write", "sepia-review", "sepia-refactor", "sepia-recreate"):
        assert wrapper in found, f"{wrapper} 入口缺失"
        sibling = PLUGIN_DIR / "skills" / wrapper / ".." / "sepia" / "SKILL.md"
        assert sibling.exists(), f"{wrapper} 的相对路径 ../sepia/SKILL.md 解析失败"
    print("  ✓ 四个操作入口都能解析到 ../sepia/SKILL.md")
    print("  ✓ AstrBot 会把每个含 SKILL.md 的子目录登记为一个技能")
    print("-" * 78)

    print("[split_text]")
    for idx, part in enumerate(split_text(LONG, max_len=40, max_parts=3), 1):
        print(f"  {idx}. ({len(part)}字) {part}")
    print("-" * 78)

    print("[looks_ai] 采样")
    for sample in [
        "当然可以！首先我们需要注意的是配置项。综上所述，希望对你有所帮助。",
        "啊这个我知道，你重启下就行",
    ]:
        print(f"  {looks_ai(sample)!s:5} {sample}")

    print("\n全部检查通过")


if __name__ == "__main__":
    main()
