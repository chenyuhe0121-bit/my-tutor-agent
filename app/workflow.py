from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.boundary_checker import boundary_check, missing_required_inputs
from app.config import DATA_DIR, get_settings
from app.documents import save_lesson_package_documents
from app.llm import call_ark_model, call_llm
from app.models import GenerateRequest
from app.prompt_builder import build_quality_prompt, build_search_summary_prompt, format_search_results, load_exam_profile
from app.quality_evaluator import attach_evaluation, evaluate_lesson_package, extract_json
from app.search import search_lesson_sources, source_reliability_note
from app.student_profile import profile_as_prompt


SESSION_DIR = DATA_DIR / "sessions"

WORKFLOW_STEPS = [
    ("prepare", "资料检索与边界检查"),
    ("teacher_version", "教师授课版"),
    ("student_handout", "学生讲义版"),
    ("homework_answer_key", "作业与答案版"),
    ("parent_feedback", "家长反馈版"),
    ("student_record_update", "学生档案更新"),
    ("quality_export", "质量检查与Word导出"),
]


def ensure_session_dir() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:8]


def session_path(session_id: str) -> Path:
    ensure_session_dir()
    return SESSION_DIR / f"{session_id}.json"


def save_session(state: dict[str, Any]) -> None:
    import json

    path = session_path(state["session_id"])
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: str) -> dict[str, Any]:
    import json

    return json.loads(session_path(session_id).read_text(encoding="utf-8"))


def create_session(req: GenerateRequest, saved_files: list[str]) -> dict[str, Any]:
    state = {
        "session_id": new_session_id(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "request": req.model_dump(),
        "saved_files": saved_files,
        "status": {
            "prepare": "pending",
            "teacher_version": "pending",
            "student_handout": "pending",
            "homework_answer_key": "pending",
            "parent_feedback": "pending",
            "student_record_update": "pending",
            "quality_export": "pending",
        },
        "logs": [],
        "context": {},
        "package": {},
        "doc_paths": {},
        "errors": {},
    }
    save_session(state)
    return state


def append_log(state: dict[str, Any], message: str) -> None:
    state["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} {message}")


def next_step(state: dict[str, Any]) -> str | None:
    for step, _ in WORKFLOW_STEPS:
        if state["status"].get(step) != "done":
            return step
    return None


def run_step(state: dict[str, Any], step: str) -> dict[str, Any]:
    if step not in state["status"]:
        raise ValueError(f"Unknown workflow step: {step}")
    state["status"][step] = "running"
    save_session(state)
    try:
        if step == "prepare":
            run_prepare(state)
        elif step in {"teacher_version", "student_handout", "homework_answer_key", "parent_feedback", "student_record_update"}:
            run_module_generation(state, step)
        elif step == "quality_export":
            run_quality_export(state)
        else:
            raise ValueError(f"Unsupported step: {step}")
        state["status"][step] = "done"
        state["errors"].pop(step, None)
    except Exception as exc:
        state["status"][step] = "error"
        state["errors"][step] = str(exc)
        append_log(state, f"{step} failed: {exc}")
    save_session(state)
    return state


def run_prepare(state: dict[str, Any]) -> None:
    req = GenerateRequest(**state["request"])
    boundary = boundary_check(req)
    missing = missing_required_inputs(req)
    search_results = []
    if req.use_web_search:
        search_results = [item.model_dump() for item in search_lesson_sources(req)]
    web_summary = ""
    settings = get_settings()
    if search_results and settings.use_ark_search_summary and settings.ark_api_key and settings.ark_model:
        try:
            from app.models import SearchResult

            web_summary = call_ark_model(build_search_summary_prompt([SearchResult(**item) for item in search_results]))
        except Exception as exc:
            web_summary = f"[豆包搜索摘要失败，已回退原始搜索结果] {exc}"
    state["context"] = {
        "boundary": boundary.model_dump(),
        "missing_inputs": missing,
        "search_results": search_results,
        "source_note": source_reliability_note([__import__("app.models", fromlist=["SearchResult"]).SearchResult(**item) for item in search_results]),
        "web_summary": web_summary,
    }
    append_log(state, "完成资料检索与学校内容边界检查。")


def run_module_generation(state: dict[str, Any], module_name: str) -> None:
    req = GenerateRequest(**state["request"])
    if not state.get("context"):
        run_prepare(state)
    prompt = build_module_prompt(state, module_name, req)
    raw = call_llm(prompt)
    module_data = extract_json(raw)
    if module_name in module_data and isinstance(module_data[module_name], (dict, list)):
        module_data = module_data[module_name]
    state["package"][module_name] = module_data
    ensure_metadata_and_positioning(state)
    append_log(state, f"完成 {module_name} 生成。")


def ensure_metadata_and_positioning(state: dict[str, Any]) -> None:
    req = GenerateRequest(**state["request"])
    boundary = state["context"].get("boundary", {})
    package = state["package"]
    package.setdefault(
        "package_metadata",
        {
            "title": "单节课可交付教学包",
            "student": "上海新八女生",
            "region": req.region,
            "grade": req.grade,
            "subjects": [s.strip() for s in req.subject_focus.replace("+", "、").split("、") if s.strip()],
            "duration_minutes": req.duration_minutes,
            "package_type": "lesson_package",
            "human_review_required": False,
        },
    )
    package.setdefault(
        "lesson_positioning",
        {
            "does_involve_school_text": boundary.get("involves_school_text", False),
            "avoids_textbook_deep_teaching": True,
            "textbook_unit_ability_point": "不绑定具体教材章节，围绕单元能力点生成训练。",
            "shanghai_exam_ability_points": ["信息筛选", "内容概括", "审题", "规范表达"],
            "content_boundary_statement": boundary.get("required_disclaimer", ""),
            "lesson_focus": req.lesson_goal,
        },
    )


def run_quality_export(state: dict[str, Any]) -> None:
    req = GenerateRequest(**state["request"])
    boundary = boundary_check(req)
    ensure_metadata_and_positioning(state)
    package = state["package"]
    package.setdefault(
        "source_basis",
        {
            "reliability_summary": state["context"].get("source_note", ""),
            "a_b_sources_used_for_direction": [],
            "c_sources_reference_only": [],
            "d_sources_excluded": [],
            "local_material_used": bool(req.local_context.strip()),
            "original_text_statement": "语文/英语阅读材料优先原创生成；网络材料只作题型和方向参考。",
        },
    )
    evaluation = evaluate_lesson_package(package, req, boundary)
    package = attach_evaluation(package, evaluation)
    state["package"] = package
    doc_paths = save_lesson_package_documents(package)
    state["doc_paths"] = {key: str(path) for key, path in doc_paths.items()}
    append_log(state, f"完成质量检查与Word导出，评分 {evaluation.evaluator_score}/100。")


def build_module_prompt(state: dict[str, Any], module_name: str, req: GenerateRequest) -> str:
    boundary = state["context"].get("boundary", {})
    search_results_text = format_search_results(
        [__import__("app.models", fromlist=["SearchResult"]).SearchResult(**item) for item in state["context"].get("search_results", [])]
    )
    web_summary = state["context"].get("web_summary") or search_results_text
    current_package = state.get("package", {})
    exam_profile = load_exam_profile()
    base = f"""你正在分步骤生成单节课教学包。当前只生成模块：{module_name}。

必须遵守：
1. 语文和英语不得提前精讲学校课文，必须转为课外同类文本与题型专项训练。
2. 数学可以做预习，但必须训练概念理解、审题、画图、规范步骤和错题整理。
3. 不能输出空泛话，必须可直接用于真实课堂。
4. 只输出合法 JSON，不要 Markdown，不要代码块。

学生画像：
{profile_as_prompt()}

本次输入：
- 地区：{req.region}
- 年级：{req.grade}
- 科目：{req.subject_focus}
- 教材版本：{req.textbook_version or "未提供"}
- 课时：{req.duration_minutes}分钟
- 目标：{req.lesson_goal}
- 薄弱点：{req.weak_points}
- 家长期望：{req.parent_expectations}
- 学生表现：{req.student_observation}
- 上节课记录：{req.previous_lesson_record or "未提供"}

边界检查：
{boundary}

联网资料：
{web_summary}

本地资料：
{req.local_context[:8000] or "未提供本地资料。"}

上海题型画像：
{exam_profile}

已生成模块：
{current_package}
"""
    schemas = {
        "teacher_version": """输出 {"teacher_version": {...}}。必须包含 teacher_goal, minute_by_minute_flow, question_explanations。minute_by_minute_flow 每个环节包含 time, teaching_goal, teacher_script, teacher_questions, possible_student_answers, hints_if_stuck, correction_if_wrong, encouragement, board_or_paper, observation_points, student_output。每20分钟必须有可见产出。""",
        "student_handout": """输出 {"student_handout": {...}}。面向学生打印，不得出现教师内部提示。必须包含 print_title, lesson_goals, task_checklist, extra_reading_material, knowledge_fill_in, class_practice, answer_area, method_summary_area, vocabulary_or_phrase_area, mistake_record_area, self_reflection_area, after_class_tasks。语文/英语必须有原创课外材料。""",
        "homework_answer_key": """输出 {"homework_answer_key": {...}}。必须包含 basic, improvement, challenge 三层。每题有 id, question, answer, analysis, scoring_points, common_pitfall。数学题给步骤解析；语文/英语给参考答案和评分要点。""",
        "parent_feedback": """输出 {"parent_feedback": {...}}。必须包含 what_was_learned, student_performance, strengths, problems_found, improvement_strategy, home_support_suggestions, next_lesson_plan, school_content_boundary_note。必须说明没有抢学校课文内容。""",
        "student_record_update": """输出 {"student_record_update": {...}}。必须包含 completed_content, new_weak_points, learning_habit_performance, attention_performance, self_control_performance, planning_ability_performance, next_lesson_suggestions, parent_support_needed。""",
    }
    return base + "\n模块 schema：\n" + schemas[module_name]

