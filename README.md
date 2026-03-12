# 经济学复试文献四通道拆解器

[![MIT License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Codex Skill](https://img.shields.io/badge/Codex-Skill-blue)](./SKILL.md)
[![Output JSON](https://img.shields.io/badge/output-Standardized%20JSON-orange)](./references/output-schema.json)
[![Economics](https://img.shields.io/badge/domain-Economics-red)](./README.md)
[![Version](https://img.shields.io/badge/version-v2.0.0-black)](./README.md)

![封面图](./assets/cover.svg)

> A standardized four-channel paper splitter for Chinese economics postgraduate retest preparation.

这个项目不是普通摘要器，也不是泛泛总结工具。
它的目标是把一篇经济学论文、文献摘要、正文节选或 PDF，稳定拆成研究生复试可直接使用的标准化结构输出。

从这个版本开始，项目已升级为：

- 固定 5 个 mandatory modules
- 固定 4 个 retest channels
- 标准化 JSON
- 标准化 Excel 导出

## 项目用途

这个 skill 面向中国经济学研究生复试，适用方向包括：

- 宏观经济学
- 微观经济学
- 数字经济学
- 相关经济学交叉方向

它解决的问题不是“帮你看懂论文”，而是“把论文变成你在复试里能说、能写、能背、能导出的结构化材料”。

## 固定主框架

每篇论文都必须先生成同一组 5 个 mandatory modules：

1. `研究背景`
2. `研究问题`
3. `核心结论`
4. `机制分析`
5. `政策启示`

这些模块是强制项，不是建议项。

- 不允许遗漏
- 不允许改名
- 不允许用近义标题替代
- 不允许因论文类型不同而更换主框架

如果原文某一模块信息不足，该模块仍然必须保留，并明确说明：

- `原文未充分展开`
- `根据摘要/正文可推断为……`

## 四通道输出

在固定 5 模块的基础上，项目会生成以下四个复试通道：

1. `general_interview`
2. `english_interview`
3. `professional_written_exam`
4. `english_written_exam`

四个通道都围绕同一组 mandatory modules 展开，不会各自重新选方向。

### `general_interview`

- 中文综合面试
- 自然、清晰、适合导师问答
- 答案应适合 30 到 90 秒的口头表达

### `english_interview`

- 英文面试
- 专业、自然、适合口试
- 术语准确，不能有明显直译腔

### `professional_written_exam`

- 中文专业课笔试
- 规范、精炼、逻辑清晰
- 适合卷面作答和得分

### `english_written_exam`

- 英文笔试
- 专业书面英语
- 适合英文短答题和分析题

## 与旧双通道结构相比的升级

旧版本主干是：

- `interview_useful`
- `written_exam_useful`

新版本主干升级为：

- 固定 5 模块
- 四通道并行输出
- 英文不再是附属翻译字段
- Excel sheet 与 JSON 字段完全对齐

升级后最大的变化是：

- 结构固定，不再根据论文类型自由改主框架
- 所有通道围绕相同 5 模块展开
- 更适合导入 JSON、Excel 和后续题库/知识库

## JSON 结构

完整输出见 [references/output-schema.json](./references/output-schema.json)。

顶层固定字段：

- `meta`
- `paper_info`
- `language_detect_result`
- `mandatory_blocks`
- `one_sentence_summary`
- `general_interview`
- `english_interview`
- `professional_written_exam`
- `english_written_exam`
- `review_outline`
- `terms`
- `low_priority`
- `extra`

其中 `mandatory_blocks` 固定包含：

- `research_background`
- `research_question`
- `core_conclusion`
- `mechanism_analysis`
- `policy_implication`

### 示例输出结构

```json
{
  "meta": {
    "schema_version": "2.0",
    "output_version": "2.0.0",
    "framework": "five-mandatory-modules-four-channels"
  },
  "mandatory_blocks": {
    "research_background": "本文讨论数字化条件变化为何会成为经济学研究的重要议题。",
    "research_question": "文章关注数字化变量如何影响经济行为与结果。",
    "core_conclusion": "文章认为数字化因素会显著影响目标经济结果，但强度受制度条件约束。",
    "mechanism_analysis": "文章强调数字化通过改变信息不对称、资源配置与激励结构来发挥作用。",
    "policy_implication": "文章提示政策设计必须兼顾效率提升与治理能力。"
  },
  "general_interview": [
    {
      "module": "research_background",
      "question": "请用口头方式概括这篇论文的研究背景。",
      "answer": "如果口头概括这篇论文的研究背景，我会先说：本文讨论数字化条件变化为何会成为经济学研究的重要议题。",
      "why_this_matters": "研究背景决定你能否先把论文讲顺，避免一开口就进入细节。"
    }
  ],
  "english_interview": [
    {
      "module": "research_background",
      "question_en": "Why is this topic worth studying in the first place?",
      "answer_en": "The paper starts from the observation that digital technologies are reshaping economic activity, so the author tries to explain why the issue matters economically.",
      "terminology_notes": "digital economics (数字经济); information asymmetry (信息不对称)"
    }
  ],
  "professional_written_exam": [
    {
      "module": "research_background",
      "question": "请概括本文的研究背景。",
      "answer": "从研究背景看，本文讨论数字化条件变化为何会成为经济学研究的重要议题。",
      "answer_type": "简答题"
    }
  ],
  "english_written_exam": [
    {
      "module": "research_background",
      "question_en": "Summarize the research background of the paper.",
      "answer_en": "The research background lies in the growing importance of digitalization and in the need to explain its economic consequences in a structured way.",
      "answer_type": "short-answer"
    }
  ]
}
```

## Excel 导出

当你要求保存结果时，脚本会在输出目录中生成：

- `full.json`
- `general_interview.json`
- `english_interview.json`
- `professional_written_exam.json`
- `english_written_exam.json`
- `retest_pack.xlsx`
- `retest_pack_memorize.xlsx`
- `retest_pack_print.xlsx`
- `run-report.json`

Excel 工作簿固定包含这些 sheet：

- `Overview`
- `Mandatory Blocks`
- `General Interview`
- `English Interview`
- `Professional Written`
- `English Written`
- `Terms`
- `Run Report`

三个 Excel 文件的用途：

- `retest_pack.xlsx`: 默认通用版
- `retest_pack_memorize.xlsx`: 更适合背诵和高亮复习
- `retest_pack_print.xlsx`: 更适合打印和纸质阅读

## 安装依赖

```bash
python3 -m pip install --user pypdf openpyxl
```

## 安装 skill

```bash
mkdir -p ~/.codex/skills
ln -s /path/to/economics-retest-paper-splitter ~/.codex/skills/economics-retest-paper-splitter
```

然后重开一个 Codex 会话，使用：

```text
$economics-retest-paper-splitter
```

## 运行方式

### 在 Codex 中调用

```text
使用 $economics-retest-paper-splitter 将这篇经济学文献拆成适合综合面试、英文面试、专业课笔试和英文笔试的标准化 JSON 与 Excel 结果。
```

### 直接运行脚本

```bash
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf
```

常用参数：

```bash
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf --output-dir /path/to/output
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf --slug custom-paper-id
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf --language 英文文献
python3 scripts/generate_retest_json.py --input-text "Title: ... Abstract: ..." --stdout-json
```

## 示例输入

```text
使用 $economics-retest-paper-splitter 分析下面这篇文献，并生成 full.json、四个 split JSON 和 Excel。

标题：数字基础设施建设与地区创新质量提升

摘要：本文基于 2011—2022 年中国地级市面板数据，考察数字基础设施建设对地区创新质量的影响。研究发现，数字基础设施显著提升地区创新质量，这一作用在东部地区和高人力资本地区更为明显。机制检验表明，数字基础设施主要通过降低信息不对称、改善金融资源配置和促进知识溢出来提升创新质量。进一步分析发现，地方政府数字治理能力越强，数字基础设施对创新质量的促进作用越明显。
```

## 阻断规则

如果只有标题，没有摘要或正文，项目不会直接生成 JSON，而会返回：

```text
请补充摘要或正文内容，以便继续拆解。
```

如果语言无法判断，会先返回：

```text
请确认这是一篇中文文献、英文文献，还是中英混合文献？
```

## 低优先级内容如何处理

以下内容优先下沉到 `low_priority`，不会占据主干结构：

- 过细的数据清洗过程
- 稳健性检验的附录细节
- 附录级技术推导
- 对复试口答和卷面帮助较弱的表格信息

## 回归样例

仓库内置了成功样例和失败样例，运行：

```bash
python3 scripts/check_examples.py
```

它会检查：

- 固定 5 模块是否稳定存在
- 四个通道是否都围绕同一组模块展开
- split JSON 是否与 full.json 保持一致骨架
- Excel sheet 结构是否正确
- 信息不足时是否正确阻断

## 当前版本说明

当前实现版本：

- `schema_version = 2.0`
- `output_version = 2.0.0`
- `framework = five-mandatory-modules-four-channels`

该版本与旧双通道输出不兼容。
如果你仍然依赖旧字段 `interview_useful` / `written_exam_useful`，需要按新 schema 适配。

## License

MIT. See [LICENSE](./LICENSE).
