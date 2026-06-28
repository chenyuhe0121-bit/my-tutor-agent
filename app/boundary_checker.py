from __future__ import annotations

import re

from app.models import BoundaryDecision, GenerateRequest


CHINESE_ALIASES = ("语文", "中文", "阅读", "作文")
ENGLISH_ALIASES = ("英语", "英文", "english")
MATH_ALIASES = ("数学", "math")
TEXTBOOK_DETAIL_WORDS = (
    "课文",
    "原文",
    "精讲",
    "逐段",
    "逐句",
    "翻译",
    "课内",
    "教材章节",
    "第",
    "单元",
)


def split_subjects(subject_focus: str) -> list[str]:
    text = subject_focus.lower()
    subjects: list[str] = []
    if any(alias.lower() in text for alias in CHINESE_ALIASES):
        subjects.append("语文")
    if any(alias.lower() in text for alias in ENGLISH_ALIASES):
        subjects.append("英语")
    if any(alias.lower() in text for alias in MATH_ALIASES):
        subjects.append("数学")
    return subjects or [subject_focus.strip() or "综合"]


def has_textbook_detail_intent(req: GenerateRequest) -> bool:
    text = " ".join([req.lesson_goal, req.search_query, req.local_context[:500], req.textbook_version])
    return any(word in text for word in TEXTBOOK_DETAIL_WORDS)


def has_local_material(req: GenerateRequest) -> bool:
    return bool(req.local_context.strip())


def boundary_check(req: GenerateRequest) -> BoundaryDecision:
    subjects = split_subjects(req.subject_focus)
    asks_textbook_detail = has_textbook_detail_intent(req)
    restrictions: list[str] = []
    allow_textbook_chapter_detail = False

    if "数学" in subjects:
        allow_textbook_chapter_detail = bool(req.textbook_version.strip() or has_local_material(req))
        restrictions.append("数学可以进行教材知识预习，但必须包含概念理解、例题、分层练习、易错点和规范步骤训练。")

    if "语文" in subjects:
        restrictions.append("语文不得默认提前精讲学校课文；只能轻触背景、字词和预习方法，核心训练应转为课外同类文本与上海题型专项。")

    if "英语" in subjects:
        restrictions.append("英语不得逐句翻译学校课文；应生成同主题原创语篇，配套阅读题、词块积累、句型仿写和写作迁移。")

    if not req.textbook_version.strip() or not has_local_material(req):
        restrictions.append("教材版本或本地资料不足时，不允许生成具体教材章节内容，只能生成通用能力导向课。")

    involves_school_text = asks_textbook_detail and any(s in subjects for s in ("语文", "英语"))
    needs_text_detail_teaching = involves_school_text
    if any(s in subjects for s in ("语文", "英语")):
        positioning = "能力导向型家教教学包：避开课文精讲，围绕课本单元能力点、上海题型和学生薄弱点生成课外材料与专项训练。"
    elif "数学" in subjects:
        positioning = "数学预习与方法训练教学包：可适度预习教材知识，但以概念理解、审题、规范步骤和错题归因为核心。"
    else:
        positioning = "通用学习能力训练教学包。"

    disclaimer = ""
    if not req.textbook_version.strip() or not has_local_material(req):
        disclaimer = "本次内容不绑定具体教材章节；如需生成教材章节级内容，请上传教材目录、课本照片或输入准确教材版本。"
    if involves_school_text:
        disclaimer = (disclaimer + " " if disclaimer else "") + "本次不会提前精讲学校课文，将转化为课外同类文本和题型专项训练。"

    return BoundaryDecision(
        subjects=subjects,
        involves_school_text=involves_school_text,
        involves_upcoming_school_text=involves_school_text,
        needs_text_detail_teaching=needs_text_detail_teaching,
        can_convert_to_extra_reading=any(s in subjects for s in ("语文", "英语")),
        can_convert_to_exam_training=True,
        allow_textbook_chapter_detail=allow_textbook_chapter_detail,
        package_positioning=positioning,
        restrictions=restrictions,
        required_disclaimer=disclaimer or "本次内容以能力训练、方法训练、题型训练和学习习惯训练为主。",
    )


def missing_required_inputs(req: GenerateRequest) -> list[str]:
    checks = {
        "学生地区": req.region,
        "年级": req.grade,
        "科目": req.subject_focus,
        "本次课时长": str(req.duration_minutes),
        "本次课目标": req.lesson_goal,
        "学生薄弱点": req.weak_points,
        "家长期望": req.parent_expectations,
    }
    missing = [label for label, value in checks.items() if not str(value).strip()]
    if not req.textbook_version.strip():
        missing.append("教材版本")
    if not req.local_context.strip():
        missing.append("本地资料")
    if not req.previous_lesson_record.strip():
        missing.append("上节课记录")
    return missing

