from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    lesson_package = "lesson_package"
    extra_reading_training = "extra_reading_training"
    parent_feedback = "parent_feedback"
    study_plan = "study_plan"


class GenerateRequest(BaseModel):
    document_type: DocumentType = Field(DocumentType.lesson_package, description="生成类型")
    region: str = Field("上海", description="学生地区")
    grade: str = Field("新八年级上", description="年级")
    subject_focus: str = Field("语文 + 数学", description="本次课科目")
    textbook_version: str = Field("", description="教材版本")
    duration_minutes: int = Field(120, ge=30, le=240, description="课时长度")
    lesson_goal: str = Field(..., description="本次课目标")
    weak_points: str = Field("", description="学生薄弱点")
    parent_expectations: str = Field("", description="家长期望")
    student_observation: str = Field("", description="学生最近表现或补充信息")
    previous_lesson_record: str = Field("", description="上节课记录")
    local_context: str = Field("", description="本地资料提取内容")
    search_query: str = Field("", description="联网搜索关键词")
    use_web_search: bool = Field(True, description="是否联网搜索")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source_level: str = "C"
    search_category: str = "C"


class BoundaryDecision(BaseModel):
    subjects: list[str]
    involves_school_text: bool = False
    involves_upcoming_school_text: bool = False
    needs_text_detail_teaching: bool = False
    can_convert_to_extra_reading: bool = True
    can_convert_to_exam_training: bool = True
    allow_textbook_chapter_detail: bool = False
    package_positioning: str
    restrictions: list[str]
    required_disclaimer: str


class QualityEvaluation(BaseModel):
    evaluator_score: int
    evaluator_comments: list[str]
    item_scores: dict[str, int]
    requires_human_review: bool
    should_rewrite: bool

