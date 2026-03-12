---
name: economics-retest-paper-splitter
description: "A standardized four-channel paper splitter for Chinese economics postgraduate retest preparation. Use when the user provides an economics paper title, abstract, excerpt, body, or PDF and wants fixed JSON or Excel outputs for general interview, English interview, professional written exam, and English written exam preparation."
---

# Economics Retest Paper Splitter

## Overview

This skill is not a generic summary tool.
It is a standardized output tool for Chinese economics postgraduate retest preparation.

Every valid output must follow one fixed backbone:

1. `研究背景`
2. `研究问题`
3. `核心结论`
4. `机制分析`
5. `政策启示`

On top of these five mandatory modules, every paper must be expanded into four fixed channels:

1. `general_interview`
2. `english_interview`
3. `professional_written_exam`
4. `english_written_exam`

The structure is fixed across papers.
Depth may vary.
The framework may not vary.

For saved or downloadable outputs, use the bundled script at `scripts/generate_retest_json.py`.
Do not hand-write JSON files when the script can produce them.

## Trigger Conditions

Use this skill when the user does any of the following:

- provides an economics paper title, abstract, excerpt, body, or PDF
- asks to split a paper for postgraduate retest preparation
- asks to distinguish general interview, English interview, professional written exam, and English written exam
- asks for structured JSON output or downloadable Excel output

## Dependencies

Required Python packages:

```bash
python3 -m pip install --user pypdf openpyxl
```

- `pypdf` is required for PDF extraction
- `openpyxl` is required for Excel export
- Poppler is not required for the main workflow

## Blocking Rules

Apply these checks before generating any JSON:

1. If the user only gives a title, or the text is too short to support `研究背景`、`研究问题`、`核心结论`、`机制分析`、`政策启示`, do not output JSON.
Ask exactly:

`请补充摘要或正文内容，以便继续拆解。`

2. If the language cannot be judged with enough confidence, do not guess.
Ask exactly:

`请确认这是一篇中文文献、英文文献，还是中英混合文献？`

3. If the source cannot support a standardized retest-oriented split, block instead of inventing content.

4. If a module is weakly supported, keep the module anyway.
Use explicit wording such as:

- `原文未充分展开`
- `根据摘要/正文可推断为……`

Do not delete the module.

## Mandatory Analysis Backbone

Every paper must first be organized into the same five mandatory modules:

- `研究背景`
- `研究问题`
- `核心结论`
- `机制分析`
- `政策启示`

These five modules are mandatory, not suggested.

The skill may additionally produce:

- `创新点`
- `局限性`
- `延伸研究`
- `术语表`

But optional additions may never replace the five mandatory modules.

## Four-Channel Constraints

All four channels must be built around the same five mandatory modules.
The channels may differ in style and depth, but not in backbone.

### `general_interview`

- Chinese
- natural and clear
- suitable for supervisor-style oral questioning
- each answer should be speakable in about 30 to 90 seconds

### `english_interview`

- English
- professional and natural
- suitable for oral interview use
- terminology must be accurate
- do not sound like a literal translation of Chinese output

### `professional_written_exam`

- Chinese
- standardized and concise
- logically organized
- suitable for high-scoring written exam answers

### `english_written_exam`

- professional written English
- suitable for short-answer and analytical written responses
- distinct from oral English in tone and sentence structure

## Consistency Rules

The following rules are mandatory:

- every paper must keep the same five mandatory modules
- every module must have corresponding content in all four channels
- different papers may have different content, but not different top-level structure
- module names may not be changed
- modules may not be omitted
- modules may not be replaced by near-synonyms
- optional sections may be added, but the mandatory backbone may not change

## Output Rules

Once enough information is available, output only valid JSON or script-generated files.
Keep field names exactly aligned with `references/output-schema.json`.

Top-level full output must contain:

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

`mandatory_blocks` must always contain:

- `research_background`
- `research_question`
- `core_conclusion`
- `mechanism_analysis`
- `policy_implication`

If a module is weakly supported, preserve the field and state that the original text did not fully elaborate it.

## Downloadable Files

When the user asks for saved JSON, downloadable JSON, reusable structured output, or Excel export, prefer:

```bash
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf
```

For raw text:

```bash
python3 scripts/generate_retest_json.py --input-text "Title: ... Abstract: ..."
```

Useful stable options:

```bash
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf --output-dir /path/to/output
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf --slug custom-paper-id
python3 scripts/generate_retest_json.py --input-file /path/to/paper.pdf --language 英文文献
python3 scripts/generate_retest_json.py --input-text "Title: ... Abstract: ..." --stdout-json
```

Use this directory convention:

- `output/economics-retest-paper-splitter/<paper-slug>/full.json`
- `output/economics-retest-paper-splitter/<paper-slug>/general_interview.json`
- `output/economics-retest-paper-splitter/<paper-slug>/english_interview.json`
- `output/economics-retest-paper-splitter/<paper-slug>/professional_written_exam.json`
- `output/economics-retest-paper-splitter/<paper-slug>/english_written_exam.json`
- `output/economics-retest-paper-splitter/<paper-slug>/retest_pack.xlsx`
- `output/economics-retest-paper-splitter/<paper-slug>/retest_pack_memorize.xlsx`
- `output/economics-retest-paper-splitter/<paper-slug>/retest_pack_print.xlsx`

File responsibilities:

- `full.json`: full four-channel output
- `general_interview.json`: Chinese comprehensive interview channel
- `english_interview.json`: English interview channel
- `professional_written_exam.json`: Chinese professional written-exam channel
- `english_written_exam.json`: English written-exam channel
- `retest_pack.xlsx`: default workbook
- `retest_pack_memorize.xlsx`: memorize-focused workbook
- `retest_pack_print.xlsx`: print-focused workbook
- `run-report.json`: debug metadata for extraction and generation

## Excel Structure

Excel output should preserve the same standardized structure and at least include:

- `Overview`
- `Mandatory Blocks`
- `General Interview`
- `English Interview`
- `Professional Written`
- `English Written`
- `Terms`
- `Run Report`

## Low-Priority Material

Push the following content into `low_priority` instead of the main backbone:

- over-detailed data cleaning procedures
- robustness details with weak retest transferability
- appendix-level technical derivations
- table details with weak oral or written reuse value

## Prohibitions

Do not do any of the following:

- produce a generic full-paper summary
- mechanically mirror `引言/方法/结果/结论`
- use `引言/方法/结果/结论` as a substitute for the retest structure
- copy one sentence into all four channels
- treat English output as an attached translation field
- generate empty or low-value filler for the sake of completeness
- change the mandatory module names to better-sounding variants
- drop a mandatory module because the paper is a review, an empirical study, or a theoretical paper

## Failure Handling

Use the script exit codes as the source of truth:

- `1`: 信息不足
- `2`: 语言无法判断
- `3`: PDF 抽取失败
- `4`: schema 校验失败
