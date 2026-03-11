#!/usr/bin/env python3
"""Generate stable retest JSON outputs from a paper text or PDF."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pypdf import PdfReader


STANDARD_TEXT_PROMPT = "请补充摘要或正文内容，以便继续拆解。"
STANDARD_LANGUAGE_PROMPT = "请确认这是一篇中文文献、英文文献，还是中英混合文献？"

EXIT_INFO_INSUFFICIENT = 1
EXIT_LANGUAGE_UNKNOWN = 2
EXIT_PDF_EXTRACTION_FAILED = 3
EXIT_SCHEMA_INVALID = 4

MIN_TEXT_LENGTH = 180
MIN_PDF_TEXT_LENGTH = 500
MIN_NON_EMPTY_PAGE_RATIO = 0.2

ROOT = Path(__file__).resolve().parents[1]
FULL_SCHEMA_PATH = ROOT / "references" / "output-schema.json"
INTERVIEW_SCHEMA_PATH = ROOT / "references" / "interview-output-schema.json"
WRITTEN_SCHEMA_PATH = ROOT / "references" / "written-output-schema.json"

ALLOWED_LANGUAGES = {"中文文献", "英文文献", "中英混合文献"}
OUTPUT_FILENAMES = ("full.json", "interview.json", "written_exam.json")
EXCEL_FILENAME = "retest_pack.xlsx"

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
        "network neutrality",
        "artificial intelligence",
        "人工智能",
        "数字",
        "平台",
        "数据",
        "算法",
        "互联网",
        "隐私",
        "数据要素",
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
        "price dispersion",
        "价格",
        "消费者",
        "企业",
        "市场",
        "竞争",
        "微观",
    ],
}

PAPER_TYPE_KEYWORDS = {
    "review": [
        "review",
        "survey",
        "literature",
        "journal of economic literature",
        "综述",
        "文献述评",
        "文献综述",
        "研究评述",
    ],
    "empirical": [
        "panel data",
        "evidence",
        "empirical",
        "difference-in-differences",
        "did",
        "regression",
        "data",
        "sample",
        "based on",
        "基于",
        "实证",
        "面板数据",
        "样本",
        "回归",
        "异质性",
    ],
    "theoretical": [
        "model",
        "theory",
        "proposition",
        "assumption",
        "framework",
        "equilibrium",
        "模型",
        "理论",
        "命题",
        "假设",
        "均衡",
    ],
    "policy": [
        "policy",
        "regulation",
        "governance",
        "privacy",
        "copyright",
        "policy implications",
        "政策",
        "监管",
        "治理",
        "制度",
        "隐私",
        "版权",
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
    "governance": "平台治理",
    "regulation": "监管规则",
    "data property": "数据产权",
}

EXPLICIT_TITLE_PATTERNS = [
    r"(?:^|\n)标题[:：]\s*(.+)",
    r"(?:^|\n)Title[:：]\s*(.+)",
]
EXPLICIT_AUTHOR_PATTERNS = [
    r"(?:^|\n)作者[:：]\s*(.+)",
    r"(?:^|\n)Authors?[:：]\s*(.+)",
]
EXPLICIT_YEAR_PATTERNS = [
    r"(?:^|\n)(?:年份|Year)[:：]\s*((?:19|20)\d{2})",
    r"\b((?:19|20)\d{2})\b",
]
EXPLICIT_KEYWORDS_PATTERNS = [
    r"(?:Keywords?|关键词)[:：]\s*(.+)",
]

ENGLISH_SECTION_HEADINGS = {
    "abstract": {"abstract"},
    "keywords": {"keywords", "jel", "jel classification"},
    "introduction": {"introduction"},
    "conclusion": {"conclusion", "conclusions", "concluding remarks", "concluding comments"},
    "references": {"references", "bibliography"},
}
CHINESE_SECTION_HEADINGS = {
    "abstract": {"摘要"},
    "keywords": {"关键词"},
    "introduction": {"引言", "导论", "绪论", "前言"},
    "conclusion": {"结论", "研究结论", "结语", "总结"},
    "references": {"参考文献"},
}


@dataclass
class UserFacingError(Exception):
    """Message that should be shown directly to the user."""

    message: str
    code: int

    def __str__(self) -> str:
        return self.message


@dataclass
class SourceData:
    input_type: str
    raw_text: str
    source_path: str
    page_count: int | None = None
    non_empty_page_ratio: float | None = None


@dataclass
class PaperMetadata:
    title: str
    authors: list[str]
    year: str
    language: str
    language_confidence: str
    language_reason: str
    field: str
    keywords: list[str]
    paper_type: str


@dataclass
class PaperSections:
    abstract: str
    abstract_sentences: list[str]
    conclusion: str
    conclusion_sentences: list[str]
    introduction: str
    intro_sentences: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate retest JSON outputs from a paper.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-file", type=Path, help="Path to a PDF, TXT, or MD file.")
    group.add_argument("--input-text", help="Inline text content.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output root directory. Defaults to ./output/economics-retest-paper-splitter",
    )
    parser.add_argument("--slug", help="Override the automatically generated paper slug.")
    parser.add_argument(
        "--language",
        choices=sorted(ALLOWED_LANGUAGES),
        help="Force the paper language instead of auto-detecting it.",
    )
    parser.add_argument(
        "--stdout-json",
        action="store_true",
        help="Print full.json content to stdout instead of writing files.",
    )
    return parser.parse_args()


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_source(input_file: Path | None, input_text: str | None) -> SourceData:
    if input_text is not None:
        return SourceData(input_type="text", raw_text=clean_text(input_text), source_path="<inline-text>")
    assert input_file is not None
    suffix = input_file.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_source(input_file)
    text = input_file.read_text(encoding="utf-8")
    return SourceData(input_type=suffix.lstrip(".") or "text", raw_text=clean_text(text), source_path=str(input_file.resolve()))


def extract_pdf_source(path: Path) -> SourceData:
    reader = PdfReader(str(path))
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    joined = clean_text("\n".join(text for text in page_texts if text))
    non_empty_pages = sum(1 for text in page_texts if len(text) >= 80)
    ratio = non_empty_pages / max(1, len(page_texts))
    if len(joined) < MIN_PDF_TEXT_LENGTH or ratio < MIN_NON_EMPTY_PAGE_RATIO:
        raise UserFacingError(STANDARD_TEXT_PROMPT, EXIT_PDF_EXTRACTION_FAILED)
    return SourceData(
        input_type="pdf",
        raw_text=joined,
        source_path=str(path.resolve()),
        page_count=len(page_texts),
        non_empty_page_ratio=ratio,
    )


def normalized_heading(line: str) -> str:
    line = clean_text(line).strip(":：")
    line = re.sub(r"^[\d一二三四五六七八九十IVXivx.()（）\s-]+", "", line)
    return line.lower()


def is_heading_line(line: str, language: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    norm = normalized_heading(stripped)
    english_heads = set().union(*ENGLISH_SECTION_HEADINGS.values())
    chinese_heads = set().union(*CHINESE_SECTION_HEADINGS.values())
    if norm in english_heads or stripped in chinese_heads:
        return True
    if language == "中文文献":
        return bool(re.fullmatch(r"[一二三四五六七八九十]+[、.．].{1,25}", stripped))
    return bool(re.fullmatch(r"\d+(?:\.\d+)*\s+[A-Z].{0,80}", stripped))


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()]


def detect_language(text: str, title_hint: str = "", abstract_hint: str = "", forced: str | None = None) -> tuple[str, str, str]:
    if forced:
        return forced, "forced", "使用命令行参数强制指定文献语言。"

    def score(chunk: str) -> tuple[int, int]:
        chinese = len(re.findall(r"[\u4e00-\u9fff]", chunk))
        latin = len(re.findall(r"[A-Za-z]{2,}", chunk))
        return chinese, latin

    priority_text = clean_text("\n".join(part for part in [title_hint, abstract_hint] if part))
    body_sample = clean_text(text[:12000])

    priority_chinese, priority_latin = score(priority_text)
    body_chinese, body_latin = score(body_sample)

    if priority_text:
        if priority_chinese >= 8 and priority_latin >= 12:
            return "中英混合文献", "medium", "标题和摘要同时包含较多中文与英文内容。"
        if priority_chinese >= 12 and priority_latin < 35:
            return "中文文献", "high", "标题与摘要主体以中文为主。"
        if priority_latin >= 20 and priority_chinese < 8:
            return "英文文献", "high", "标题与摘要主体以英文连续文本为主。"

    if body_chinese >= 25 and body_latin >= 25:
        return "中英混合文献", "medium", "正文抽样同时包含较多中文和英文内容。"
    if body_chinese >= 70 and body_latin < 120:
        return "中文文献", "medium", "正文抽样以中文内容为主。"
    if body_latin >= 70 and body_chinese < 30:
        return "英文文献", "medium", "正文抽样以英文内容为主。"
    raise UserFacingError(STANDARD_LANGUAGE_PROMPT, EXIT_LANGUAGE_UNKNOWN)


def find_labeled_value(text: str, patterns: list[str], flags: int = re.IGNORECASE) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_title(text: str, input_path: Path | None) -> tuple[str, bool]:
    explicit = find_labeled_value(text, EXPLICIT_TITLE_PATTERNS)
    if explicit:
        return explicit, False

    lines = [line for line in split_lines(text) if line]
    skip_patterns = [
        r"working paper",
        r"series",
        r"http",
        r"journal",
        r"nber",
        r"massachusetts avenue",
        r"abstract",
        r"jel",
        r"keywords?",
        r"references",
        r"摘要",
        r"关键词",
        r"引言",
        r"结论",
        r"参考文献",
    ]
    for line in lines[:50]:
        lowered = line.lower()
        if len(line) < 4 or len(line) > 180:
            continue
        if any(re.search(pattern, lowered) for pattern in skip_patterns):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        if re.search(r"[A-Za-z\u4e00-\u9fff]", line):
            return normalize_title_case(line), False

    if input_path is not None:
        return normalize_title_case(input_path.stem.replace("-", " ")), True
    return "Untitled Paper", True


def normalize_title_case(title: str) -> str:
    words = title.split()
    if not words:
        return title
    if all(word.isupper() for word in words if re.search(r"[A-Z]", word)):
        return " ".join(word.capitalize() for word in words)
    return title


def extract_authors(text: str, title: str) -> list[str]:
    labeled = find_labeled_value(text, EXPLICIT_AUTHOR_PATTERNS)
    if labeled:
        parts = [part.strip() for part in re.split(r"[,;；，、]| and ", labeled) if part.strip()]
        return parts[:6]

    lines = [line for line in split_lines(text) if line]
    title_candidates = {title, title.replace(" ", "")}
    name_pattern = re.compile(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}$")
    for index, line in enumerate(lines[:60]):
        if line in title_candidates:
            authors: list[str] = []
            for candidate_line in lines[index + 1 : index + 8]:
                candidate = candidate_line.replace("∗", "").replace("†", "").strip()
                if name_pattern.fullmatch(candidate):
                    authors.append(candidate)
            if authors:
                return authors[:6]
    return []


def extract_year(text: str) -> str:
    labeled = find_labeled_value(text, EXPLICIT_YEAR_PATTERNS)
    if labeled:
        return labeled[:4]
    return ""


def extract_section_block(text: str, start_heads: set[str], stop_heads: set[str], language: str) -> str:
    lines = split_lines(text)
    start_index: int | None = None
    for index, line in enumerate(lines):
        if not line:
            continue
        norm = normalized_heading(line)
        if norm in start_heads or line in start_heads:
            start_index = index + 1
            break
    if start_index is None:
        return ""

    collected: list[str] = []
    for line in lines[start_index:]:
        if not line:
            if collected and collected[-1]:
                collected.append("")
            continue
        norm = normalized_heading(line)
        if norm in stop_heads or line in stop_heads:
            break
        if collected and is_heading_line(line, language) and len(" ".join(collected)) > 120:
            break
        collected.append(line)
    return clean_text("\n".join(collected))


def extract_abstract(text: str, language: str) -> str:
    if language == "中文文献":
        abstract = extract_section_block(
            text,
            CHINESE_SECTION_HEADINGS["abstract"],
            CHINESE_SECTION_HEADINGS["keywords"] | CHINESE_SECTION_HEADINGS["introduction"],
            language,
        )
        if abstract:
            return abstract
        fallback = re.search(r"(?:摘要)[:：]?\s*(.+?)(?:\n\s*关键词|\n\s*引言|\Z)", text, re.DOTALL)
        if fallback:
            return clean_text(fallback.group(1))
    else:
        abstract = extract_section_block(
            text,
            ENGLISH_SECTION_HEADINGS["abstract"],
            ENGLISH_SECTION_HEADINGS["keywords"] | ENGLISH_SECTION_HEADINGS["introduction"],
            "英文文献",
        )
        if abstract:
            return abstract
        fallback = re.search(
            r"(?:ABSTRACT|Abstract)[:：]?\s*(.+?)(?:\n\s*Keywords|\n\s*JEL|\n\s*(?:1\s+Introduction|Introduction)|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if fallback:
            return clean_text(fallback.group(1))

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    if paragraphs:
        return clean_text(paragraphs[0])[:2000]
    return ""


def extract_conclusion(text: str, language: str) -> str:
    if language == "中文文献":
        conclusion = extract_section_block(
            text,
            CHINESE_SECTION_HEADINGS["conclusion"],
            CHINESE_SECTION_HEADINGS["references"],
            language,
        )
        if conclusion:
            return conclusion[:2500]
        fallback = re.search(r"(?:结论|结语)[:：]?\s*(.+?)(?:\n\s*参考文献|\Z)", text, re.DOTALL)
        if fallback:
            return clean_text(fallback.group(1))[:2500]
    else:
        conclusion = extract_section_block(
            text,
            ENGLISH_SECTION_HEADINGS["conclusion"],
            ENGLISH_SECTION_HEADINGS["references"],
            "英文文献",
        )
        if conclusion:
            return conclusion[:2500]
        fallback = re.search(
            r"(?:Conclusion|Conclusions|Concluding Remarks)[:：]?\s*(.+?)(?:\n\s*References|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if fallback:
            return clean_text(fallback.group(1))[:2500]
    return ""


def extract_introduction(text: str, language: str) -> str:
    if language == "中文文献":
        intro = extract_section_block(
            text,
            CHINESE_SECTION_HEADINGS["introduction"],
            CHINESE_SECTION_HEADINGS["conclusion"] | CHINESE_SECTION_HEADINGS["references"],
            language,
        )
        return intro[:2000]
    intro = extract_section_block(
        text,
        ENGLISH_SECTION_HEADINGS["introduction"],
        ENGLISH_SECTION_HEADINGS["conclusion"] | ENGLISH_SECTION_HEADINGS["references"],
        "英文文献",
    )
    return intro[:2000]


def split_sentences(text: str, language: str) -> list[str]:
    if not text:
        return []
    if language == "中文文献":
        parts = re.split(r"(?<=[。！？；])", text)
    else:
        parts = re.split(r"(?<=[.!?])\s+", text)
    sentences = [clean_text(part) for part in parts if clean_text(part)]
    return sentences


def determine_field(title: str, abstract: str, conclusion: str) -> str:
    haystack = f"{title}\n{abstract}\n{conclusion}".lower()
    scores = {}
    for field, keywords in FIELD_KEYWORDS.items():
        scores[field] = sum(1 for keyword in keywords if keyword in haystack)
    best_field = max(scores, key=scores.get)
    return best_field if scores[best_field] > 0 else "相关经济学交叉方向"


def extract_keywords(title: str, abstract: str, text: str, field: str, language: str) -> list[str]:
    explicit = find_labeled_value(text, EXPLICIT_KEYWORDS_PATTERNS)
    if explicit:
        parts = [part.strip() for part in re.split(r"[,;；，、]", explicit) if part.strip()]
        if parts:
            return parts[:8]

    haystack = f"{title}\n{abstract}".lower()
    if language == "中文文献":
        title_terms = [
            term.strip()
            for term in re.split(r"[、，；：:：\-—\s与和]+", re.sub(r"[^\u4e00-\u9fffA-Za-z0-9、，；：:：\-—\s与和]", " ", title))
            if len(term.strip()) >= 2
        ]
        phrase_candidates = [
            "数据要素流通",
            "平台治理",
            "区域创新",
            "创新绩效",
            "数字基础设施",
            "隐私保护",
            "知识溢出",
            "信息不对称",
            "资源配置",
            "政府治理能力",
            "市场化水平",
        ]
        found_cn: list[str] = []
        for candidate in title_terms + phrase_candidates:
            if candidate in f"{title}\n{abstract}" and candidate not in found_cn:
                found_cn.append(candidate)
        if found_cn:
            return found_cn[:8]

    found: list[str] = []
    for keyword in KEYWORD_FALLBACKS[field]:
        if keyword.lower() in haystack and keyword not in found:
            found.append(keyword)
    if found:
        return found[:8]
    return KEYWORD_FALLBACKS[field][:5]


def slugify(title: str) -> tuple[str, bool]:
    title = title.lower()
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", title)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if slug:
        return slug, False
    return "untitled-paper", True


def detect_cost_terms(text: str) -> list[str]:
    lowered = text.lower()
    labels = [label for token, label in DIGITAL_COST_LABELS if token in lowered]
    deduped: list[str] = []
    for label in labels:
        if label not in deduped:
            deduped.append(label)
    return deduped


def detect_policy_topics(text: str) -> list[str]:
    lowered = text.lower()
    topics = [label for token, label in POLICY_TERMS.items() if token in lowered]
    deduped: list[str] = []
    for topic in topics:
        if topic not in deduped:
            deduped.append(topic)
    return deduped[:6]


def detect_paper_type(title: str, abstract: str, conclusion: str, text: str) -> str:
    haystack = f"{title}\n{abstract}\n{conclusion}\n{text[:5000]}".lower()
    scores = {paper_type: 0 for paper_type in PAPER_TYPE_KEYWORDS}
    for paper_type, keywords in PAPER_TYPE_KEYWORDS.items():
        scores[paper_type] = sum(1 for keyword in keywords if keyword in haystack)

    if scores["review"] > 0:
        return "review"
    if scores["empirical"] >= 2:
        return "empirical"
    if scores["theoretical"] >= 2:
        return "theoretical"
    if scores["policy"] >= 2:
        return "policy"

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "empirical"


def build_topic_summary(title: str, metadata: PaperMetadata, sections: PaperSections, cost_terms: list[str]) -> str:
    if metadata.paper_type == "review":
        mechanism = "、".join(cost_terms) if cost_terms else "关键成本下降"
        return f"本文以综述方式梳理《{title}》所涉及的数字经济研究，并将核心变化归结为{mechanism}等成本结构重塑。"
    if metadata.paper_type == "empirical":
        lead = sections.abstract_sentences[0] if sections.abstract_sentences else "文章基于数据检验数字化变量对经济结果的影响。"
        return f"本文是一篇实证研究，核心关注点是：{lead}"
    if metadata.paper_type == "theoretical":
        return f"本文是一篇理论导向研究，重点讨论《{title}》所涉及机制如何在不同假设下影响经济结果。"
    return f"本文围绕《{title}》展开政策与治理分析，重点讨论数字化情境下规则设计与经济结果之间的关系。"


def chinese_anchor_from_english(english_sentence: str, fallback: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", english_sentence):
        return english_sentence
    lowered = english_sentence.lower()
    if "search" in lowered:
        return "文章强调搜索成本下降会改变信息比较、匹配效率和价格形成。"
    if "privacy" in lowered:
        return "文章指出隐私与数据使用边界会直接影响数字市场的运行规则。"
    if "productivity" in lowered:
        return "文章强调数字技术对生产率的影响存在明显异质性，并取决于组织能力。"
    return fallback


def pick_background(metadata: PaperMetadata, sections: PaperSections) -> str:
    if metadata.language == "中文文献" and sections.abstract_sentences:
        return sections.abstract_sentences[0]
    if metadata.paper_type == "review":
        return "文章的出发点是解释数字技术为什么会系统性改变经济活动，而不是把数字经济当成完全独立的新理论。"
    if metadata.paper_type == "empirical":
        return "文章的出发点是检验数字化变量是否真实影响了某类经济结果，以及这种影响通过哪些机制发生。"
    if metadata.paper_type == "theoretical":
        return "文章的出发点是通过模型化分析澄清数字化情境下的关键机制和边界条件。"
    return "文章的出发点是讨论数字化带来的效率提升与制度治理之间如何形成新的政策张力。"


def pick_conclusion(metadata: PaperMetadata, sections: PaperSections) -> str:
    if metadata.language == "中文文献" and sections.conclusion_sentences:
        return sections.conclusion_sentences[0]
    if metadata.language == "英文文献" and sections.conclusion_sentences:
        return chinese_anchor_from_english(
            sections.conclusion_sentences[0],
            "文章最终强调数字化会重塑经济成本结构，但真实效应取决于组织、制度与平台规则。",
        )
    if metadata.paper_type == "review":
        return "文章最终强调，数字经济的很多现象仍可用标准经济学解释，但必须把注意力放在成本结构变化上。"
    if metadata.paper_type == "empirical":
        return "文章最终强调，数字化变量对经济结果的影响真实存在，但强度和方向受机制条件与样本异质性影响。"
    if metadata.paper_type == "theoretical":
        return "文章最终强调，理论结论依赖关键假设设定，因此需要注意模型边界。"
    return "文章最终强调，数字经济政策不能只看效率提升，还要兼顾制度约束与治理后果。"


def pick_method_phrase(metadata: PaperMetadata, sections: PaperSections) -> str:
    abstract = sections.abstract.lower()
    if metadata.paper_type == "review":
        return "通过系统梳理相关研究构建统一分析框架"
    if metadata.paper_type == "empirical":
        if any(token in abstract for token in ["panel", "dataset", "sample", "基于", "面板数据", "样本"]):
            return "基于样本数据开展实证识别"
        return "通过经验数据检验关键变量之间的关系"
    if metadata.paper_type == "theoretical":
        return "通过模型设定与机制推演展开分析"
    return "围绕政策规则与制度安排进行分析评估"


def build_interview_useful(metadata: PaperMetadata, sections: PaperSections, cost_terms: list[str], policy_topics: list[str]) -> list[dict[str, Any]]:
    mechanism_line = "、".join(cost_terms) if cost_terms else "关键成本变化"
    policy_line = "、".join(policy_topics) if policy_topics else "平台治理、隐私保护与制度约束"
    background = pick_background(metadata, sections)
    conclusion = pick_conclusion(metadata, sections)
    method_phrase = pick_method_phrase(metadata, sections)

    common = [
        {
            "label": "研究背景",
            "core_content": background,
            "reason_for_interview": "适合开场交代文献切入点，帮助快速建立主线。",
            "typical_questions": ["这篇文章为什么值得研究？", "作者关注的现实背景是什么？"],
            "oral_answer_sample": f"我理解这篇文章的背景是：{background}",
        },
        {
            "label": "研究问题",
            "core_content": f"本文核心要回答的是：在{metadata.field}语境下，数字化条件变化如何影响经济行为、组织方式与制度安排。",
            "reason_for_interview": "适合把文章主线压缩成一句清晰表述。",
            "typical_questions": ["这篇文章到底在研究什么？", "如果一句话概括这篇文献，你会怎么说？"],
            "oral_answer_sample": "如果一句话概括，我会说作者是在讨论数字化条件变化如何重塑经济运行逻辑。",
        },
    ]

    if metadata.paper_type == "review":
        type_specific = [
            {
                "label": "理论脉络",
                "core_content": f"文章把分散的数字经济研究归到同一框架下，主线是{mechanism_line}下降如何改变市场、平台和福利结果。",
                "reason_for_interview": "综述文献最适合从理论脉络切入，能体现你的结构化理解。",
                "typical_questions": ["这篇综述是怎么组织文献的？", "它的统一框架是什么？"],
                "oral_answer_sample": f"我认为这篇文章最有价值的地方，是把很多零散研究统一到{mechanism_line}变化这条主线上。",
            },
            {
                "label": "文献贡献",
                "core_content": "文章的贡献不在于提出一个全新理论，而在于提供了一个可迁移的解释框架，让不同领域的数字经济研究可以放进同一套逻辑中理解。",
                "reason_for_interview": "适合回答“贡献是什么”这类评价问题。",
                "typical_questions": ["这篇文章最大的贡献是什么？", "为什么它具有代表性？"],
                "oral_answer_sample": "它最大的贡献不是提出新模型，而是把数字经济研究组织成一套可复用的分析框架。",
            },
        ]
    elif metadata.paper_type == "empirical":
        type_specific = [
            {
                "label": "识别策略",
                "core_content": f"文章主要是{method_phrase}，重点在于说明数字化变量与结果变量之间的关系不是简单相关，而是尽量靠近因果识别。",
                "reason_for_interview": "实证论文面试经常会追问“你怎么理解它的识别思路”。",
                "typical_questions": ["这篇文章是怎么做实证识别的？", "为什么作者的结论不只是相关性？"],
                "oral_answer_sample": f"从实证角度看，这篇文章不是只描述现象，而是希望通过{method_phrase}去识别更可信的因果关系。",
            },
            {
                "label": "异质性与机制",
                "core_content": f"文章不仅讨论总体效应，还会继续问这种影响在不同样本、不同条件下是否有差异，并通过{mechanism_line}等路径解释这种差异从何而来。",
                "reason_for_interview": "适合导师进一步追问机制检验和异质性分析。",
                "typical_questions": ["文章有没有做异质性分析？", "机制检验告诉了我们什么？"],
                "oral_answer_sample": "我觉得这篇文章比较完整的地方在于，它不仅给出平均效应，还会继续追问在哪些条件下效果更强，以及这种差异背后的机制是什么。",
            },
        ]
    elif metadata.paper_type == "theoretical":
        type_specific = [
            {
                "label": "模型假设",
                "core_content": "文章的核心在于设定关键假设，再观察这些假设变化如何影响均衡结果，因此理解它时最重要的是抓住假设和机制之间的对应关系。",
                "reason_for_interview": "理论论文面试最容易被追问模型假设和边界。",
                "typical_questions": ["这篇文章最关键的假设是什么？", "如果放松假设，结论会不会变？"],
                "oral_answer_sample": "我理解理论论文时会先抓假设，因为它的结论本质上是由假设决定的。",
            },
            {
                "label": "理论边界",
                "core_content": "文章的理论价值在于澄清机制，但它的外部适用性取决于现实世界是否满足这些核心假设。",
                "reason_for_interview": "适合回答理论论文的局限性与适用范围。",
                "typical_questions": ["这个理论结果在现实里一定成立吗？", "它的边界在哪里？"],
                "oral_answer_sample": "我会把它理解成一种机制澄清工具，而不是对所有现实场景都自动成立的结论。",
            },
        ]
    else:
        type_specific = [
            {
                "label": "制度背景",
                "core_content": f"文章的重点不只是市场行为本身，而是数字化条件下的制度环境如何约束或放大经济结果，特别是{policy_line}等问题。",
                "reason_for_interview": "政策型文献适合从制度背景和治理目标切入。",
                "typical_questions": ["这篇文章关注的政策问题是什么？", "为什么数字经济研究会落到治理问题上？"],
                "oral_answer_sample": f"我觉得这篇文章最核心的现实意义，是把数字经济放到{policy_line}这些制度问题下重新理解。",
            },
            {
                "label": "政策评价",
                "core_content": "文章强调，政策设计不能只追求效率提升，还要兼顾实施约束、治理成本和分配结果。",
                "reason_for_interview": "适合对接现实政策讨论。",
                "typical_questions": ["作者对政策设计有什么判断？", "它的政策含义是什么？"],
                "oral_answer_sample": "我理解作者不是只强调效率，而是提醒我们数字政策往往带有明显的治理权衡。",
            },
        ]

    tail = [
        {
            "label": "核心结论",
            "core_content": conclusion,
            "reason_for_interview": "适合回答“文章最重要的发现是什么”。",
            "typical_questions": ["作者最后得出了什么判断？", "文章的总体结论是什么？"],
            "oral_answer_sample": f"我觉得文章最后最重要的结论是：{conclusion}",
        },
        {
            "label": "政策启示",
            "core_content": f"从政策层面看，文章提示需要重点关注{policy_line}等问题，因为数字技术带来效率提升的同时，也会放大治理与规则设计的重要性。",
            "reason_for_interview": "适合把文献与现实政策问题连接起来。",
            "typical_questions": ["这篇文章有哪些政策含义？", "为什么数字经济研究会走向制度治理问题？"],
            "oral_answer_sample": f"我觉得这篇文章一个很强的现实启示是，数字经济不能只看效率，还要看{policy_line}这些制度问题。",
        },
        {
            "label": "局限性",
            "core_content": (
                "作为综述，它更强于框架整合，弱于对单个机制的严格识别。"
                if metadata.paper_type == "review"
                else "文章虽然给出了明确结论，但对机制边界、外部有效性或制度条件的讨论仍有继续展开的空间。"
            ),
            "reason_for_interview": "适合回答文献评价题，避免只说优点。",
            "typical_questions": ["这篇文章有什么不足？", "你觉得它还有哪些没有展开的地方？"],
            "oral_answer_sample": "如果从文献评价角度看，我会说它的强项很明确，但仍然有一些边界条件和外部适用性问题值得继续讨论。",
        },
        {
            "label": "延伸研究方向",
            "core_content": "后续可以继续追问新技术条件下是否出现新的机制、同一机制在不同制度环境中为何会有不同表现，以及现实治理规则如何影响数字化效应的最终落地。",
            "reason_for_interview": "适合回答“如果继续研究你会怎么做”。",
            "typical_questions": ["如果往下做研究，你会怎么延伸？", "这篇文章对今天的研究还有哪些启发？"],
            "oral_answer_sample": "如果往后延伸，我会继续问哪些条件会改变机制强弱，以及现实治理规则为什么会让不同地区出现不同结果。",
        },
    ]
    return common + type_specific + tail


def build_written_exam_useful(metadata: PaperMetadata, sections: PaperSections, cost_terms: list[str], policy_topics: list[str]) -> list[dict[str, Any]]:
    mechanism_line = "、".join(cost_terms) if cost_terms else "搜索成本、交易成本与信息不对称成本"
    policy_line = "、".join(policy_topics) if policy_topics else "平台治理、隐私保护与制度监管"
    if metadata.paper_type == "review":
        return [
            {
                "label": "核心概念定义",
                "core_content": "数字经济研究的核心不在于完全创造新理论，而在于分析数字化如何通过改变关键经济成本重塑经济活动。",
                "reason_for_written_exam": "适合名词解释和总括性简答题。",
                "question_types": ["名词解释", "简答题"],
                "exam_expression": "所谓数字经济，本质上是数字技术改变信息处理方式并进一步重塑关键经济成本结构的过程。",
            },
            {
                "label": "理论脉络",
                "core_content": f"文章以{mechanism_line}为主线整合文献，说明搜索理论、价格理论、声誉理论与组织理论如何共同解释数字化现象。",
                "reason_for_written_exam": "适合综述题和理论来源题。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": f"从理论脉络看，文章并未脱离传统经济学，而是在既有理论框架下，围绕{mechanism_line}等成本变化重构数字经济解释体系。",
            },
            {
                "label": "理论框架",
                "core_content": f"全文的分析框架可概括为“数字化 -> 成本下降 -> 市场与组织方式变化 -> 福利与治理结果变化”，其中重点成本包括{mechanism_line}。",
                "reason_for_written_exam": "适合论述题搭建总分结构。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": "文章构建了一个基于成本变化的统一框架，用以解释数字化对市场、平台、企业和消费者的系统性影响。",
            },
            {
                "label": "规范化结论表述",
                "core_content": "数字经济的关键不在于技术标签本身，而在于技术通过成本结构重塑改变了既有经济机制。",
                "reason_for_written_exam": "适合作为综述类题目结尾总结。",
                "question_types": ["论述题"],
                "exam_expression": "总体而言，数字经济的理论价值在于将分散现象统一还原为成本结构变化所引致的市场与组织重构。",
            },
            {
                "label": "政策背景",
                "core_content": f"文章涉及的政策背景主要包括{policy_line}，反映数字经济研究天然带有制度与治理维度。",
                "reason_for_written_exam": "适合联系制度背景作答。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": f"在政策层面，数字经济并非单纯技术扩散问题，还涉及{policy_line}等制度安排。",
            },
            {
                "label": "高频术语",
                "core_content": "digital economics, search costs, replication costs, transportation costs, tracking costs, verification costs, platform governance, consumer surplus",
                "reason_for_written_exam": "适合术语积累。",
                "question_types": ["名词解释", "简答题"],
                "exam_expression": "作答时可围绕‘成本下降—市场重构—治理回应’这一主线，并结合高频术语提升表达规范性。",
            },
            {
                "label": "可背诵知识块",
                "core_content": "数字经济的核心逻辑可以概括为：信息数字化导致关键成本下降，关键成本下降导致交易与组织方式变化，进而影响效率、福利与治理结果。",
                "reason_for_written_exam": "适合直接背诵。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": "数字经济的本质是成本结构重塑，其影响通过市场、组织与制度三重渠道展开。",
            },
        ]

    if metadata.paper_type == "empirical":
        return [
            {
                "label": "核心概念定义",
                "core_content": "本文属于数字经济实证研究，重点检验数字化变量对具体经济结果的影响及其作用机制。",
                "reason_for_written_exam": "适合简答题开头。",
                "question_types": ["简答题"],
                "exam_expression": "从研究类型看，数字经济实证研究的重点在于识别数字化变量如何影响经济绩效，并解释其作用路径。",
            },
            {
                "label": "理论框架",
                "core_content": f"文章遵循“数字化变量 -> {mechanism_line}变化 -> 结果变量变化”的实证逻辑，并在此基础上讨论异质性与机制检验。",
                "reason_for_written_exam": "适合实证论文答题结构。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": f"文章的实证框架是：数字化因素通过影响{mechanism_line}等中介机制，进而改变经济结果，并表现出显著的异质性。",
            },
            {
                "label": "机制链条",
                "core_content": f"数字化 -> {mechanism_line}下降 -> 资源配置与行为激励变化 -> 结果变量变化。",
                "reason_for_written_exam": "适合机制展开题。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": f"从作用机制看，数字化通过降低{mechanism_line}，改变资源配置效率与行为激励，并最终影响目标经济变量。",
            },
            {
                "label": "规范化结论表述",
                "core_content": "实证研究通常表明数字化效应真实存在，但其方向和强度依赖制度条件、组织能力和样本异质性。",
                "reason_for_written_exam": "适合作为实证总结。",
                "question_types": ["论述题"],
                "exam_expression": "总体而言，数字经济的实证效应并非线性一致，而是受制度环境、组织资本和样本异质性共同影响。",
            },
            {
                "label": "政策背景",
                "core_content": f"文章的政策背景主要体现在{policy_line}，说明实证结论需要放回制度环境中解释。",
                "reason_for_written_exam": "适合联系现实作答。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": f"在政策层面，数字经济实证结论的成立通常依赖于{policy_line}等制度条件。",
            },
            {
                "label": "高频术语",
                "core_content": "empirical evidence, panel data, heterogeneity, mechanism test, digitalization, platform governance, privacy",
                "reason_for_written_exam": "适合术语积累。",
                "question_types": ["名词解释", "简答题"],
                "exam_expression": "作答时可突出‘实证识别—机制检验—异质性分析’这一逻辑链条。",
            },
            {
                "label": "可背诵知识块",
                "core_content": "数字经济实证研究的基本思路是：先识别数字化变量的总体效应，再解释其通过哪些机制发挥作用，最后比较不同条件下的异质性表现。",
                "reason_for_written_exam": "适合迁移到其他实证论文。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": "数字经济实证研究通常围绕总体效应、机制检验和异质性分析三个层次展开。",
            },
        ]

    if metadata.paper_type == "theoretical":
        return [
            {
                "label": "核心概念定义",
                "core_content": "本文属于理论导向研究，核心任务是通过模型假设和逻辑推演解释数字化情境下的经济机制。",
                "reason_for_written_exam": "适合理论型文献概括。",
                "question_types": ["简答题"],
                "exam_expression": "理论型数字经济文献的重点在于通过假设设定和机制推导解释数字化条件下的行为结果。",
            },
            {
                "label": "理论框架",
                "core_content": "文章围绕关键假设、机制链条和均衡结果构建理论框架，并以此说明数字化如何改变传统经济结论。",
                "reason_for_written_exam": "适合模型框架题。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": "理论分析通常遵循‘假设设定—机制推演—均衡结果—边界条件’的结构。",
            },
            {
                "label": "机制链条",
                "core_content": f"模型设定 -> {mechanism_line}变化 -> 激励结构改变 -> 行为与均衡结果变化。",
                "reason_for_written_exam": "适合机制推演题。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": f"从理论机制看，数字化通过改变{mechanism_line}及相关激励结构，进而影响行为选择与均衡结果。",
            },
            {
                "label": "规范化结论表述",
                "core_content": "理论结论依赖假设条件成立，因此其价值在于澄清机制而非直接替代经验事实。",
                "reason_for_written_exam": "适合作为理论题结尾。",
                "question_types": ["论述题"],
                "exam_expression": "理论文献的价值主要在于澄清机制、界定边界，而非直接给出现实世界中的经验效应大小。",
            },
            {
                "label": "高频术语",
                "core_content": "model, assumption, equilibrium, mechanism, proposition, incentive, boundary condition",
                "reason_for_written_exam": "适合理论术语积累。",
                "question_types": ["名词解释", "简答题"],
                "exam_expression": "作答时宜突出模型假设、机制链条、均衡结果和边界条件。",
            },
            {
                "label": "可背诵知识块",
                "core_content": "理论型数字经济研究通常通过设定关键假设，分析成本变化如何改变激励结构，并据此推导行为与均衡结果。",
                "reason_for_written_exam": "适合直接背诵。",
                "question_types": ["简答题", "论述题"],
                "exam_expression": "理论分析的关键在于：假设决定机制，机制决定结果，边界决定适用范围。",
            },
        ]

    return [
        {
            "label": "制度背景",
            "core_content": f"本文属于政策导向研究，核心讨论数字化条件下的{policy_line}等制度安排如何影响市场结果。",
            "reason_for_written_exam": "适合政策型文献概括。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"政策型数字经济文献的重点在于分析{policy_line}等制度安排如何塑造市场运行结果。",
        },
        {
            "label": "理论框架",
            "core_content": "文章围绕政策目标、制度工具、实施约束和经济后果构建分析框架。",
            "reason_for_written_exam": "适合制度分析题。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": "政策分析通常遵循‘政策目标—制度工具—实施约束—效果评价’的逻辑链条。",
        },
        {
            "label": "机制链条",
            "core_content": f"规则设计 -> {policy_line}变化 -> 激励与约束条件改变 -> 市场行为与福利结果变化。",
            "reason_for_written_exam": "适合政策机制题。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"从政策机制看，数字治理规则通过影响{policy_line}等关键制度条件，进一步改变市场激励与行为结果。",
        },
        {
            "label": "规范化结论表述",
            "core_content": "数字经济政策不能只追求效率提升，还应兼顾治理成本、实施约束与分配后果。",
            "reason_for_written_exam": "适合作为政策题结尾。",
            "question_types": ["论述题"],
            "exam_expression": "数字经济政策具有显著的效率与治理双重目标，政策设计需要在促进创新与防范风险之间寻求平衡。",
        },
        {
            "label": "政策背景",
            "core_content": f"文章涉及的政策背景主要包括{policy_line}，反映数字经济研究高度依赖现实制度环境。",
            "reason_for_written_exam": "适合联系现实作答。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": f"在现实层面，数字经济政策往往围绕{policy_line}等制度议题展开。",
        },
        {
            "label": "高频术语",
            "core_content": "policy evaluation, platform governance, privacy, regulation, digital rights, welfare, implementation constraints",
            "reason_for_written_exam": "适合政策术语积累。",
            "question_types": ["名词解释", "简答题"],
            "exam_expression": "作答时宜突出制度工具、实施约束、治理目标和政策后果。",
        },
        {
            "label": "可背诵知识块",
            "core_content": "政策型数字经济研究通常围绕制度工具如何改变市场激励、治理成本和福利结果展开。",
            "reason_for_written_exam": "适合迁移到政策论述题。",
            "question_types": ["简答题", "论述题"],
            "exam_expression": "政策分析的核心在于：制度设计改变激励结构，激励结构影响行为结果，行为结果决定政策绩效。",
        },
    ]


def build_overlap(metadata: PaperMetadata, cost_terms: list[str], policy_topics: list[str]) -> list[dict[str, str]]:
    mechanism = "、".join(cost_terms) if cost_terms else "关键成本下降"
    policy = "、".join(policy_topics) if policy_topics else "平台治理与隐私保护"
    topics = [
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
    if metadata.paper_type == "empirical":
        topics.append(
            {
                "topic": "实证识别",
                "interview_version": "我更关注它是怎么把相关性往因果识别方向推进的。",
                "written_version": "数字经济实证研究通常需要通过识别策略增强因果推断的可信度。",
            }
        )
    return topics[: max(2, min(4, len(topics)))]


def build_low_priority(metadata: PaperMetadata) -> list[dict[str, str]]:
    if metadata.paper_type == "review":
        return [
            {"label": "具体文献条目清单", "reason": "优先级低于统一框架、机制主线与政策含义。"},
            {"label": "机构与版本信息", "reason": "不影响对综述核心贡献的掌握。"},
        ]
    if metadata.paper_type == "empirical":
        return [
            {"label": "稳健性与附录细节", "reason": "在复试准备中优先级低于主结果、机制与异质性。"},
            {"label": "数据清洗与变量构造细节", "reason": "适合作为补充理解，不是第一轮记忆重点。"},
        ]
    if metadata.paper_type == "theoretical":
        return [
            {"label": "技术性推导细节", "reason": "适合作为深入阅读内容，不适合作为第一轮口头和笔试准备重点。"},
            {"label": "附录证明过程", "reason": "对抓住理论主线的边际收益较低。"},
        ]
    return [
        {"label": "制度实施中的枝节案例", "reason": "优先级低于政策目标、工具与治理逻辑。"},
        {"label": "背景材料中的扩展叙述", "reason": "适合作为补充阅读，不适合作为第一轮背诵重点。"},
    ]


def build_review_outline(metadata: PaperMetadata) -> dict[str, list[str]]:
    if metadata.paper_type == "review":
        return {
            "interview_outline": ["先讲研究背景。", "再讲统一框架。", "然后讲文献贡献与政策含义。", "最后讲局限性与开放问题。"],
            "written_outline": ["先背定义。", "再背理论脉络与框架。", "然后背政策背景。", "最后背结论表达与高频术语。"],
        }
    if metadata.paper_type == "empirical":
        return {
            "interview_outline": ["先讲研究问题。", "再讲识别策略。", "然后讲机制和异质性。", "最后讲政策含义与局限性。"],
            "written_outline": ["先背研究对象与定义。", "再背实证框架。", "然后背机制链条和结论。", "最后背政策背景与术语。"],
        }
    if metadata.paper_type == "theoretical":
        return {
            "interview_outline": ["先讲问题意识。", "再讲模型假设。", "然后讲核心机制与边界。", "最后讲现实启发。"],
            "written_outline": ["先背研究对象。", "再背模型框架。", "然后背机制推演。", "最后背规范化结论。"],
        }
    return {
        "interview_outline": ["先讲制度背景。", "再讲政策工具。", "然后讲治理权衡。", "最后讲现实启发。"],
        "written_outline": ["先背政策背景。", "再背分析框架。", "然后背机制链条。", "最后背规范化结论。"],
    }


def build_extra(metadata: PaperMetadata, cost_terms: list[str], policy_topics: list[str]) -> dict[str, Any]:
    mechanism = "、".join(cost_terms) if cost_terms else "关键成本下降"
    policy = "、".join(policy_topics) if policy_topics else "平台治理与制度约束"
    key_points = [f"{metadata.field}研究的关键是把技术变化还原为经济成本变化。"]
    if metadata.paper_type == "review":
        key_points.append("综述型文献的价值主要体现在统一框架与组织文献。")
    elif metadata.paper_type == "empirical":
        key_points.append("实证型文献的价值主要体现在识别总体效应、机制与异质性。")
    elif metadata.paper_type == "theoretical":
        key_points.append("理论型文献的价值主要体现在机制澄清和边界界定。")
    else:
        key_points.append("政策型文献的价值主要体现在制度评价与治理权衡。")
    key_points.append("数字化效应通常伴随明显异质性。")
    return {
        "key_points": key_points,
        "mechanisms": [
            f"数字化 -> {mechanism} -> 交易与组织方式变化",
            "技术扩散 -> 激励结构变化 -> 市场与福利结果重构",
        ],
        "policy_implications": [
            f"需要关注{policy}。",
            "需要把效率提升与制度治理放在同一分析框架下。",
        ],
        "limitations": [
            "不同场景下机制强弱可能存在明显异质性。",
            "需要结合具体文献类型判断外部适用性与识别力度。",
        ],
    }


def build_english_support(cost_terms: list[str], paper_type: str) -> dict[str, Any]:
    key_terms = [
        {"english": "digital economics", "chinese": "数字经济", "explanation": "研究数字技术如何改变经济活动与资源配置的领域。"},
        {"english": "consumer surplus", "chinese": "消费者剩余", "explanation": "消费者愿付价格与实际支付价格之间的差额。"},
        {"english": "platform governance", "chinese": "平台治理", "explanation": "围绕平台规则、激励和责任分配形成的治理安排。"},
        {"english": paper_type, "chinese": {"review": "综述型文献", "empirical": "实证型文献", "theoretical": "理论型文献", "policy": "政策型文献"}[paper_type], "explanation": "用于区分论文类型的内部分析标签。"},
    ]
    for token, chinese in DIGITAL_COST_LABELS:
        if chinese in cost_terms:
            key_terms.append({"english": f"{token} costs", "chinese": chinese, "explanation": f"指与{chinese}相关的资源消耗或约束。"})
    return {
        "key_terms": key_terms,
        "oral_sentence_patterns": [
            "This paper should be understood through its core mechanism rather than through isolated findings.",
            "The main contribution is to explain how changing costs reshape economic behavior.",
            "In the interview, I would first explain the question, then the mechanism, and finally the policy implication.",
        ],
        "written_sentence_patterns": [
            "The paper shows that digitization matters because it changes the structure of economic costs.",
            "The mechanism can be summarized as changing constraints leading to new behavioral and institutional outcomes.",
            "The final effect is heterogeneous and depends on organizational, institutional, and policy conditions.",
        ],
    }


def build_metadata(source: SourceData, forced_language: str | None = None) -> tuple[PaperMetadata, PaperSections, bool]:
    cleaned = source.raw_text
    if len(cleaned) < MIN_TEXT_LENGTH:
        raise UserFacingError(STANDARD_TEXT_PROMPT, EXIT_INFO_INSUFFICIENT)

    title, used_title_fallback = extract_title(cleaned, Path(source.source_path) if source.source_path != "<inline-text>" else None)
    authors = extract_authors(cleaned, title)
    year = extract_year(cleaned)

    provisional_language, _, _ = detect_language(cleaned, title_hint=title, abstract_hint="", forced=forced_language)
    abstract = extract_abstract(cleaned, provisional_language)
    language, confidence, reason = detect_language(cleaned, title_hint=title, abstract_hint=abstract, forced=forced_language)

    min_abstract_length = 60 if language == "中文文献" else 120
    if len(clean_text(abstract)) < min_abstract_length:
        raise UserFacingError(STANDARD_TEXT_PROMPT, EXIT_INFO_INSUFFICIENT)

    conclusion = extract_conclusion(cleaned, language)
    introduction = extract_introduction(cleaned, language)
    abstract_sentences = split_sentences(abstract, language)
    conclusion_sentences = split_sentences(conclusion, language)
    intro_sentences = split_sentences(introduction, language)

    field = determine_field(title, abstract, conclusion)
    keywords = extract_keywords(title, abstract, cleaned, field, language)
    paper_type = detect_paper_type(title, abstract, conclusion, cleaned)

    metadata = PaperMetadata(
        title=title,
        authors=authors,
        year=year,
        language=language,
        language_confidence=confidence,
        language_reason=reason,
        field=field,
        keywords=keywords,
        paper_type=paper_type,
    )
    sections = PaperSections(
        abstract=abstract,
        abstract_sentences=abstract_sentences,
        conclusion=conclusion,
        conclusion_sentences=conclusion_sentences,
        introduction=introduction,
        intro_sentences=intro_sentences,
    )
    return metadata, sections, used_title_fallback


def build_full_output(source: SourceData, forced_language: str | None = None) -> tuple[dict[str, Any], str, bool, PaperMetadata, PaperSections]:
    metadata, sections, used_title_fallback = build_metadata(source, forced_language=forced_language)
    cost_terms = detect_cost_terms("\n".join([source.raw_text, sections.abstract, sections.conclusion]))
    policy_topics = detect_policy_topics("\n".join([source.raw_text, sections.abstract, sections.conclusion]))

    full = {
        "meta": {"schema_version": "1.0"},
        "paper_info": {
            "title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "language": metadata.language,
            "field": metadata.field,
            "keywords": metadata.keywords,
        },
        "language_detect_result": {
            "detected_language": metadata.language,
            "confidence": metadata.language_confidence,
            "reason": metadata.language_reason,
        },
        "one_sentence_summary": build_topic_summary(metadata.title, metadata, sections, cost_terms),
        "interview_useful": build_interview_useful(metadata, sections, cost_terms, policy_topics),
        "written_exam_useful": build_written_exam_useful(metadata, sections, cost_terms, policy_topics),
        "overlap_but_rewritten": build_overlap(metadata, cost_terms, policy_topics),
        "low_priority": build_low_priority(metadata),
        "review_outline": build_review_outline(metadata),
        "extra": build_extra(metadata, cost_terms, policy_topics),
        "english_support": build_english_support(cost_terms, metadata.paper_type),
    }
    slug, slug_used_hash = slugify(metadata.title)
    return full, slug, used_title_fallback or slug_used_hash, metadata, sections


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
    if isinstance(schema, bool):
        if not isinstance(data, bool):
            raise ValueError(f"{path} should be a boolean")
        return
    if isinstance(schema, (int, float)):
        if not isinstance(data, (int, float)):
            raise ValueError(f"{path} should be a number")
        return
    if schema is None and data is not None:
        raise ValueError(f"{path} should be null")


def write_json(path: Path, data: dict[str, Any], schema_path: Path) -> None:
    schema = load_schema(schema_path)
    validate_against_schema(data, schema)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    validate_against_schema(reloaded, schema)


def style_sheet(sheet) -> None:
    header_fill = PatternFill(fill_type="solid", fgColor="DCE6F1")
    title_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    section_fill = PatternFill(fill_type="solid", fgColor="F4B183")

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = title_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    if sheet.max_row >= 2:
        for cell in sheet[2]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row in sheet.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    for column_cells in sheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            max_length = max(max_length, len(value))
        sheet.column_dimensions[column_letter].width = min(max(max_length + 2, 14), 48)

    if sheet.max_row >= 1:
        sheet.freeze_panes = "A3"

    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row):
        if row[0].value in {"Interview", "Written", "Overlap", "Terms", "Run Report"}:
            for cell in row:
                cell.font = Font(bold=True, color="000000")
                cell.fill = section_fill


def append_table(sheet, title: str, headers: list[str], rows: list[list[str]]) -> None:
    sheet.append([title])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    sheet.append([])


def create_excel_workbook(
    output_path: Path,
    full: dict[str, Any],
    interview: dict[str, Any],
    written: dict[str, Any],
    run_report: dict[str, Any],
) -> None:
    workbook = Workbook()

    overview = workbook.active
    overview.title = "Overview"
    overview.append(["Overview"])
    overview.append(["Field", "Value"])
    info = full["paper_info"]
    overview_rows = [
        ["Title", info["title"]],
        ["Authors", "；".join(info["authors"]) if info["authors"] else ""],
        ["Year", info["year"]],
        ["Language", info["language"]],
        ["Field", info["field"]],
        ["Keywords", "；".join(info["keywords"])],
        ["Summary", full["one_sentence_summary"]],
        ["Schema Version", full["meta"]["schema_version"]],
    ]
    for row in overview_rows:
        overview.append(row)
    style_sheet(overview)

    interview_sheet = workbook.create_sheet("Interview")
    append_table(
        interview_sheet,
        "Interview",
        ["Label", "Core Content", "Reason", "Typical Questions", "Oral Answer Sample"],
        [
            [
                item["label"],
                item["core_content"],
                item["reason_for_interview"],
                "；".join(item["typical_questions"]),
                item["oral_answer_sample"],
            ]
            for item in interview["interview_useful"]
        ],
    )
    style_sheet(interview_sheet)

    written_sheet = workbook.create_sheet("Written")
    append_table(
        written_sheet,
        "Written",
        ["Label", "Core Content", "Reason", "Question Types", "Exam Expression"],
        [
            [
                item["label"],
                item["core_content"],
                item["reason_for_written_exam"],
                "；".join(item["question_types"]),
                item["exam_expression"],
            ]
            for item in written["written_exam_useful"]
        ],
    )
    style_sheet(written_sheet)

    overlap_sheet = workbook.create_sheet("Overlap")
    append_table(
        overlap_sheet,
        "Overlap",
        ["Topic", "Interview Version", "Written Version"],
        [
            [item["topic"], item["interview_version"], item["written_version"]]
            for item in full["overlap_but_rewritten"]
        ],
    )
    style_sheet(overlap_sheet)

    terms_sheet = workbook.create_sheet("Terms")
    append_table(
        terms_sheet,
        "Terms",
        ["English", "Chinese", "Explanation"],
        [
            [item["english"], item["chinese"], item["explanation"]]
            for item in full["english_support"]["key_terms"]
        ],
    )
    append_table(
        terms_sheet,
        "Oral Patterns",
        ["Pattern"],
        [[item] for item in full["english_support"]["oral_sentence_patterns"]],
    )
    append_table(
        terms_sheet,
        "Written Patterns",
        ["Pattern"],
        [[item] for item in full["english_support"]["written_sentence_patterns"]],
    )
    style_sheet(terms_sheet)

    report_sheet = workbook.create_sheet("Run Report")
    report_sheet.append(["Run Report"])
    report_sheet.append(["Field", "Value"])
    for key, value in run_report.items():
        report_sheet.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value])
    style_sheet(report_sheet)

    workbook.save(output_path)
    reloaded = load_workbook(output_path)
    expected_sheets = {"Overview", "Interview", "Written", "Overlap", "Terms", "Run Report"}
    if set(reloaded.sheetnames) != expected_sheets:
        raise ValueError(f"Excel workbook sheets mismatch: {reloaded.sheetnames}")


def build_run_report(source: SourceData, metadata: PaperMetadata, sections: PaperSections, used_fallback_slug: bool) -> dict[str, Any]:
    return {
        "input_type": source.input_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": metadata.language,
        "paper_type": metadata.paper_type,
        "used_fallback_slug": used_fallback_slug,
        "abstract_length": len(sections.abstract),
        "source_path": source.source_path,
    }


def main() -> int:
    args = parse_args()
    input_path = args.input_file.resolve() if args.input_file else None
    try:
        source = load_source(input_path, args.input_text)
        full, auto_slug, used_fallback_slug, metadata, sections = build_full_output(source, forced_language=args.language)
        interview, written = split_outputs(full)

        if args.stdout_json:
            print(json.dumps(full, ensure_ascii=False, indent=2))
            return 0

        slug = args.slug or auto_slug
        output_root = args.output_dir.resolve() if args.output_dir else Path.cwd() / "output" / "economics-retest-paper-splitter"
        output_dir = output_root / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        run_report = build_run_report(source, metadata, sections, used_fallback_slug)

        write_json(output_dir / "full.json", full, FULL_SCHEMA_PATH)
        write_json(output_dir / "interview.json", interview, INTERVIEW_SCHEMA_PATH)
        write_json(output_dir / "written_exam.json", written, WRITTEN_SCHEMA_PATH)
        (output_dir / "run-report.json").write_text(
            json.dumps(run_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        create_excel_workbook(output_dir / EXCEL_FILENAME, full, interview, written, run_report)

        print(output_dir / "full.json")
        print(output_dir / "interview.json")
        print(output_dir / "written_exam.json")
        print(output_dir / EXCEL_FILENAME)
        return 0
    except UserFacingError as exc:
        print(str(exc))
        return exc.code
    except ValueError as exc:
        print(str(exc))
        return EXIT_SCHEMA_INVALID


if __name__ == "__main__":
    sys.exit(main())
