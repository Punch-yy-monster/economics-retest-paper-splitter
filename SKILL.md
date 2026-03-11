---
name: economics-retest-paper-splitter
description: "Split an economics paper or literature excerpt into two different postgraduate retest study materials for Chinese university economics candidates: interview-useful content and written-exam-useful content. Use when the user provides a Chinese, English, or mixed economics paper title, abstract, or body and wants strict JSON output for macroeconomics, microeconomics, digital economics, or related interdisciplinary economics retest preparation."
---

# Economics Retest Paper Splitter

## Overview

Turn one economics paper into two different retest outputs: `interview_useful` and `written_exam_useful`.
Detect language first, refuse to analyze when material is insufficient, and return only valid JSON once enough content is available.

For saved or downloadable outputs, use the bundled script at `scripts/generate_retest_json.py` as the primary path.
Do not hand-write JSON files when the script can produce them.

## Dependencies

Required Python package:

```bash
python3 -m pip install --user pypdf
```

`pypdf` is required for PDF extraction.
Poppler is not required for the main workflow.

## Gatekeeping

Apply these checks before analyzing:

1. Judge whether the user has provided enough text.
- If the user only gives a title, only a very short excerpt, or not enough content to identify the research question, conclusion, and mechanism, ask exactly:
`请补充摘要或正文内容，以便继续拆解。`

2. Judge language.
- Allowed labels: `中文文献`, `英文文献`, `中英混合文献`, `无法判断`.
- If the user explicitly states the language, use the user's label directly.
- If you cannot judge language with high confidence, ask exactly:
`请确认这是一篇中文文献、英文文献，还是中英混合文献？`

When blocked by either rule above, ask the required question in plain Chinese and do not output JSON yet.

## Analysis Workflow

### 1. Identify basic paper information

Extract only what the source supports:

- `title`
- `authors`
- `year`
- `language`
- `field`
- `keywords`

Set `field` to the best-fit label from:

- `宏观经济学`
- `微观经济学`
- `数字经济学`
- `相关经济学交叉方向`

Leave unknown values empty instead of inventing them.

### 2. Build a paper-level understanding

Infer or extract:

- research background
- research question
- research significance
- core conclusion
- mechanism chain
- policy or institutional background
- innovation
- limitations
- possible extension directions

Do not mirror the paper's section headings. Reorganize everything by retest usefulness.

### 3. Force the dual-channel split

Produce two different versions of the same paper:

#### `interview_useful`

Keep only content that helps with oral explanation, supervisor follow-up questions, mechanism interpretation, real-world linkage, policy implications, and literature evaluation.

Good labels include:

- `研究背景`
- `研究问题`
- `研究意义`
- `核心结论`
- `机制分析`
- `政策启示`
- `创新点`
- `局限性`
- `延伸研究方向`
- `导师可能追问`

For each item:

- explain the point in natural oral language
- show why it is useful in an interview
- give likely follow-up questions
- provide a short oral answer sample that sounds speakable instead of bookish

#### `written_exam_useful`

Keep only content that helps with term explanation, short-answer questions, essay questions, theory accumulation, standardized expression, and memorization.

Good labels include:

- `核心概念定义`
- `理论脉络`
- `理论框架`
- `机制链条`
- `规范化结论表述`
- `制度背景`
- `政策背景`
- `高频术语`
- `可背诵知识块`

For each item:

- rewrite in concise exam language
- make the logic chain explicit
- prefer definitional or normative phrasing
- make `exam_expression` directly writable in an answer sheet

## Rewrite Rules

Do not output a generic summary.
Do not mechanically restate `摘要-引言-方法-结论`.
Do not copy the same sentence into both channels.

If one knowledge point is useful for both interview and written exam:

- put the oral version in `interview_version`
- put the exam-style version in `written_version`
- record both in `overlap_but_rewritten`

Use these distinctions:

- Interview version: causal, explanatory, discussible, easy to say aloud
- Written version: compact, formal, easy to memorize, easy to score

## Output Rules

Once enough information is available, output only valid JSON.
Do not add Markdown, headings, or explanations outside JSON.
Keep field names exactly as defined in [references/output-schema.json](references/output-schema.json).

Populate arrays with only useful entries. Do not pad with empty objects.
Use empty strings or empty arrays only when a field truly cannot be supported by the source.

## Downloadable JSON Files

When the user asks for downloadable JSON, saved JSON, separate JSON files, or clearly intends to reuse the result outside the chat, write files in the current workspace after generating the analysis.

Prefer this command:

```bash
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf
```

For raw text:

```bash
python3 scripts/generate_retest_json.py --input-text "Title: ... Abstract: ..."
```

Use this directory convention:

- `output/economics-retest-paper-splitter/<paper-slug>/full.json`
- `output/economics-retest-paper-splitter/<paper-slug>/interview.json`
- `output/economics-retest-paper-splitter/<paper-slug>/written_exam.json`

Build `<paper-slug>` from the paper title:

- lowercase English if possible
- replace spaces and punctuation with hyphens
- keep it short and stable
- if the title is unavailable, use `untitled-paper`

File responsibilities:

- `full.json`: complete combined output using [references/output-schema.json](references/output-schema.json)
- `interview.json`: interview-only downloadable JSON using [references/interview-output-schema.json](references/interview-output-schema.json)
- `written_exam.json`: written-exam-only downloadable JSON using [references/written-output-schema.json](references/written-output-schema.json)

If the user explicitly asks only for one of the two channels, still prefer saving the requested file and mention the saved path.
If the user asks to analyze in chat only and does not ask to save, you may return JSON without creating files.

After writing files:

- mention the saved file paths in the response
- keep the JSON itself valid
- do not add extra commentary inside the JSON files
- treat the script output as the source of truth for saved files

## Field Guidance

### `one_sentence_summary`

Summarize the paper in one sentence focused on the research question and main conclusion, not on the paper's structure.

### `low_priority`

Place low-retention or low-retest-value material here, such as:

- overly technical estimation details
- robustness checks with low oral or written reuse
- data-cleaning minutiae
- tables or appendix details that do not improve retest performance

### `review_outline`

Return two short review routes:

- `interview_outline`: oral review order
- `written_outline`: memorization and answer-writing order

### `english_support`

Always support bilingual retest preparation when the paper contains English terms or when the topic clearly has standard English vocabulary.

Include:

- key terms with Chinese explanation
- oral sentence patterns for interviews
- written sentence patterns for written exams

### Split-file content

For `interview.json`, keep only fields useful for oral preparation and file reuse:

- `paper_info`
- `language_detect_result`
- `one_sentence_summary`
- `interview_useful`
- `review_outline.interview_outline`
- `extra.key_points`
- `extra.mechanisms`
- `extra.policy_implications`
- `extra.limitations`
- `english_support.key_terms`
- `english_support.oral_sentence_patterns`

For `written_exam.json`, keep only fields useful for written preparation and file reuse:

- `paper_info`
- `language_detect_result`
- `one_sentence_summary`
- `written_exam_useful`
- `review_outline.written_outline`
- `extra.key_points`
- `extra.mechanisms`
- `extra.policy_implications`
- `extra.limitations`
- `english_support.key_terms`
- `english_support.written_sentence_patterns`

## Style

Default to Chinese unless the user asks for another language.
Keep oral samples natural and short.
Keep written expressions standardized and easy to recite.
Prefer explicit mechanism chains such as `政策变化 -> 激励变化 -> 行为调整 -> 结果变化`.
