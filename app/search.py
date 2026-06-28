from __future__ import annotations

from urllib.parse import parse_qs, quote_plus, unquote, urlparse
import re

import requests
from bs4 import BeautifulSoup

from app.config import get_settings
from app.models import GenerateRequest, SearchResult


A_LEVEL_DOMAINS = [
    "moe.gov.cn",
    "shmeea.edu.cn",
    "edu.sh.gov.cn",
    "shanghai.gov.cn",
    "pep.com.cn",
]

B_LEVEL_HINTS = [
    "教研",
    "名师",
    "学校",
    "school",
    "edu",
    "教师进修",
]

C_LEVEL_HINTS = [
    "百度文库",
    "学科网",
    "教习网",
    "组卷",
    "教案",
    "教育平台",
    "51jiaoxi",
    "zxxk",
    "renrendoc",
    "doc88",
]

D_LEVEL_HINTS = [
    "论坛",
    "问答",
    "营销",
    "淘宝",
    "百科",
    "zhidao",
    "baike",
    "taobao",
]


def classify_source(url: str, title: str = "", snippet: str = "") -> str:
    lowered = " ".join([url, title, snippet]).lower()
    if any(domain in lowered for domain in A_LEVEL_DOMAINS):
        return "A"
    if any(hint.lower() in lowered for hint in D_LEVEL_HINTS):
        return "D"
    if any(hint.lower() in lowered for hint in C_LEVEL_HINTS):
        return "C"
    if any(hint.lower() in lowered for hint in B_LEVEL_HINTS):
        return "B"
    return "C"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_duckduckgo_url(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return href


def build_search_queries(req: GenerateRequest) -> list[tuple[str, str]]:
    subject = req.subject_focus
    grade = req.grade
    region = req.region or "上海"
    weak = req.weak_points or "阅读概括 审题 规划能力"
    user_query = req.search_query.strip()

    queries: list[tuple[str, str]] = []
    if user_query:
        queries.append(("user", user_query))

    if "语文" in subject:
        queries.extend(
            [
                ("A", "site:shmeea.edu.cn 上海市 初中学业水平考试 语文 试卷 评析"),
                ("B", "site:moe.gov.cn 义务教育语文课程标准 2022 PDF 第四学段 阅读 表达 学习任务群"),
                ("C", f"初中 现代文 阅读 记叙文 成长 亲情 {grade} 信息筛选 内容概括 表达效果"),
                ("C", f"初中 非连续性文本 阅读 上海 {weak}"),
            ]
        )
    if "英语" in subject or "English" in subject:
        queries.extend(
            [
                ("A", "site:shmeea.edu.cn 上海市 初中学业水平考试 英语 试卷 评析"),
                ("B", "site:moe.gov.cn 义务教育英语课程标准 2022 PDF 主题 语篇 学习策略"),
                ("C", "junior high English reading passage friendship 300 words questions"),
                ("C", "grade 8 English reading passage questions writing task"),
            ]
        )
    if "数学" in subject:
        queries.extend(
            [
                ("B", "site:moe.gov.cn 义务教育数学课程标准 2022 初中 核心素养"),
                ("C", f"{region} 初中 {grade} 数学 预习 概念 审题 规范步骤 易错点"),
            ]
        )

    if not queries:
        queries.append(("B", f"{region} 初中 {grade} 学习方法 题型训练 {weak}"))
    return queries


def search_lesson_sources(req: GenerateRequest) -> list[SearchResult]:
    settings = get_settings()
    all_results: list[SearchResult] = []
    seen: set[str] = set()
    per_query_limit = max(2, min(settings.search_result_limit, 4))
    for category, query in build_search_queries(req):
        try:
            results = search_web(query, per_query_limit)
        except Exception:
            continue
        for item in results:
            if item.url in seen:
                continue
            seen.add(item.url)
            item.search_category = category
            all_results.append(item)
    return all_results[: max(settings.search_result_limit * 3, 8)]


def search_web(query: str, limit: int | None = None) -> list[SearchResult]:
    settings = get_settings()
    max_results = limit or settings.search_result_limit
    if not query.strip():
        return []
    if settings.search_provider == "tavily" and settings.tavily_api_key:
        return tavily_search(query, max_results)
    return duckduckgo_search(query, max_results)


def tavily_search(query: str, limit: int) -> list[SearchResult]:
    settings = get_settings()
    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": limit,
            "include_answer": False,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    results = []
    for item in data.get("results", [])[:limit]:
        url = item.get("url", "")
        title = clean_text(item.get("title", ""))
        snippet = clean_text(item.get("content", ""))
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                source_level=classify_source(url, title, snippet),
            )
        )
    return results


def duckduckgo_search(query: str, limit: int) -> list[SearchResult]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 TutorAIAgentMVP/0.2"},
        timeout=20,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for node in soup.select(".result"):
        link = node.select_one(".result__a")
        snippet = node.select_one(".result__snippet")
        if not link:
            continue
        href = normalize_duckduckgo_url(link.get("href", ""))
        title = clean_text(link.get_text(" "))
        desc = clean_text(snippet.get_text(" ") if snippet else "")
        if title and href:
            results.append(
                SearchResult(
                    title=title,
                    url=href,
                    snippet=desc,
                    source_level=classify_source(href, title, desc),
                )
            )
        if len(results) >= limit:
            break
    return results


def source_reliability_note(results: list[SearchResult]) -> str:
    counts = {level: sum(1 for item in results if item.source_level == level) for level in ["A", "B", "C", "D"]}
    if counts["A"] or counts["B"]:
        return (
            f"检索到 A/B 级资料 {counts['A'] + counts['B']} 条，可作为教学方向依据；"
            f"C 级 {counts['C']} 条仅作题材和题型参考；D 级 {counts['D']} 条不得用于核心内容。"
        )
    if counts["C"] or counts["D"]:
        return "当前资料可信度不足：仅检索到 C/D 级资料。系统应优先基于用户上传资料或通用教学方法生成，不得把 C/D 级资料作为核心依据。"
    return "未检索到可用联网资料。系统应基于用户上传资料、学生画像和通用教学方法生成。"

