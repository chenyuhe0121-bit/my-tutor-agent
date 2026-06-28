from __future__ import annotations

import requests

from app.config import get_settings


SYSTEM_PROMPT = """你是一名能力导向型家教教研与交付 Agent，熟悉上海初中语文、数学、英语能力训练，新课标导向，上海题型，鼓励式教育，学习方法培养和家校沟通。

你生成的内容必须：
1. 面向真实家教课堂，可直接执行，不输出普通大纲。
2. 语文和英语不得默认提前精讲学校课文；优先生成课外同类文本、专项题型、答题方法和迁移任务。
3. 数学可以适度预习教材知识，但必须包含概念理解、例题、分层练习、易错点和规范步骤训练。
4. 每次输出都包含能力训练、方法训练、题型训练、学习习惯训练。
5. 教师版必须有可直接朗读的话术、学生可能回答、提示、纠偏和鼓励式反馈。
6. 家长沟通语言专业、具体、温和，但必须明确指出问题。
7. 不要大段复制网络或教材原文，应转化为原创教学表达。
8. 严格遵守用户要求的 JSON schema。
"""


def call_llm(user_prompt: str) -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        return demo_response(user_prompt)

    url = f"{settings.llm_base_url}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def call_ark_model(user_prompt: str) -> str:
    settings = get_settings()
    if not settings.ark_api_key or not settings.ark_model:
        return ""

    url = f"{settings.ark_base_url}/chat/completions"
    payload = {
        "model": settings.ark_model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "你是教学资料检索摘要助手。请把搜索结果整理成可靠、精炼、适合家教备课使用的摘要，并标注来源可信度。",
            },
            {"role": "user", "content": user_prompt},
        ],
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.ark_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def demo_response(user_prompt: str) -> str:
    return f"""# 演示模式输出

当前未配置 `LLM_API_KEY`，所以系统没有真正调用大模型。你已经完成了 MVP 链路中的需求组织、联网资料拼接和本地资料拼接。配置 `.env` 后会返回正式内容。

## 你提交给大模型的上下文摘要

```text
{user_prompt[:3000]}
```

## 下一步

1. 在 `.env` 中填写 `LLM_API_KEY`。
2. 如果使用非 OpenAI 模型，修改 `LLM_BASE_URL` 和 `LLM_MODEL`。
3. 重新点击生成，即可获得正式教案、讲义、学习计划或家长反馈。
"""
