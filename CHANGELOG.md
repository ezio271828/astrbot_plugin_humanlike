# 更新日志

## 1.2.2

- 添加插件 logo（`logo.png`，256×256）
- 补充从仓库安装的说明：HTTP API 的 `download_url` 需要归档 zip 地址，否则会报「插件压缩包格式错误」

## 1.2.1

- 修复：流式输出下 `on_decorating_result` 的修改不会生效（AstrBot 在流式分支直接返回）。
  现在检测到流式回复会跳过规则清洗并打印一次告警，不再出现「日志说清洗了、实际没生效」的误导。
- 版本号与日志中的跳过原因同步输出

## 1.2.0

- 内置 [SEPIA](https://github.com/Nanako0129/sepia) v0.12.4 技能包（MIT，原样引入，见 `NOTICE.md`）
  - `skills/` 下 6 个技能供 Agent 在你明确要求时做高质量改写与诊断
  - `always_on.md` 作为每轮注入的群聊版规则，两者共用一套事实来源
- 按 SEPIA 的实测依据修正清洗规则：
  - 破折号默认不再替换（不是模型无关特征）
  - 新增引文/代码/URL/版本号保护，不再误改引用内容
  - 新增双音节凑数规则（「进行讨论」→「讨论」）
- 新增 `/deai reload`，改完规则文件无需重启
- 配置项从 17 项增加到 23 项

## 1.1.0

- 支持与 Skill 融合：插件目录下的 `skills/` 会被 AstrBot 自动发现
- 新增 `style_source` / `skill_name` / `skill_max_chars` 配置

## 1.0.0

- 首次发布：提示词注入 + 规则清洗 + 可选二次重写三层去 AI 味
- `/deai status|on|off|test` 调试指令
