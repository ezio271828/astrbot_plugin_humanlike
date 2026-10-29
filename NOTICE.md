# 第三方来源与许可

## SEPIA

本插件的 `skills/` 目录**逐字节原样**包含了 SEPIA 的技能包，未做任何修改：

- 项目：SEPIA — https://github.com/Nanako0129/sepia
- 版本：`0.12.4`
- 引入的 commit：`fb06be76abeae7dd606960a32f2b10c1d1798e0d`（2026-10-15）
- 作者：Nanako Tsai
- 许可：MIT（全文见下方）

包含的技能：

```
skills/sepia/                # 规范体：路由 + 四个操作 + references/
skills/sepia-write/          # write 操作入口
skills/sepia-review/         # review 操作入口（只诊断不改）
skills/sepia-refactor/       # refactor 操作入口（最小编辑）
skills/sepia-recreate/       # recreate 操作入口（整体重写）
skills/sepia-hemingway/      # 可选的声音 skill
```

升级方式：把上游 `skills/` 重新覆盖到本目录同名位置即可，不需要改任何代码（`diff -r` 可校验）。

### 派生文件

`always_on.md` 是**本插件作者依据 SEPIA 的规则写出的提取版**，用于群聊短回复场景的每轮注入，
不是 SEPIA 原文。它引用的具体依据（`style-pass.md §2/§3/§4/§7`、`languages/zh.md §1/§2/§3/§5`、
`domains/dev-replies.md`、`professional-pass.md`）以 `skills/sepia/` 内的原文为准。
如果上游这几分文件有变化，`always_on.md` 需要人工复核。

---

## MIT License（SEPIA）

```
MIT License

Copyright (c) 2026 Nanako Tsai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
