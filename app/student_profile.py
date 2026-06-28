STUDENT_PROFILE = {
    "name": "上海新八女生",
    "region": "上海",
    "grade": "新八年级上",
    "subjects": ["语文", "数学", "英语"],
    "stage": "八年级上能力导向预习与专项训练",
    "curriculum": "新课标导向 + 上海题型能力训练",
    "parent_expectations": [
        "授课中老师以身作则",
        "教会孩子正确的学习方法和学习态度",
        "帮助孩子提高自制力",
        "帮助孩子学会做规划",
        "采用鼓励式教育",
    ],
    "weak_points": [
        "注意力容易分散",
        "数学审题不够细",
        "语文阅读概括偏弱",
    ],
    "default_strategy": {
        "product_positioning": [
            "能力导向型家教教研与交付 Agent",
            "不把家教课变成学校课文替代课堂",
            "每节课同时包含能力训练、方法训练、题型训练和学习习惯训练",
        ],
        "chinese": [
            "不提前精讲八上课文",
            "围绕单元能力生成课外同类文本",
            "重点训练概括、批注、信息筛选、主旨理解、表达效果",
            "每节课保留一个方法卡",
        ],
        "english": [
            "不逐句讲学校课文",
            "生成同主题英语语篇",
            "重点训练阅读理解、词块积累、句型仿写和短文表达",
            "每节课保留一个词块卡和一个仿写任务",
        ],
        "math": [
            "可以进行教材知识预习",
            "强调概念理解、审题、画图、规范步骤、错题整理",
            "每道题训练从条件到结论的推理链",
        ],
        "habits": [
            "每 20 分钟必须有一个可见学生产出",
            "每节课设置一个学习方法小目标",
            "每周设置一个可完成的规划任务",
            "反馈语言具体、温和、可执行，但问题要明确",
        ],
    },
}


def profile_as_prompt() -> str:
    lines = [
        "学生画像：",
        f"- 地区：{STUDENT_PROFILE['region']}",
        f"- 年级：{STUDENT_PROFILE['grade']}",
        f"- 科目：{'、'.join(STUDENT_PROFILE['subjects'])}",
        f"- 学习阶段：{STUDENT_PROFILE['stage']}",
        f"- 课程导向：{STUDENT_PROFILE['curriculum']}",
        "- 已知薄弱点：",
    ]
    lines.extend(f"  - {item}" for item in STUDENT_PROFILE["weak_points"])
    lines.append("- 家长期望：")
    lines.extend(f"  - {item}" for item in STUDENT_PROFILE["parent_expectations"])
    lines.append("- 默认教学策略：")
    for subject, items in STUDENT_PROFILE["default_strategy"].items():
        lines.append(f"  - {subject}:")
        lines.extend(f"    - {item}" for item in items)
    return "\n".join(lines)

