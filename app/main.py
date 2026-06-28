from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.boundary_checker import boundary_check, missing_required_inputs
from app.config import ROOT_DIR, UPLOAD_DIR, ensure_dirs, get_settings
from app.documents import package_to_markdown, save_lesson_package_documents
from app.file_reader import read_local_file
from app.llm import call_ark_model, call_llm
from app.models import DocumentType, GenerateRequest
from app.prompt_builder import TYPE_LABELS, build_generation_prompt, build_search_summary_prompt
from app.quality_evaluator import attach_evaluation, dump_json, evaluate_lesson_package, extract_json
from app.search import search_lesson_sources, source_reliability_note
from app.student_profile import STUDENT_PROFILE
from app.workflow import WORKFLOW_STEPS, create_session, load_session, next_step, run_step


ensure_dirs()

app = FastAPI(title=get_settings().app_name)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=ROOT_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "student": STUDENT_PROFILE,
            "type_labels": TYPE_LABELS,
            "settings": get_settings(),
        },
    )


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    document_type: DocumentType = Form(DocumentType.lesson_package),
    region: str = Form("上海"),
    grade: str = Form("新八年级上"),
    subject_focus: str = Form("语文 + 数学"),
    textbook_version: str = Form(""),
    duration_minutes: int = Form(120),
    lesson_goal: str = Form(...),
    weak_points: str = Form("注意力容易分散，数学审题不够细，语文阅读概括偏弱"),
    parent_expectations: str = Form("学习方法、学习态度、自制力、规划能力、鼓励式教育"),
    student_observation: str = Form(""),
    previous_lesson_record: str = Form(""),
    search_query: str = Form(""),
    use_web_search: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
):
    local_context_parts = []
    saved_files = []
    for upload in files:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix
        saved_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
        saved_path.write_bytes(await upload.read())
        saved_files.append(upload.filename)
        text = read_local_file(saved_path)
        if text:
            local_context_parts.append(f"[本地文件：{upload.filename}]\n{text[:8000]}")

    req = GenerateRequest(
        document_type=document_type,
        region=region,
        grade=grade,
        subject_focus=subject_focus,
        textbook_version=textbook_version,
        duration_minutes=duration_minutes,
        lesson_goal=lesson_goal,
        weak_points=weak_points,
        parent_expectations=parent_expectations,
        student_observation=student_observation,
        previous_lesson_record=previous_lesson_record,
        local_context="\n\n".join(local_context_parts),
        search_query=search_query,
        use_web_search=use_web_search,
    )


@app.post("/workflow/start", response_class=HTMLResponse)
async def workflow_start(
    request: Request,
    document_type: DocumentType = Form(DocumentType.lesson_package),
    region: str = Form("上海"),
    grade: str = Form("新八年级上"),
    subject_focus: str = Form("语文 + 数学"),
    textbook_version: str = Form(""),
    duration_minutes: int = Form(120),
    lesson_goal: str = Form(...),
    weak_points: str = Form("注意力容易分散，数学审题不够细，语文阅读概括偏弱"),
    parent_expectations: str = Form("学习方法、学习态度、自制力、规划能力、鼓励式教育"),
    student_observation: str = Form(""),
    previous_lesson_record: str = Form(""),
    search_query: str = Form(""),
    use_web_search: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
):
    local_context_parts = []
    saved_files = []
    for upload in files:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix
        saved_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
        saved_path.write_bytes(await upload.read())
        saved_files.append(upload.filename)
        text = read_local_file(saved_path)
        if text:
            local_context_parts.append(f"[本地文件：{upload.filename}]\n{text[:8000]}")

    req = GenerateRequest(
        document_type=document_type,
        region=region,
        grade=grade,
        subject_focus=subject_focus,
        textbook_version=textbook_version,
        duration_minutes=duration_minutes,
        lesson_goal=lesson_goal,
        weak_points=weak_points,
        parent_expectations=parent_expectations,
        student_observation=student_observation,
        previous_lesson_record=previous_lesson_record,
        local_context="\n\n".join(local_context_parts),
        search_query=search_query,
        use_web_search=use_web_search,
    )
    state = create_session(req, saved_files)
    state = run_step(state, "prepare")
    return render_workflow(request, state)


@app.get("/workflow/{session_id}", response_class=HTMLResponse)
def workflow_view(request: Request, session_id: str):
    return render_workflow(request, load_session(session_id))


@app.post("/workflow/{session_id}/step/{step}", response_class=HTMLResponse)
def workflow_step(request: Request, session_id: str, step: str):
    state = load_session(session_id)
    state = run_step(state, step)
    return render_workflow(request, state)


@app.post("/workflow/{session_id}/next", response_class=HTMLResponse)
def workflow_next(request: Request, session_id: str):
    state = load_session(session_id)
    step = next_step(state)
    if step:
        state = run_step(state, step)
    return render_workflow(request, state)


def render_workflow(request: Request, state: dict):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "student": STUDENT_PROFILE,
            "type_labels": TYPE_LABELS,
            "settings": get_settings(),
            "workflow_state": state,
            "workflow_steps": WORKFLOW_STEPS,
            "next_workflow_step": next_step(state),
        },
    )

    boundary = boundary_check(req)
    missing_inputs = missing_required_inputs(req)

    search_results = []
    if req.use_web_search:
        try:
            search_results = search_lesson_sources(req)
        except Exception as exc:
            req.local_context += f"\n\n[联网搜索失败] {exc}"

    web_summary = ""
    settings = get_settings()
    if search_results and settings.use_ark_search_summary and settings.ark_api_key and settings.ark_model:
        try:
            web_summary = call_ark_model(build_search_summary_prompt(search_results))
        except Exception as exc:
            web_summary = f"[豆包搜索摘要失败，已回退原始搜索结果] {exc}\n\n"

    package: dict = {}
    generation_error = ""
    evaluation = None
    try:
        raw_output = call_llm(build_generation_prompt(req, boundary, search_results, web_summary=web_summary))
        package = extract_json(raw_output)
        evaluation = evaluate_lesson_package(package, req, boundary)
        if evaluation.should_rewrite:
            raw_output = call_llm(
                build_generation_prompt(
                    req,
                    boundary,
                    search_results,
                    web_summary=web_summary,
                    rewrite_feedback="；".join(evaluation.evaluator_comments),
                )
            )
            package = extract_json(raw_output)
            evaluation = evaluate_lesson_package(package, req, boundary)
        package = attach_evaluation(package, evaluation)
    except Exception as exc:
        generation_error = str(exc)
        package = fallback_package(req, boundary, missing_inputs, search_results, generation_error)
        evaluation = evaluate_lesson_package(package, req, boundary)
        package = attach_evaluation(package, evaluation)

    doc_paths = {}
    docx_error = ""
    try:
        doc_paths = save_lesson_package_documents(package)
    except Exception as exc:
        docx_error = str(exc)

    result_markdown = package_to_markdown(package)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "student": STUDENT_PROFILE,
            "type_labels": TYPE_LABELS,
            "settings": get_settings(),
            "result": result_markdown,
            "doc_paths": doc_paths,
            "docx_error": docx_error,
            "saved_files": saved_files,
            "search_results": search_results,
            "missing_inputs": missing_inputs,
            "boundary": boundary,
            "source_note": source_reliability_note(search_results),
            "generation_error": generation_error,
        },
    )


def fallback_package(req: GenerateRequest, boundary, missing_inputs: list[str], search_results, error: str) -> dict:
    return {
        "package_metadata": {
            "title": "单节课教学包生成失败后的保底结构",
            "student": "上海新八女生",
            "region": req.region,
            "grade": req.grade,
            "subjects": [s.strip() for s in req.subject_focus.replace("+", "、").split("、") if s.strip()],
            "duration_minutes": req.duration_minutes,
            "package_type": "lesson_package",
            "human_review_required": True,
        },
        "lesson_positioning": {
            "does_involve_school_text": boundary.involves_school_text,
            "avoids_textbook_deep_teaching": True,
            "textbook_unit_ability_point": "教材版本或本地资料不足时，仅生成通用能力导向课。",
            "shanghai_exam_ability_points": ["信息筛选", "内容概括", "审题", "规范表达"],
            "content_boundary_statement": boundary.required_disclaimer,
            "lesson_focus": "语文+数学预习方法启动课",
        },
        "teacher_version": {
            "teacher_goal": "保底版本仅供排查生成错误，正式授课前必须重新生成。",
            "minute_by_minute_flow": [
                {
                    "time": "0-20分钟",
                    "teaching_goal": "建立课堂目标和学习产出意识",
                    "teacher_script": "今天我们不抢学校课文内容，而是训练你上课前就能用的预习方法。",
                    "teacher_questions": ["你平时预习时最容易卡在哪里？"],
                    "possible_student_answers": ["不知道重点", "读完记不住", "数学题看不懂"],
                    "hints_if_stuck": ["可以从语文阅读和数学审题各说一个困难。"],
                    "correction_if_wrong": ["这不是能力差，而是还没有固定方法。我们今天先把方法固定下来。"],
                    "encouragement": ["你能说出卡点，就已经开始会学习了。"],
                    "board_or_paper": "写下：目标-方法-产出",
                    "observation_points": ["是否能说出一个具体困难"],
                    "student_output": "写出本节课个人目标",
                }
            ],
            "question_explanations": [],
        },
        "student_handout": {
            "print_title": "语文+数学预习方法启动课",
            "lesson_goals": ["学会一套语文预习五步法", "学会数学审题三步法"],
            "task_checklist": ["写出目标", "完成练习", "记录错因"],
            "extra_reading_material": {
                "title": "本次不绑定具体教材章节",
                "text_type": "方法材料",
                "difficulty": "八年级适用",
                "word_count": "约300字",
                "is_original": True,
                "source_basis": "基于学生薄弱点生成",
                "content": "正式内容生成失败，请检查模型输出。错误：" + error,
            },
            "knowledge_fill_in": ["预习不是提前背答案，而是带着____去听课。"],
            "class_practice": [{"id": "P1", "question": "写出你今天要改进的一个学习动作。", "answer_space": "________________"}],
            "answer_area": ["________________"],
            "method_summary_area": ["今天我学到的方法是：________________"],
            "vocabulary_or_phrase_area": [],
            "mistake_record_area": ["我的错因：________________"],
            "self_reflection_area": ["我今天最专注的时刻是：________________"],
            "after_class_tasks": ["每天用15分钟完成一次预习打卡。"],
        },
        "homework_answer_key": {"basic": [], "improvement": [], "challenge": []},
        "parent_feedback": {
            "what_was_learned": "本次生成失败，系统输出保底结构。",
            "student_performance": "需要重新生成后填写。",
            "strengths": "需要课堂观察后填写。",
            "problems_found": "模型生成错误：" + error,
            "improvement_strategy": "检查 API、网络或提示词后重新生成。",
            "home_support_suggestions": "暂不发送给家长。",
            "next_lesson_plan": "重新生成正式教学包。",
            "school_content_boundary_note": boundary.required_disclaimer,
        },
        "student_record_update": {
            "completed_content": [],
            "new_weak_points": [],
            "learning_habit_performance": "待记录",
            "attention_performance": "待记录",
            "self_control_performance": "待记录",
            "planning_ability_performance": "待记录",
            "next_lesson_suggestions": ["重新生成正式教学包"],
            "parent_support_needed": [],
        },
        "source_basis": {
            "reliability_summary": source_reliability_note(search_results),
            "a_b_sources_used_for_direction": [],
            "c_sources_reference_only": [],
            "d_sources_excluded": [],
            "local_material_used": bool(req.local_context.strip()),
            "original_text_statement": "保底结构，无正式原创阅读材料。",
        },
    }
