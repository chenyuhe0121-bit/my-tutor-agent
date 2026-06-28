from __future__ import annotations

import json
import re
from typing import Any

from app.boundary_checker import BoundaryDecision
from app.llm import call_llm
from app.models import GenerateRequest, QualityEvaluation
from app.prompt_builder import build_quality_prompt


QUALITY_ITEMS = {
    "1": ("teacher_version", "student_handout", "homework_answer_key", "parent_feedback", "student_record_update"),
    "2": ("minute_by_minute_flow",),
    "3": ("teacher_script",),
    "4": ("possible_student_answers",),
    "5": ("correction_if_wrong", "correction_script"),
    "6": ("encouragement",),
    "7": ("student_handout", "print_title"),
    "8": ("answer_area", "answer_space"),
    "9": ("class_practice", "question"),
    "10": ("analysis", "answer"),
    "11": ("basic", "improvement", "challenge"),
    "12": ("weak", "薄弱", "审题", "概括", "注意力"),
    "13": ("方法", "method"),
    "14": ("自制力", "规划", "self_control", "planning"),
    "15": ("observation_points",),
    "16": ("student_output",),
    "17": ("source_basis", "reliability"),
    "18": ("content_boundary_statement", "本次内容不绑定具体教材章节"),
    "19": ("120", "minute_by_minute_flow"),
    "20": ("teacher_version", "student_handout", "parent_feedback"),
}


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def heuristic_evaluate(package: dict[str, Any], req: GenerateRequest) -> QualityEvaluation:
    text = dump_json(package)
    item_scores: dict[str, int] = {}
    for item, keywords in QUALITY_ITEMS.items():
        score = 5 if all(keyword in text for keyword in keywords[: min(len(keywords), 3)]) else 3
        if item == "19" and str(req.duration_minutes) in text:
            score = 5
        item_scores[item] = score

    required = ["teacher_version", "student_handout", "homework_answer_key", "parent_feedback", "student_record_update"]
    missing = [key for key in required if key not in package]
    if missing:
        for item in ["1", "20"]:
            item_scores[item] = min(item_scores[item], 1)

    score = sum(item_scores.values())
    comments = []
    if missing:
        comments.append(f"缺少核心模块：{', '.join(missing)}")
    if score < 90:
        comments.append("建议人工复核：教学包仍可能存在细节不足。")
    if not comments:
        comments.append("结构完整，达到 MVP 教学包交付要求。")
    return QualityEvaluation(
        evaluator_score=score,
        evaluator_comments=comments,
        item_scores=item_scores,
        requires_human_review=score < 90,
        should_rewrite=score < 85,
    )


def evaluate_lesson_package(
    package: dict[str, Any],
    req: GenerateRequest,
    boundary: BoundaryDecision,
) -> QualityEvaluation:
    package_json = dump_json(package)
    try:
        raw = call_llm(build_quality_prompt(package_json, req, boundary))
        data = extract_json(raw)
        return QualityEvaluation(**data)
    except Exception:
        return heuristic_evaluate(package, req)


def attach_evaluation(package: dict[str, Any], evaluation: QualityEvaluation) -> dict[str, Any]:
    evaluation.requires_human_review = evaluation.evaluator_score < 90
    evaluation.should_rewrite = evaluation.evaluator_score < 85
    package["evaluator_score"] = evaluation.evaluator_score
    package["evaluator_comments"] = evaluation.evaluator_comments
    package["evaluator_item_scores"] = evaluation.item_scores
    package["requires_human_review"] = evaluation.requires_human_review
    if isinstance(package.get("package_metadata"), dict):
        package["package_metadata"]["human_review_required"] = evaluation.requires_human_review
    return package
