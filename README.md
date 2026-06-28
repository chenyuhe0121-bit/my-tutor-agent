# 家教 AI Agent MVP

这是一个面向真实家教单子的快速可运行 MVP，聚焦：

- 上海新八年级女生
- 语文、数学八上预习
- 新课标导向
- 学习方法、自制力、规划能力培养
- 鼓励式教育
- 联网搜索教材/教案/课程大纲资料
- 调用大模型生成教案、讲义、家长反馈
- 读取本地 Word/PDF/Markdown/TXT 资料
- 导出 Markdown 和 Word 文档

## 1. 快速启动

```powershell
cd D:\实习文件夹\tutor-ai-agent-mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`，至少填写：

```env
LLM_API_KEY=你的大模型API密钥
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=https://api.openai.com/v1
```

如果你使用 DeepSeek、Kimi、通义等 OpenAI 兼容接口，修改 `LLM_BASE_URL` 和 `LLM_MODEL` 即可。

启动：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开：

```text
http://127.0.0.1:8000
```

## 2. 联网搜索配置

默认使用 DuckDuckGo HTML 搜索，不需要 API Key，但稳定性受网络环境影响。

也可以使用 Tavily：

```env
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的TavilyKey
```

## 3. 输出文件

生成结果会保存在：

```text
outputs/
```

每次生成会输出：

- `.md`：Markdown 文档
- `.docx`：Word 文档

## 4. MVP 功能范围

当前版本已包含：

- 固定种子学生档案
- 本地资料上传与文本提取
- 联网搜索
- 大模型调用
- 教案/讲义/家长反馈/学习计划生成
- Markdown/Word 导出
- 简单 Web 页面

暂不包含：

- 用户登录
- 数据库
- 向量知识库
- PDF 导出
- 多学生管理
- 权限系统

这些会作为下一阶段企业级能力继续扩展。

