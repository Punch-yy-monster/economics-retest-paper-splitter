#!/usr/bin/env python3
"""Generate stable retest JSON outputs from a paper text or PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader


STANDARD_TEXT_PROMPT = "请补充摘要或正文内容，以便继续拆解。"
STANDARD_LANGUAGE_PROMPT = "请确认这是一篇中文文献、英文文献，还是中英混合文献？"

MIN_TEXT_LENGTH = 180
MIN_PDF_TEXT_LENGTH = 500
MIN_NON_EMPTY_PAGE_RATIO = 0.2

ROOT = Path(__file__).resolve().parents[1]
FULL_SCHEMA_PATH = ROOT / "references" / "output-schema.json"
INTERVIEW_SCHEMA_PATH = ROOT / "references" / "interview-output-schema.json"
WRITTEN_SCHEMA_PATH = ROOT / "references" / "written-output-schema.json"

FIELD_KEYWORDS = {
    "数字经济学": [
        "digital",
        "digitization",
        "digitisation",
        "internet",
        "platform",
        "data",
        "algorithm",
        "online",
        "privacy",
        "ai ",
        "人工智能",
        "数字",
        "平台",
        "数据",
        "算法",
        "互联网",
    ],
    "宏观经济学": [
        "gdp",
        "inflation",
        "monetary",
        "fiscal",
        "business cycle",
        "growth",
        "失业",
        "通胀",
        "货币政策",
        "财政政策",
        "宏观",
        "经济增长",
    ],
    "微观经济学": [
        "consumer",
        "firm",
        "market",
        "pricing",
        "competition",
        "search cost",
        "价格",
        "消费者",
        "企业",
        "市场",
        "竞争",
        "微观",
    ],
}

DIGITAL_COST_LABELS = [
    ("search", "搜索成本"),
    ("replication", "复制成本"),
    ("transportation", "运输成本"),
    ("tracking", "追踪成本"),
    ("verification", "验证成本"),
]

KEYWORD_FALLBACKS = {
    "数字经济学": [
        "digital economics",
        "digital technology",
        "platform economics",
        "data",
        "privacy",
    ],
    "宏观经济学": [
        "economic growth",
        "inflation",
        "monetary policy",
        "fiscal policy",
        "business cycle",
    ],
    "微观经济学": [
        "market structure",
        "consumer behavior",
        "pricing",
        "competition",
        "search costs",
    ],
    "相关经济学交叉方向": [
        "economics",
        "policy",
        "institutions",
        "welfare",
        "technology",
    ],
}

POLICY_TERMS = {
    "network neutrality": "网络中立",
    "privacy": "隐私保护",
    "copyright": "版权治理",
    "discrimination": "反歧视",
    "reputation": "声誉机制",
    "platform": "平台规则",
    "net neutrality": "网络中立",
}


class UserFacingError(Exception):
    """Message that should be shown directly to the user."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate retest JSON outputs from a paper.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-file", type=Path, help="Path to a PDF, TXT, or MD file.")
    group.add_argument("--input-text", help="Inline text content.")
    return parser.parse_args()


def read_text_input(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    return path.read_text(encoding="utf-8")


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    joined = "\n".join(text for text in page_texts if text)
    non_empty_pages = sum(1 for text in page_texts if len(text) >= 80)
    ratio = non_empty_pages / max(1, len(page_texts))
    if len(clean_text(joined)) < MIN_PDF_TEXT_LENGTH or ratio < MIN_NON_EMPTY_PAGE_RATIO:
        raise UserFacingError(STANDARD_TEXT_PROMPT)
    return joined


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_language(text: str) -> tuple[str, str, str]:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z]{2,}", text))
    if chinese_chars >= 50 and latin_words < 60:
        return "中文文献", "high", "正文以中文句子为主，英文词汇占比较低。"
    if latin_words >= 120 and chinese_chars < 30:
        return "英文文献", "high", "标题、摘要或正文主体以英文连续文本为主。"
    if chinese_chars >= 30 and latin_words >= 50:
        return "中英混合文献", "medium", "文本同时包含较多中文内容与英文术语或段落。"
    raise UserFacingError(STANDARD_LANGUAGE_PROMPT)


def normalize_title_case(title: str) -> str:
    words = title.split()
    if not words:
        return title
    if all(word.isupper() for word in words if re.search(r"[A-Z]", word)):
        return " ".join(word.capitalize() for word in words)
    return title


def extract_title(text: str, input_path: Path | None) -> str:
    explicit_patterns = [
        r"(?:^|\n)标题[:：]\s*(.+)",
        r"(?:^|\n)Title[:：]\s*(.+)",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    skip_patterns = [
        r"working paper",
        r"series",
        r"http",
        r"journal",
        r"nber",
        r"massachusetts avenue",
        r"st\. george street",
        r"main street",
        r"abstract",
        r"jel",
        r"keywords?",
        r"references",
    ]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:40]:
        lowered = line.lower()
        if len(line) < 4 or len(line) > 140:
            continue
        if any(re.search(pattern, lowered) for pattern in skip_patterns):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]", line):
            return normalize_title_case(line)

    if input_path is not None:
        return normalize_title_case(input_path.stem.replace("-", " "))
    return "Untitled Paper"


def extract_authors(text: str, title: str) -> list[str]:
    patterns = [
        r"(?:^|\n)作者[:：]\s*(.+)",
        r"(?:^|\n)Authors?[:：]\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            parts = [part.strip() for part in re.split(r"[,;，、]| and ", raw) if part.strip()]
            return parts[:4]

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    name_pattern = re.compile(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}$")
    try:
        title_index = next(index for index, line in enumerate(lines[:50]) if line == title)
    except StopIteration:
        title_index = 0

    authors: list[str] = []
    for line in lines[title_index + 1 : title_index + 8]:
        candidate = line.replace("∗", "").replace("†", "").strip()
        if name_pattern.fullmatch(candidate):
            authors.append(candidate)
    return authors[:4]


def extract_year(text: str) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else ""


def extract_abstract(text: str) -> str:
    patterns = [
        r"(?:ABSTRACT|Abstract)\s*(.+?)(?:\n\s*1\s+[A-Z]|\n\s*Keywords|\n\s*JEL|\n\s*[0-9]+\.[0-9]+|\n\s*[一二三四五六七八九十]+[、.])",
        r"(?:摘要)\s*(.+?)(?:\n\s*关键词|\n\s*[一二三四五六七八九十]+[、.])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1))

    fallback_patterns = [
        r"(?:ABSTRACT|Abstract)[:：]?\s*(.+)$",
        r"(?:摘要)[:：]?\s*(.+)$",
    ]
    for pattern in fallback_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1))

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if paragraphs:
        return clean_text(paragraphs[0])[:1600]
    return ""


def split_sentences(text: str, language: str) -> list[str]:
    if not text:
        return []
    if language == "中文文献":
        parts = re.split(r"(?<=[。！？；])", text)
    else:
        parts = re.split(r"(?<=[.!?])\s+", text)
    sentences = [clean_text(part) for part in parts if clean_text(part)]
    return sentences


def determine_field(title: str, abstract: str) -> str:
    haystack = f"{title}\n{abstract}".lower()
    scores = {}
    for field, keywords in FIELD_KEYWORDS.items():
        scores[field] = sum(1 for keyword in keywords if keyword in haystack)
    best_field = max(scores, key=scores.get)
    return best_field if scores[best_field] > 0 else "相关经济学交叉方向"


def extract_keywords(text: str, field: str) -> list[str]:
    patterns = [
        r"(?:Keywords?|关键词)[:：]\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            return [part.strip() for part in re.split(r"[,;，、]", raw) if part.strip()][:8]
    return KEYWORD_FALLBACKS[field]


def slugify(title: str) -> str:
    title = title.lower()
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", title)
    ascii_slug = re.sub(r"-{2,}", "-", ascii_slug).strip("-")
    if ascii_slug:
        return ascii_slug
    digest = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    return f"paper-{digest}"


def detect_cost_terms(text: str) -> list[str]:
    lowered = text.lower()
    labels = [label for token, label in DIGITAL_COST_LABELS if token in lowered]
    return labels


def detect_policy_topics(text: str) -> list[str]:
    lowered = text.lower()
    topics = [label for token, label in POLICY_TERMS.items() if token in lowered]
    deduped: list[str] = []
    for topic in topics:
        if topic not in deduped:
            deduped.append(topic)
    return deduped[:4]


def build_topic_summary(title: str, abstract_sentences: list[str], language: str) -> str:
    if not abstract_sentences:
        return f"本文围绕《{title}》展开，重点讨论其核心研究问题与结论。"
    if language == "中文文献":
        lead = abstract_sentences[0]
        return lead if len(lead) <= 80 else lead[:80]
    first = abstract_sentences[0][:120]
    return f"本文围绕《{title}》展开，摘要首先强调：{first}"


def build_interview_useful(
    title: str,
    abstract: str,
    abstract_sentences: list[str],
    field: str,
    cost_terms: list[str],
    policy_topics: list[str],
    is_review: bool,
) -> list[dict[str, Any]]:
    mechanism_line = (
        "、".join(cost_terms)
        if cost_terms
        else "关键交易成本、信息获取成本与制度协调成本"
    )
    policy_line = "、".join(policy_topics) if policy_topics else "平台治理、数据使用规则与制度约束"
    abstract_focus = abstract_sentences[0] if abstract_sentences else abstract[:160]
    conclusion_focus = abstract_sentences[-1] if abstract_sentences else "文章强调数字技术并不会自动带来单一方向的福利提升。"

    return [
        {
            "label": "研究背景",
            "core_content": f"《{title}》的研究背景可以概括为：{abstract_focus}",
            "reason_for_interview": "适合开场说明文章切入点，帮助快速建立你对文献的整体把握。",
            "typical_questions": [
                "这篇文章为什么值得研究？",
                "作者关注的现实背景是什么？",
            ],
            "oral_answer_sample": f"我理解这篇文章的背景是，{abstract_focus}，所以作者想从经济学角度解释这种变化到底改变了什么。 ",
        },
        {
            "label": "研究问题",
            "core_content": f"本文核心要回答的是：在{field}语境下，哪些成本或约束发生了变化，以及这种变化如何影响经济活动与制度安排。",
            "reason_for_interview": "能帮助你把文章主线概括成一句可回答的话。",
            "typical_questions": [
                "这篇文章到底在研究什么？",
                "如果一句话概括这篇文献，你会怎么说？",
            ],
            "oral_answer_sample": "如果一句话概括，我会说作者是在讨论数字化条件下，哪些关键成本下降了，以及这些变化怎样重塑经济行为。 ",
        },
        {
            "label": "机制分析",
            "core_content": f"文章最核心的机制框架是围绕{mechanism_line}展开。作者的逻辑不是把数字经济看成全新理论，而是强调成本结构变化之后，经典经济模型会得出不同的行为结果。",
            "reason_for_interview": "机制是导师最可能继续追问的部分，也是最能体现理解深度的部分。",
            "typical_questions": [
                "文章的核心机制是什么？",
                "为什么说数字经济的关键是成本下降？",
            ],
            "oral_answer_sample": f"我觉得作者最重要的贡献是把问题收束到{mechanism_line}这条主线上，也就是数字化先改变成本条件，再改变交易和组织方式。 ",
        },
        {
            "label": "核心结论",
            "core_content": conclusion_focus,
            "reason_for_interview": "适合回答“文章最重要的发现是什么”。",
            "typical_questions": [
                "作者最后得出了什么判断？",
                "文章的总体结论是什么？",
            ],
            "oral_answer_sample": "作者最后的判断不是数字化一定单向改善一切，而是它显著重塑了经济成本结构，因此效果取决于组织、技能和制度环境。 ",
        },
        {
            "label": "政策启示",
            "core_content": f"从政策层面看，文章提示需要重点关注{policy_line}等问题，因为数字技术带来效率提升的同时，也会放大治理与规则设计的重要性。",
            "reason_for_interview": "适合把文献和现实政策问题连接起来。",
            "typical_questions": [
                "这篇文章有什么政策含义？",
                "数字经济研究为什么会落到治理问题上？",
            ],
            "oral_answer_sample": f"我觉得这篇文章一个很强的现实启示是，数字经济不能只看效率，还要看{policy_line}这些制度问题。 ",
        },
        {
            "label": "创新点",
            "core_content": (
                "文章的创新在于提供了一个统一的解释框架，把分散的数字经济研究整合到同一条经济学主线中。"
                if is_review
                else "文章的创新主要体现在以数字化引发的成本变化为主线解释具体经济现象。"
            ),
            "reason_for_interview": "能体现你不仅看到了结论，也理解文章的方法论价值。",
            "typical_questions": [
                "这篇文章的贡献体现在哪里？",
                "你觉得它为什么有代表性？",
            ],
            "oral_answer_sample": "我认为它最大的价值，是把很多零散问题整合成一个统一框架，而不是只罗列数字经济现象。 ",
        },
        {
            "label": "局限性",
            "core_content": "这篇文章更强于框架整合，弱于对单个机制的严格识别；如果要判断某个具体结论是否稳健，还需要回到对应的实证文献中去看。",
            "reason_for_interview": "适合回答文献评价题，避免只说优点不说不足。",
            "typical_questions": [
                "这篇文章有什么不足？",
                "你觉得它还有哪些没有展开的地方？",
            ],
            "oral_answer_sample": "如果从文献评价角度看，我会说这篇文章强在总框架，但弱在它毕竟不是单篇识别型论文，所以很多结论还要结合具体研究再判断。 ",
        },
        {
            "label": "延伸研究方向",
            "core_content": "后续可以继续追问新技术条件下是否出现新的成本下降类型，以及同一机制在不同国家、行业和制度环境中为何会表现出不同的结果。",
            "reason_for_interview": "适合回答“如果继续研究你会怎么做”。",
            "typical_questions": [
                "如果往下做研究，你会怎么延伸？",
                "这篇文章对今天的研究还有哪些启发？",
            ],
            "oral_answer_sample": "如果往后延伸，我会关注新技术是不是带来了新的成本变化，以及这些变化在不同制度环境下为什么会有不同效果。 ",
        },
    ]


def build_written_exam_useful(
    title: str,
    field: str,
    cost_terms: list[str],
    policy_topics: list[str],
    abstract_sentences: list[str],
) -> list[dict[str, Any]]:
    mechanism_line = "、".join(cost_terms) if cost_terms else "搜索成本、交易成本与信息不对称成本"
    policy_line = "、".join(policy_topics) if policy_topics else "平台治理、隐私保护与制度监管"
    opening = abstract_sentences[0] if abstract_sentences else f"《{title}》围绕数字技术如何影响经济活动展开讨论。"

    return [
        {
            "label": "核心概念定义",
            "core_content": f"{opening}",
            "reason_for_written_exam": "适合用于名词解释和“什么是该研究主题”类简答题。",
            "question_types": ["名词解释", "简答题"],
            "exam_expression": f"就《{title}》所体现的研究思路而言，{field}的核心不在于单纯讨论技术本身，而在于分析技术变化如何通过成本重构影响经济行为。",
        },
        {
            "label": "理论脉络",
            "core_content": f"文章将{field}问题放回标准经济学框架中理解，强调在成本结构变化后，既有搜索理论、价格理论、声誉理论和组织理论需要重新解释数字化现象。",
            "reason_for_written_exam": "适合文献综述题和理论来源题。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"从理论脉络看，文章并未脱离传统经济学，而是在既有理论基础上，围绕{mechanism_line}等成本变化重构对数字经济的解释。 ",
        },
        {
            "label": "理论框架",
            "core_content": f"全文的理论框架可概括为“数字化 -> 成本下降 -> 交易与组织方式变化 -> 效率、福利与治理结果变化”，其中重点成本包括{mechanism_line}。",
            "reason_for_written_exam": "适合论述题中搭建总分结构。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"文章构建的分析框架是：数字技术推动关键成本下降，关键成本下降进一步影响市场交易、平台组织、企业决策与政策治理。 ",
        },
        {
            "label": "机制链条",
            "core_content": f"数字化 -> 信息处理与传输更便宜 -> {mechanism_line}下降 -> 市场匹配、价格形成、平台组织和福利分配发生变化。",
            "reason_for_written_exam": "适合机制展开题。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"从作用机制看，数字化通过降低{mechanism_line}，重塑了交易成本、信息流动和组织边界，并据此改变市场运行机制。 ",
        },
        {
            "label": "规范化结论表述",
            "core_content": "数字技术的经济效应并不只是简单提升效率，而是通过重构成本结构带来复杂且具有异质性的行为后果。",
            "reason_for_written_exam": "适合论述题结尾总结。",
            "question_types": ["论述题"],
            "exam_expression": "总体而言，数字经济的本质是成本结构重塑。其影响既表现为效率提升，也表现为平台治理、制度约束和分配结果的复杂变化。 ",
        },
        {
            "label": "政策背景",
            "core_content": f"文章涉及的政策背景主要包括{policy_line}，表明数字经济研究天然带有强烈的制度与治理维度。",
            "reason_for_written_exam": "适合联系现实制度背景作答。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"在政策层面，数字经济并非仅涉及技术扩散问题，还涉及{policy_line}等制度安排。 ",
        },
        {
            "label": "高频术语",
            "core_content": f"{', '.join(token for token, _ in DIGITAL_COST_LABELS if any(token == cost_en for cost_en, _ in DIGITAL_COST_LABELS if _ in cost_terms)) or 'search costs, consumer surplus, platform governance, privacy'}",
            "reason_for_written_exam": "适合术语积累与英文表达。",
            "question_types": ["名词解释", "简答题"],
            "exam_expression": "作答时可围绕‘成本下降—市场重构—政策治理’这一主线展开，并结合高频术语提升表达规范性。 ",
        },
        {
            "label": "可背诵知识块",
            "core_content": f"《{title}》所体现的基本逻辑是：信息数字化带来关键成本下降，关键成本下降改变交易和组织方式，交易和组织方式变化进一步影响效率、福利与治理结果。",
            "reason_for_written_exam": "适合直接背诵并迁移到论述题。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"{field}的核心逻辑可以概括为：技术进步导致成本条件变化，成本条件变化导致行为与制度安排变化，行为与制度安排变化最终影响经济绩效。 ",
        },
    ]


def build_overlap(cost_terms: list[str], policy_topics: list[str]) -> list[dict[str, str]]:
    mechanism = "、".join(cost_terms) if cost_terms else "关键成本下降"
    policy = "、".join(policy_topics) if policy_topics else "平台治理与隐私保护"
    return [
        {
            "topic": "数字经济的本质",
            "interview_version": "可以把它理解为数字技术先改变了成本条件，经济行为才跟着变。",
            "written_version": "数字经济的本质是数字化引发关键经济成本下降，并据此重塑资源配置与市场结构。",
        },
        {
            "topic": "核心机制",
            "interview_version": f"这篇文章最值得抓住的是{mechanism}这条主线。",
            "written_version": f"文章以{mechanism}下降为核心机制框架解释数字化对经济活动的影响。",
        },
        {
            "topic": "政策含义",
            "interview_version": f"数字经济不能只谈效率，也要谈{policy}这些制度问题。",
            "written_version": f"数字经济研究具有显著制度维度，政策上需兼顾效率提升与{policy}等治理目标。",
        },
    ]


def build_low_priority() -> list[dict[str, str]]:
    return [
        {"label": "具体计量细节", "reason": "对复试短时间准备的直接收益较低，优先级低于总框架和机制逻辑。"},
        {"label": "附录和机构信息", "reason": "不影响对文章核心思想的掌握。"},
        {"label": "长篇参考文献清单", "reason": "适合作为扩展阅读，不适合作为第一轮记忆重点。"},
    ]


def build_review_outline() -> dict[str, list[str]]:
    return {
        "interview_outline": [
            "先交代研究对象与背景。",
            "再概括核心研究问题与机制主线。",
            "然后说明最重要结论与政策含义。",
            "最后补创新点、局限性和延伸方向。",
        ],
        "written_outline": [
            "先背核心概念定义与总框架。",
            "再背机制链条与规范化结论。",
            "然后整理政策背景与高频术语。",
            "最后背可迁移的知识块表达。",
        ],
    }


def build_extra(cost_terms: list[str], policy_topics: list[str], field: str) -> dict[str, Any]:
    mechanism = "、".join(cost_terms) if cost_terms else "关键成本下降"
    policy = "、".join(policy_topics) if policy_topics else "平台治理与制度约束"
    return {
        "key_points": [
            f"{field}研究的关键是把技术变化还原为经济成本变化。",
            "数字化通常不会自动带来单向福利改善，而是伴随显著异质性。",
            "平台规则、组织资本和制度环境会影响数字技术的实际效果。",
        ],
        "mechanisms": [
            f"数字化 -> 信息处理更便宜 -> {mechanism} -> 交易与组织方式变化",
            "技术扩散 -> 市场边界变化 -> 效率与分配结果重构",
        ],
        "policy_implications": [
            f"需要关注{policy}。",
            "需要把效率提升与制度治理放在同一分析框架下。",
        ],
        "limitations": [
            "框架整合强，但不能替代单篇识别型实证研究。",
            "不同场景下机制强弱可能存在明显异质性。",
        ],
    }


def build_english_support(cost_terms: list[str]) -> dict[str, Any]:
    key_terms = [
        {"english": "digital economics", "chinese": "数字经济", "explanation": "研究数字技术如何改变经济活动与资源配置的领域。"},
        {"english": "consumer surplus", "chinese": "消费者剩余", "explanation": "消费者愿付价格与实际支付价格之间的差额。"},
        {"english": "platform governance", "chinese": "平台治理", "explanation": "围绕平台规则、激励和责任分配形成的治理安排。"},
    ]
    for token, chinese in DIGITAL_COST_LABELS:
        if chinese in cost_terms:
            key_terms.append(
                {
                    "english": f"{token} costs",
                    "chinese": chinese,
                    "explanation": f"指与{chinese}相关的资源消耗或约束。",
                }
            )
    return {
        "key_terms": key_terms,
        "oral_sentence_patterns": [
            "This paper explains the topic through changing economic costs rather than through a completely new theory.",
            "The key contribution is to organize the literature around a small number of core mechanisms.",
            "In my view, the paper is useful because it connects digital change to standard economic reasoning.",
        ],
        "written_sentence_patterns": [
            "The paper shows that digitization mainly matters because it changes the structure of economic costs.",
            "The main mechanism can be summarized as lower costs leading to new market and organizational outcomes.",
            "The economic effects of digital technology are heterogeneous and shaped by institutional conditions.",
        ],
    }


def build_full_output(text: str, input_path: Path | None) -> tuple[dict[str, Any], str]:
    cleaned = clean_text(text)
    if len(cleaned) < MIN_TEXT_LENGTH:
        raise UserFacingError(STANDARD_TEXT_PROMPT)

    language, confidence, reason = detect_language(cleaned)
    title = extract_title(cleaned, input_path)
    authors = extract_authors(cleaned, title)
    year = extract_year(cleaned)
    abstract = extract_abstract(cleaned)
    min_abstract_length = 60 if language == "中文文献" else 120
    if len(clean_text(abstract)) < min_abstract_length:
        raise UserFacingError(STANDARD_TEXT_PROMPT)

    abstract_sentences = split_sentences(abstract, language)
    field = determine_field(title, abstract)
    keywords = extract_keywords(cleaned, field)
    cost_terms = detect_cost_terms(cleaned)
    policy_topics = detect_policy_topics(cleaned)
    is_review = "review" in cleaned.lower() or "综述" in cleaned

    paper_info = {
        "title": title,
        "authors": authors,
        "year": year,
        "language": language,
        "field": field,
        "keywords": keywords,
    }
    language_detect_result = {
        "detected_language": language,
        "confidence": confidence,
        "reason": reason,
    }
    one_sentence_summary = build_topic_summary(title, abstract_sentences, language)
    interview_useful = build_interview_useful(
        title,
        abstract,
        abstract_sentences,
        field,
        cost_terms,
        policy_topics,
        is_review,
    )
    written_exam_useful = build_written_exam_useful(
        title,
        field,
        cost_terms,
        policy_topics,
        abstract_sentences,
    )
    review_outline = build_review_outline()
    extra = build_extra(cost_terms, policy_topics, field)
    english_support = build_english_support(cost_terms)

    full = {
        "meta": {"schema_version": "1.0"},
        "paper_info": paper_info,
        "language_detect_result": language_detect_result,
        "one_sentence_summary": one_sentence_summary,
        "interview_useful": interview_useful,
        "written_exam_useful": written_exam_useful,
        "overlap_but_rewritten": build_overlap(cost_terms, policy_topics),
        "low_priority": build_low_priority(),
        "review_outline": review_outline,
        "extra": extra,
        "english_support": english_support,
    }
    return full, slugify(title)


def split_outputs(full: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    interview = {
        "paper_info": full["paper_info"],
        "language_detect_result": full["language_detect_result"],
        "one_sentence_summary": full["one_sentence_summary"],
        "interview_useful": full["interview_useful"],
        "review_outline": {"interview_outline": full["review_outline"]["interview_outline"]},
        "extra": full["extra"],
        "english_support": {
            "key_terms": full["english_support"]["key_terms"],
            "oral_sentence_patterns": full["english_support"]["oral_sentence_patterns"],
        },
    }
    written = {
        "paper_info": full["paper_info"],
        "language_detect_result": full["language_detect_result"],
        "one_sentence_summary": full["one_sentence_summary"],
        "written_exam_useful": full["written_exam_useful"],
        "review_outline": {"written_outline": full["review_outline"]["written_outline"]},
        "extra": full["extra"],
        "english_support": {
            "key_terms": full["english_support"]["key_terms"],
            "written_sentence_patterns": full["english_support"]["written_sentence_patterns"],
        },
    }
    return interview, written


def load_schema(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_against_schema(data: Any, schema: Any, path: str = "$") -> None:
    if isinstance(schema, dict):
        if not isinstance(data, dict):
            raise ValueError(f"{path} should be an object")
        schema_keys = set(schema.keys())
        data_keys = set(data.keys())
        missing = schema_keys - data_keys
        extra = data_keys - schema_keys
        if missing:
            raise ValueError(f"{path} missing keys: {sorted(missing)}")
        if extra:
            raise ValueError(f"{path} has unexpected keys: {sorted(extra)}")
        for key, value in schema.items():
            validate_against_schema(data[key], value, f"{path}.{key}")
        return

    if isinstance(schema, list):
        if not isinstance(data, list):
            raise ValueError(f"{path} should be a list")
        if not schema:
            return
        exemplar = schema[0]
        for index, item in enumerate(data):
            validate_against_schema(item, exemplar, f"{path}[{index}]")
        return

    if isinstance(schema, str):
        if not isinstance(data, str):
            raise ValueError(f"{path} should be a string")
        return
    if isinstance(schema, (int, float)):
        if not isinstance(data, (int, float)):
            raise ValueError(f"{path} should be a number")
        return
    if isinstance(schema, bool):
        if not isinstance(data, bool):
            raise ValueError(f"{path} should be a boolean")
        return
    if schema is None and data is not None:
        raise ValueError(f"{path} should be null")


def write_json(path: Path, data: dict[str, Any], schema_path: Path) -> None:
    schema = load_schema(schema_path)
    validate_against_schema(data, schema)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    validate_against_schema(reloaded, schema)


def main() -> int:
    args = parse_args()
    input_path = args.input_file.resolve() if args.input_file else None
    try:
        raw_text = args.input_text if args.input_text is not None else read_text_input(input_path)
        full, slug = build_full_output(raw_text, input_path)
        interview, written = split_outputs(full)

        output_dir = Path.cwd() / "output" / "economics-retest-paper-splitter" / slug
        output_dir.mkdir(parents=True, exist_ok=True)

        full_path = output_dir / "full.json"
        interview_path = output_dir / "interview.json"
        written_path = output_dir / "written_exam.json"

        write_json(full_path, full, FULL_SCHEMA_PATH)
        write_json(interview_path, interview, INTERVIEW_SCHEMA_PATH)
        write_json(written_path, written, WRITTEN_SCHEMA_PATH)

        print(full_path)
        print(interview_path)
        print(written_path)
        return 0
    except UserFacingError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
