from __future__ import annotations

import json
from pathlib import Path

from app.boundary_checker import BoundaryDecision
from app.config import DATA_DIR
from app.models import GenerateRequest, SearchResult
from app.search import source_reliability_note
from app.student_profile import profile_as_prompt


TYPE_LABELS = {
    "lesson_package": "单节课教学包",
    "extra_reading_training": "课外材料与题型训练包",
    "parent_feedback": "家长反馈",
    "study_plan": "阶段学习规划",
}


def load_exam_profile() -> dict:
    path = DATA_DIR / "exam_profile_shanghai_junior.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def format_search_results(results: list[SearchResult]) -> str:
    if not results:
        return "未检索到联网资料，或本次未启用联网搜索。"
    lines = [source_reliability_note(results)]
    for idx, item in enumerate(results, start=1):
        lines.append(
            f"{idx}. [{item.source_level}级 | {item.search_category}类检索] {item.title}\n"
            f"   URL: {item.url}\n"
            f"   摘要: {item.snippet}"
        )
    return "\n".join(lines)


def build_search_summary_prompt(results: list[SearchResult]) -> str:
    return """请整理以下联网搜索结果，输出适合家教备课使用的资料摘要。

规则：
1. A/B级资料可以作为教学方向依据。
2. C级资料只能作为题材、难度、题型参考，不得直接复制。
3. D级资料不得用于核心教学内容。
4. 对语文/英语阅读材料，优先建议原创生成，不复制网络文章。
5. 如果资料可信度不足，请明确说明。

搜索结果：
""" + format_search_results(results)


def build_generation_prompt(
    req: GenerateRequest,
    boundary: BoundaryDecision,
    search_results: list[SearchResult],
    web_summary: str = "",
    rewrite_feedback: str = "",
) -> str:
    web_context = web_summary.strip() or format_search_results(search_results)
    local_context = req.local_context.strip()[:10000] or "未提供本地资料。"
    exam_profile = json.dumps(load_exam_profile(), ensure_ascii=False, indent=2)
    rewrite_block = f"\n质量检查要求重写原因：\n{rewrite_feedback}\n" if rewrite_feedback else ""

    return f"""你要生成一份「单节课可交付教学包 lesson_package」，不是普通教案。

产品定位：
能力导向型家教教研与交付 Agent。家教老师不应抢占学校老师的课本精讲内容，尤其是语文课文和英语课文。核心价值是围绕教材单元能力点、上海考试题型和学生薄弱点，生成课外拓展材料、专项训练题、答题方法、学习习惯训练和家长反馈。

学生画像：
{profile_as_prompt()}

本次输入：
- 学生地区：{req.region}
- 年级：{req.grade}
- 科目：{req.subject_focus}
- 教材版本：{req.textbook_version or "未提供"}
- 本次课时长：{req.duration_minutes} 分钟
- 本次课目标：{req.lesson_goal}
- 学生薄弱点：{req.weak_points or "未提供，默认注意力容易分散、数学审题不够细、语文阅读概括偏弱"}
- 家长期望：{req.parent_expectations or "学习方法、学习态度、自制力、规划能力、鼓励式教育"}
- 学生最近表现：{req.student_observation or "未提供"}
- 上节课记录：{req.previous_lesson_record or "未提供"}

学校内容边界检查结果：
- 本节课定位：{boundary.package_positioning}
- 是否涉及学校课文：{boundary.involves_school_text}
- 是否需要提前讲解课文细节：{boundary.needs_text_detail_teaching}
- 是否可转化为课外同类文本训练：{boundary.can_convert_to_extra_reading}
- 是否可转化为题型专项训练：{boundary.can_convert_to_exam_training}
- 是否允许具体教材章节细讲：{boundary.allow_textbook_chapter_detail}
- 必须写入结果的说明：{boundary.required_disclaimer}
- 限制规则：
{chr(10).join("- " + item for item in boundary.restrictions)}

联网资料摘要：
{web_context}

本地资料摘要：
{local_context}

上海题型画像库：
{exam_profile}
{rewrite_block}

硬性生成规则：
1. 输出必须是合法 JSON，不要用 Markdown 包裹，不要输出代码块。
2. 顶层必须包含：package_metadata, lesson_positioning, teacher_version, student_handout, homework_answer_key, parent_feedback, student_record_update, source_basis, evaluator_placeholder。
3. teacher_version 必须适合老师直接拿着上课，包含逐分钟流程。每个环节必须包含：time, teaching_goal, teacher_script, teacher_questions, possible_student_answers, hints_if_stuck, correction_if_wrong, encouragement, board_or_paper, observation_points, student_output。
4. 每 20 分钟至少有一个可见 student_output。120分钟课堂必须覆盖完整节奏。
5. student_handout 面向学生打印，不得出现教师内部提示，必须包含目标、任务清单、知识点填空、课堂练习、答题区、方法总结区、自我复盘区、课后任务。
6. homework_answer_key 必须三层：基础巩固、能力提升、挑战拓展。每道题必须有题目、答案、解析、易错点。数学题给步骤解析；语文/英语题给参考答案和评分要点。
7. parent_feedback 必须温和、专业、鼓励式，但问题明确，不空泛夸奖，并说明本节课没有抢学校课文内容。
8. student_record_update 必须是结构化 JSON 对象，包含：本节课完成内容、新发现的薄弱点、学习习惯表现、专注力表现、自制力表现、规划能力表现、下节课建议、需要家长配合的事项。
9. 对语文/英语：不得提前精讲学校课文；必须包含原创课外同类文本或英语语篇、上海题型化训练、答题方法、词句/词块积累和迁移任务。
10. 对数学：可以预习教材知识，但必须包含概念理解、例题、分层练习、易错点和规范步骤训练。
11. 如果教材版本或本地资料不足，不得生成具体教材章节内容。必须说明“本次内容不绑定具体教材章节”，并定位为通用能力导向课。
12. 禁止使用空泛表达：根据实际情况调整、可适当拓展、引导学生思考、作为企业级 AI Agent。
13. 资料规则：A/B级可作依据，C级只能辅助参考，D级不得用于核心内容。语文/英语阅读材料优先原创生成。

请按下面 JSON schema 输出：
{{
  "package_metadata": {{
    "title": "string",
    "student": "string",
    "region": "string",
    "grade": "string",
    "subjects": ["string"],
    "duration_minutes": 120,
    "package_type": "lesson_package",
    "human_review_required": false
  }},
  "lesson_positioning": {{
    "does_involve_school_text": false,
    "avoids_textbook_deep_teaching": true,
    "textbook_unit_ability_point": "string",
    "shanghai_exam_ability_points": ["string"],
    "content_boundary_statement": "string",
    "lesson_focus": "string"
  }},
  "teacher_version": {{
    "teacher_goal": "string",
    "minute_by_minute_flow": [
      {{
        "time": "0-10分钟",
        "teaching_goal": "string",
        "teacher_script": "可直接朗读的话术",
        "teacher_questions": ["string"],
        "possible_student_answers": ["string"],
        "hints_if_stuck": ["string"],
        "correction_if_wrong": ["string"],
        "encouragement": ["string"],
        "board_or_paper": "string",
        "observation_points": ["string"],
        "student_output": "string"
      }}
    ],
    "question_explanations": [
      {{
        "question_id": "string",
        "tested_ability": "string",
        "answer": "string",
        "thinking_path": "string",
        "common_mistakes": ["string"],
        "teacher_followups": ["string"],
        "correction_script": "string",
        "encouragement": "string"
      }}
    ]
  }},
  "student_handout": {{
    "print_title": "string",
    "lesson_goals": ["string"],
    "task_checklist": ["string"],
    "extra_reading_material": {{
      "title": "string",
      "text_type": "现代文/非连续性文本/英语语篇/数学方法材料",
      "difficulty": "string",
      "word_count": "string",
      "is_original": true,
      "source_basis": "string",
      "content": "原创文本或数学方法材料"
    }},
    "knowledge_fill_in": ["string"],
    "class_practice": [
      {{
        "id": "string",
        "question": "string",
        "answer_space": "留给学生作答的空白提示"
      }}
    ],
    "answer_area": ["string"],
    "method_summary_area": ["string"],
    "vocabulary_or_phrase_area": ["string"],
    "mistake_record_area": ["string"],
    "self_reflection_area": ["string"],
    "after_class_tasks": ["string"]
  }},
  "homework_answer_key": {{
    "basic": [{{"id":"string","question":"string","answer":"string","analysis":"string","scoring_points":["string"],"common_pitfall":"string"}}],
    "improvement": [{{"id":"string","question":"string","answer":"string","analysis":"string","scoring_points":["string"],"common_pitfall":"string"}}],
    "challenge": [{{"id":"string","question":"string","answer":"string","analysis":"string","scoring_points":["string"],"common_pitfall":"string"}}]
  }},
  "parent_feedback": {{
    "what_was_learned": "string",
    "student_performance": "string",
    "strengths": "string",
    "problems_found": "string",
    "improvement_strategy": "string",
    "home_support_suggestions": "string",
    "next_lesson_plan": "string",
    "school_content_boundary_note": "string"
  }},
  "student_record_update": {{
    "completed_content": ["string"],
    "new_weak_points": ["string"],
    "learning_habit_performance": "string",
    "attention_performance": "string",
    "self_control_performance": "string",
    "planning_ability_performance": "string",
    "next_lesson_suggestions": ["string"],
    "parent_support_needed": ["string"]
  }},
  "source_basis": {{
    "reliability_summary": "string",
    "a_b_sources_used_for_direction": ["string"],
    "c_sources_reference_only": ["string"],
    "d_sources_excluded": ["string"],
    "local_material_used": true,
    "original_text_statement": "string"
  }},
  "evaluator_placeholder": {{
    "evaluator_score": null,
    "evaluator_comments": []
  }}
}}
"""


def build_quality_prompt(package_json: str, req: GenerateRequest, boundary: BoundaryDecision) -> str:
    return f"""你是 lesson_quality_evaluator。请对下面的单节课教学包进行质量评分。

评分规则：20项，每项0-5分，总分100分。低于85分应重写；低于90分需要人工复核。

检查维度：
1. 是否分为教师版、学生版、作业答案版、家长反馈版、档案更新版。
2. 教师版是否有逐分钟流程。
3. 教师版是否有可直接朗读的教师话术。
4. 教师版是否有学生可能回答。
5. 教师版是否有纠偏话术。
6. 教师版是否有鼓励式反馈。
7. 学生版是否可打印。
8. 学生版是否有答题区。
9. 是否有具体练习题。
10. 是否有答案解析。
11. 是否有分层作业。
12. 是否结合学生画像中的薄弱点。
13. 是否体现学习方法训练。
14. 是否体现自制力/规划能力训练。
15. 是否有课堂观察点。
16. 是否有本节课结束后的学生产出。
17. 是否避免低可信来源。
18. 是否避免模糊教材表述。
19. 是否适合 {req.duration_minutes} 分钟真实课堂。
20. 是否可以导出为正式 Word/PDF。

学校内容边界：{boundary.model_dump_json(ensure_ascii=False)}

只输出合法 JSON：
{{
  "evaluator_score": 0,
  "evaluator_comments": ["string"],
  "item_scores": {{"1": 0, "2": 0}},
  "requires_human_review": true,
  "should_rewrite": true
}}

待评价教学包：
{package_json[:30000]}
"""

