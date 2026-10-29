# -*- coding: utf-8 -*-
"""astrbot_plugin_humanlike —— 让机器人说话不像 AI。

三层手段，全部可单独开关：
1. 提示词层（最有效）：把“聊天风格”硬规则注入 system_prompt / 额外用户内容块
2. 后处理层：回复发出前做规则清洗（去套话、去 Markdown、书面词换口语、拆长句）
3. 重写层（可选、有额外成本）：把回复再交给模型改写成口语，然后清洗
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

# 插件是以 data.plugins.<目录名>.main 的形式被 import 的，所以相对导入可用；
# 万一被别的加载方式导进来，退化成同目录导入，保证插件不会因为几行 import 起不来。
try:
    from .deai_rules import (
        DEFAULT_PROMPT,
        clean_text,
        extract_always_on,
        looks_ai,
        split_text,
        strip_frontmatter,
    )
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from deai_rules import (
        DEFAULT_PROMPT,
        clean_text,
        extract_always_on,
        looks_ai,
        split_text,
        strip_frontmatter,
    )

# TextPart 是较新版本才有的（用于往本轮请求追加额外内容块）；没有就降级改 system_prompt
try:  # pragma: no cover
    from astrbot.core.agent.message import TextPart
except Exception:  # pragma: no cover
    TextPart = None

# 用来识别流式回复：AstrBot 在流式时虽然会调用 on_decorating_result，
# 但此时文本已经边生成边发出去了，钩子里的修改不会影响用户看到的内容
# （见 astrbot/core/pipeline/result_decorate/stage.py：流式分支直接 return）。
try:  # pragma: no cover
    from astrbot.api.event import ResultContentType
except Exception:  # pragma: no cover
    ResultContentType = None


DEFAULT_REWRITE_PROMPT = """把下面这段话改写成真人随手打字的样子：
- 保持原意和关键信息，不要丢结论
- 更短：能砍的铺垫、修饰、总结都砍掉
- 口语化，像在微信/QQ 上随口说的
- 不要分点、不要 Markdown、不要开场白、不要结尾套话
只输出改写后的正文，不要任何解释。"""


class HumanlikePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 运行时开关：/deai off 只影响本次进程，不改配置文件
        self._enabled = bool(config.get("enabled", True))
        # 规则来源缓存，None 表示还没读过
        self._skill_text: str | None = None
        self._file_text: str | None = None
        self._streaming_warned = False
        logger.info(
            f"[humanlike] 已加载，总开关={'开' if self._enabled else '关'}，"
            f"注入={'开' if config.get('inject_prompt', True) else '关'}，"
            f"重写={'开' if config.get('rewrite_enabled', False) else '关'}"
        )

    # ------------------------------------------------------------------ #
    # 配置小工具
    # ------------------------------------------------------------------ #
    @property
    def style_prompt(self) -> str:
        """常驻风格规则的来源优先级：配置里手写的 > SKILL.md > 内置。

        和 Skill 融合的关键就在这里：同一份 SKILL.md 既给 Agent 按需加载，
        又被插件抽出来每轮注入，两边不会各写一份然后慢慢对不上。
        """
        custom = (self.config.get("extra_prompt") or "").strip()
        if custom:
            return custom
        source = self.config.get("style_source") or "file"
        if source == "file":
            text = self._load_style_file()
            if text:
                return text
        elif source == "skill":
            text = self._load_skill_style()
            if text:
                return text
        return DEFAULT_PROMPT

    def _style_file_path(self) -> Path:
        name = (self.config.get("always_on_file") or "always_on.md").strip() or "always_on.md"
        path = Path(name)
        return path if path.is_absolute() else Path(__file__).resolve().parent / path

    def _load_style_file(self, force: bool = False) -> str:
        """读取 always_on.md 作为常驻风格规则（frontmatter 会被剥离）。

        这份文件是按 SEPIA 的规则提取的群聊版，和 skills/sepia/ 的原文分工不同：
        原文给 Agent 按需读，这份每轮注入。改它不需要动代码。
        """
        if self._file_text is not None and not force:
            return self._file_text
        path = self._style_file_path()
        try:
            raw = path.read_text(encoding="utf-8")
            self._file_text = strip_frontmatter(raw)
            logger.info(
                f"[humanlike] 已加载常驻规则：{path.name}（{len(self._file_text)} 字）"
            )
        except FileNotFoundError:
            self._file_text = ""
            logger.warning(f"[humanlike] 找不到 {path}，回退内置提示词")
        except Exception as exc:
            self._file_text = ""
            logger.warning(f"[humanlike] 读取 {path} 失败：{exc}，回退内置提示词")
        return self._file_text

    # ------------------------------------------------------------------ #
    # Skill 融合
    # ------------------------------------------------------------------ #
    def _skill_path(self) -> Path:
        name = (self.config.get("skill_name") or "deai-writing").strip() or "deai-writing"
        return Path(__file__).resolve().parent / "skills" / name / "SKILL.md"

    def _load_skill_style(self, force: bool = False) -> str:
        """读取 skills/<name>/SKILL.md，取出常驻规则段。失败返回空串（由调用方回退）。"""
        if self._skill_text is not None and not force:
            return self._skill_text
        path = self._skill_path()
        try:
            raw = path.read_text(encoding="utf-8")
            max_chars = int(self.config.get("skill_max_chars", 1500) or 0)
            self._skill_text = extract_always_on(raw, max_chars)
            logger.info(
                f"[humanlike] 已加载 Skill 规则：{path.name} "
                f"（注入 {len(self._skill_text)} 字）"
            )
        except FileNotFoundError:
            self._skill_text = ""
            logger.warning(f"[humanlike] 找不到 {path}，回退内置提示词")
        except Exception as exc:
            self._skill_text = ""
            logger.warning(f"[humanlike] 读取 Skill 失败：{exc}，回退内置提示词")
        return self._skill_text

    def _clean_opts(self) -> dict:
        return {
            "strip_openings": bool(self.config.get("strip_openings", True)),
            "strip_closings": bool(self.config.get("strip_closings", True)),
            "replace_words": bool(self.config.get("replace_words", True)),
            "clean_markdown": bool(self.config.get("clean_markdown", True)),
            "strip_emoji": bool(self.config.get("strip_emoji", False)),
            "custom_replace": self.config.get("custom_replace") or [],
            "strip_dash": bool(self.config.get("strip_dash", False)),
            "protect": bool(self.config.get("protect_quotes", True)),
        }

    # ------------------------------------------------------------------ #
    # 第 1 层：请求前注入风格规则
    # ------------------------------------------------------------------ #
    @filter.on_llm_request()
    async def inject_style(self, event: AstrMessageEvent, req):
        """在模型生成之前就把“别像 AI”写进它的输入里。"""
        if not self._enabled or not self.config.get("inject_prompt", True):
            return
        style = self.style_prompt
        if not style:
            return

        position = self.config.get("prompt_position", "system")
        try:
            if position == "extra" and TextPart is not None:
                # 作为额外的用户内容块追加，不动 system_prompt（更适合每轮会变的内容）
                req.extra_user_content_parts.append(TextPart(text=style))
            else:
                # 风格规则是稳定内容，放在 system_prompt 里既不会破坏提示词缓存，
                # 又比塞在用户消息里更容易被模型遵守。
                req.system_prompt = f"{req.system_prompt or ''}\n\n{style}".strip()
        except Exception as exc:  # 任何版本差异都别把正常对话搞挂
            logger.warning(f"[humanlike] 注入风格提示词失败：{exc}")

    # ------------------------------------------------------------------ #
    # 第 2、3 层：回复发出前清洗 / 可选重写 / 可选拆条
    # ------------------------------------------------------------------ #
    @filter.on_decorating_result()
    async def humanize_result(self, event: AstrMessageEvent):
        if not self._enabled:
            return
        result = event.get_result()
        if result is None:
            return
        chain = getattr(result, "chain", None)
        if not chain:
            return

        # 流式回复：文本已经边生成边发出，改 chain 也不会影响用户看到的内容。
        # 与其「假装清洗成功」，不如明确跳过并提示 —— 提示词层在流式下依然有效。
        if (
            ResultContentType is not None
            and getattr(result, "result_content_type", None)
            == ResultContentType.STREAMING_FINISH
        ):
            if not self._streaming_warned:
                self._streaming_warned = True
                logger.warning(
                    "[humanlike] 检测到流式输出：AstrBot 在流式回复时不应用后处理结果，"
                    "本插件已跳过规则清洗（提示词层仍然生效）。"
                    "想让后处理生效请关闭流式输出；或保持现状，靠 always_on.md 约束风格。"
                )
            return

        plains = [
            c for c in chain if isinstance(c, Comp.Plain) and (getattr(c, "text", "") or "")
        ]
        if not plains:
            return

        try:
            # 3-1 可选：交给模型重写（会多一次请求，注意延迟和费用）
            if self.config.get("rewrite_enabled", False):
                rewritten = await self._rewrite(event, "\n".join(c.text for c in plains))
                if rewritten:
                    plains[0].text = rewritten
                    for extra in plains[1:]:
                        extra.text = ""

            # 3-2 规则清洗
            opts = self._clean_opts()
            for comp in plains:
                if comp.text:
                    before = comp.text
                    comp.text = clean_text(comp.text, **opts)
                    if self.config.get("log_ai_score", False):
                        logger.info(
                            f"[humanlike] AI味={looks_ai(before)} "
                            f"{len(before)}字 -> {len(comp.text)}字"
                        )

            # 3-3 可选：把一大段拆成几条短消息，模拟“连发几条”
            if self.config.get("split_replies", False) and len(plains) == 1:
                await self._maybe_split(event, plains[0])
        except Exception as exc:
            logger.warning(f"[humanlike] 回复后处理失败，已跳过：{exc}")

    async def _maybe_split(self, event: AstrMessageEvent, comp) -> None:
        max_len = int(self.config.get("split_max_len", 60) or 60)
        max_parts = int(self.config.get("split_max_parts", 3) or 3)
        delay = float(self.config.get("split_delay", 1.0) or 0)
        chunks = split_text(comp.text, max_len=max_len, max_parts=max_parts)
        if len(chunks) <= 1:
            return
        comp.text = chunks[0]
        for chunk in chunks[1:]:
            if delay > 0:
                # 加一点随机间隔，比连珠炮更像人在打字
                await asyncio.sleep(delay * random.uniform(0.6, 1.4))
            await event.send(event.plain_result(chunk))

    async def _rewrite(self, event: AstrMessageEvent, text: str) -> str:
        """用当前会话的模型再改一遍。失败就返回空串，由调用方回退到规则清洗。"""
        try:
            provider_id = await self.context.get_current_chat_provider_id(
                umo=event.unified_msg_origin
            )
            if not provider_id:
                return ""
            prompt = (self.config.get("rewrite_prompt") or "").strip() or DEFAULT_REWRITE_PROMPT
            resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=f"{prompt}\n\n原文：\n{text}",
            )
            out = (resp.completion_text or "").strip()
            return clean_text(out, **self._clean_opts()) if out else ""
        except Exception as exc:
            logger.warning(f"[humanlike] 二次重写失败，回退规则清洗：{exc}")
            return ""

    # ------------------------------------------------------------------ #
    # 调试指令
    # ------------------------------------------------------------------ #
    @filter.command_group("deai")
    def deai(self):
        """去 AI 味插件指令组"""

    @deai.command("status")
    async def deai_status(self, event: AstrMessageEvent):
        """查看当前开关状态"""
        state = "开" if self._enabled else "关"
        mode = self.config.get("style_source") or "file"
        if (self.config.get("extra_prompt") or "").strip():
            source = "配置里手写的 extra_prompt"
        elif mode == "file":
            source = (
                f"always_on 文件（{self._style_file_path().name}，"
                f"{len(self._load_style_file())} 字）"
            )
        elif mode == "skill":
            source = (
                f"SKILL.md（{self._skill_path().parent.name}，"
                f"{len(self._load_skill_style())} 字）"
            )
        else:
            source = "内置 DEFAULT_PROMPT"
        yield event.plain_result(
            f"去AI味：{state}｜注入提示词="
            f"{'开' if self.config.get('inject_prompt', True) else '关'}｜"
            f"重写={'开' if self.config.get('rewrite_enabled', False) else '关'}｜"
            f"拆条={'开' if self.config.get('split_replies', False) else '关'}\n"
            f"风格来源：{source}"
        )

    @deai.command("reload")
    async def deai_reload(self, event: AstrMessageEvent):
        """重新读取 SKILL.md（改完 skill 不用重启实例）"""
        mode = self.config.get("style_source") or "file"
        if mode == "file":
            text, path = self._load_style_file(force=True), self._style_file_path()
        else:
            text = self._load_skill_style(force=True)
            path = self._skill_path()
        if not text:
            yield event.plain_result(f"没读到 {path}，当前回退到内置提示词")
            return
        yield event.plain_result(
            f"已重新加载 {path.name}，注入 {len(text)} 字\n\n预览：\n{text[:300]}"
        )

    @deai.command("on")
    async def deai_on(self, event: AstrMessageEvent):
        """临时开启（不改配置文件）"""
        self._enabled = True
        yield event.plain_result("去AI味已开启")

    @deai.command("off")
    async def deai_off(self, event: AstrMessageEvent):
        """临时关闭（不改配置文件）"""
        self._enabled = False
        yield event.plain_result("去AI味已关闭")

    @deai.command("test")
    async def deai_test(self, event: AstrMessageEvent):
        """预览清洗效果：/deai test 一段想清洗的文本"""
        raw = event.message_str or ""
        for prefix in ("/deai test", "deai test", "/deai  test"):
            if raw.lower().startswith(prefix):
                raw = raw[len(prefix) :]
                break
        raw = raw.strip()
        if not raw:
            yield event.plain_result("用法：/deai test 这里放一段想清洗的文本")
            return
        yield event.plain_result(
            f"清洗后：\n{clean_text(raw, **self._clean_opts())}"
        )

    async def terminate(self):
        logger.info("[humanlike] 插件已卸载")
