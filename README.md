# 经济学复试文献双通道拆解器

将一篇经济学文献强制拆成两套不同用途的复试材料：

- 面试有用内容
- 笔试有用内容

这个技能面向中国高校经济学研究生复试考生，适用方向包括：

- 宏观经济学
- 微观经济学
- 数字经济学
- 相关经济学交叉方向

它不是通用摘要器。它的目标是把同一篇文献改写成两套不同的复试表达材料，并以严格 JSON 返回。

## 适用场景

当你希望 Codex 在阅读经济学文献后，直接输出适合复试准备的材料时，使用这个技能：

- 将论文拆成“面试表达版”和“笔试作答版”
- 识别研究背景、研究问题、机制分析、政策启示、创新点、局限性
- 提取核心概念、理论脉络、机制链条、规范化结论和高频术语
- 为英文或中英混合文献补充复试常用英文术语和句型

## 主要特性

- 强制双通道拆解，而不是普通摘要
- 先做语言识别，再决定是否继续分析
- 信息不足时先追问，不盲目输出
- 面试版和笔试版禁止原样复制
- 同一知识点如果同时适用于两者，会分别改写并记录在 `overlap_but_rewritten`
- 输出仅为合法 JSON，便于后续保存、程序处理或二次加工

## 安装

将技能目录放到 `~/.codex/skills/` 下，或使用软链接安装：

```bash
mkdir -p ~/.codex/skills
ln -s /path/to/economics-retest-paper-splitter ~/.codex/skills/economics-retest-paper-splitter
```

如果你是从这个仓库直接使用，把 `/path/to/economics-retest-paper-splitter` 替换为仓库本地路径。

安装后重开一个 Codex 会话，或重启桌面应用以刷新技能列表。

## 触发方式

在对话中显式提到：

```text
$economics-retest-paper-splitter
```

例如：

```text
使用 $economics-retest-paper-splitter 拆解这篇数字经济文献，输出适合复试面试和笔试的 JSON。
```

## 输入要求

优先提供以下任一内容：

- 论文标题 + 摘要
- 论文摘要 + 关键结论
- 论文正文节选
- 完整正文

如果只提供标题、只提供很短的一段、或信息不足以识别研究问题与机制，技能会先追问：

```text
请补充摘要或正文内容，以便继续拆解。
```

如果无法高置信度判断语言，技能会先追问：

```text
请确认这是一篇中文文献、英文文献，还是中英混合文献？
```

## 输出结构

输出为严格 JSON，核心字段包括：

- `paper_info`
- `language_detect_result`
- `one_sentence_summary`
- `interview_useful`
- `written_exam_useful`
- `overlap_but_rewritten`
- `low_priority`
- `review_outline`
- `extra`
- `english_support`

完整结构见 [references/output-schema.json](references/output-schema.json)。

## 使用原则

- 不输出普通摘要
- 不按“摘要、引言、方法、结论”机械复述
- 不把同样内容原样复制到面试和笔试两部分
- 默认使用中文输出，除非用户另有要求

## 仓库结构

```text
.
├── SKILL.md
├── README.md
├── LICENSE
├── agents/
│   └── openai.yaml
└── references/
    └── output-schema.json
```

## License

MIT. See [LICENSE](LICENSE).
