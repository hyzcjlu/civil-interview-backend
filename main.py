import json
import os
import time
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

# FastAPI 相关导入
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 原有业务逻辑导入
from data_loader import load_question
from prompt_builder import build_prompt
from post_process import post_process
from mock_data import mock_llm_result
from openai import OpenAI

# ================= 配置区域 =================
USE_MOCK = False  # True: 使用模拟数据; False: 调用真实 API
API_PROVIDER = "QWEN"  # "DEEPSEEK" 或 "QWEN"

# API 密钥配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-your-deepseek-key")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "sk-7ce4eac74f4d4ee889c1132799e27ff8")
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen-plus"

# 内存数据库 (用于演示，生产环境请替换为 SQLite/MySQL)
mock_db = {
    "questions": [],
    "exams": {},
    "history": [],
    "users": {"preferences": {"target_score": 80, "focus_areas": []}}
}

# ===========================================

app = FastAPI(title="公考面试 AI 评分系统 API", version="1.0.0")

# 配置 CORS (允许前端跨域访问)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议指定具体域名 ['http://localhost:3001']
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================= Pydantic 模型定义 =================

class QuestionCreate(BaseModel):
    question: str
    type: str = "single"
    category: str = "general"
    keywords: List[str] = []
    score_criteria: Dict[str, Any] = {}


class QuestionUpdate(BaseModel):
    question: Optional[str] = None
    type: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[List[str]] = None


class ExamStartRequest(BaseModel):
    questionIds: List[str]


class EvaluateRequest(BaseModel):
    examId: str
    questionId: str
    answerText: str
    audioUrl: Optional[str] = None


class UserPreferences(BaseModel):
    target_score: int
    focus_areas: List[str]


# ================= 核心业务逻辑函数 =================

def call_llm_api(prompt: str) -> Optional[Dict]:
    """调用大模型 API (复用原有逻辑)"""
    if API_PROVIDER == "DEEPSEEK":
        api_key = DEEPSEEK_API_KEY
        base_url = DEEPSEEK_BASE_URL
        model = DEEPSEEK_MODEL
    else:
        api_key = QWEN_API_KEY
        base_url = QWEN_BASE_URL
        model = QWEN_MODEL

    if not api_key or api_key.startswith("sk-your"):
        print("❌ 错误：未配置有效的 API Key")
        return None

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个严格的公务员面试评分专家，只输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=2000
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"): content = content[7:]
        if content.endswith("```"): content = content[:-3]
        return json.loads(content)
    except Exception as e:
        print(f"❌ API 调用失败：{e}")
        return None


def process_scoring_logic(question: Dict, answer_text: str) -> Dict:
    """执行评分核心逻辑"""
    prompt = build_prompt(answer_text, question)

    raw_result = {}
    if USE_MOCK:
        raw_result = mock_llm_result
    else:
        raw_result = call_llm_api(prompt)
        if not raw_result:
            raise HTTPException(status_code=500, detail="LLM 评分服务不可用")

    return post_process(raw_result, answer_text, question)


# ================= API 接口实现 =================

# --- 1. 题库管理接口 (/questions) ---

@app.get("/questions")
async def get_questions(category: Optional[str] = None, limit: int = 10):
    """获取题目列表 (对应 questionBank.js getQuestions)"""
    # 如果有真实数据从 DB 查，这里模拟返回
    if USE_MOCK or len(mock_db["questions"]) == 0:
        # 模拟返回一些数据
        return [
            {"id": "q1", "question": "如何看待县长直播带货？", "type": "single", "category": "phenomenon"},
            {"id": "q2", "question": "组织一次乡村振兴调研", "type": "single", "category": "planning"}
        ]
    return mock_db["questions"][:limit]


@app.get("/questions/{question_id}")
async def get_question_by_id(question_id: str):
    """获取单个题目详情 (对应 questionBank.js getQuestionById)"""
    # 模拟查找
    return {"id": question_id, "question": f"题目详情：{question_id}", "type": "single"}


@app.post("/questions")
async def create_question(data: QuestionCreate):
    """创建新题目 (对应 questionBank.js createQuestion)"""
    new_q = data.dict()
    new_q["id"] = f"q_{uuid.uuid4().hex[:8]}"
    new_q["created_at"] = datetime.now().isoformat()
    mock_db["questions"].append(new_q)
    return new_q


@app.put("/questions/{question_id}")
async def update_question(question_id: str, data: QuestionUpdate):
    """更新题目 (对应 questionBank.js updateQuestion)"""
    return {"id": question_id, **data.dict(exclude_unset=True), "updated": True}


@app.delete("/questions/{question_id}")
async def delete_question(question_id: str):
    """删除题目 (对应 questionBank.js deleteQuestion)"""
    return {"success": True, "id": question_id}


@app.post("/questions/import")
async def import_questions(file: UploadFile = File(...)):
    """导入题目 (对应 questionBank.js importQuestions)"""
    # 这里可以添加解析 Excel/JSON 的逻辑
    return {"imported": 10, "failed": 0, "filename": file.filename}


@app.get("/questions/random")
async def get_random_questions(limit: int = 3):
    """获取随机题目 (对应 questionBank.js getRandomQuestions)"""
    return [
        {"id": f"rand_{i}", "question": f"随机题目 {i}", "type": "single"}
        for i in range(limit)
    ]


# --- 2. 考试流程接口 (/exam) ---

@app.post("/exam/start")
async def start_exam(request: ExamStartRequest):
    """开始考试 (对应 exam.js startExam)"""
    exam_id = f"exam_{uuid.uuid4().hex[:8]}"
    mock_db["exams"][exam_id] = {
        "id": exam_id,
        "questionIds": request.questionIds,
        "status": "in_progress",
        "start_time": datetime.now().isoformat(),
        "answers": {}
    }
    return {"examId": exam_id, "status": "started", "questionIds": request.questionIds}


@app.post("/exam/{exam_id}/upload")
async def upload_recording(exam_id: str, recording: UploadFile = File(...)):
    """上传录音 (对应 exam.js uploadRecording)"""
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="考试不存在")

    # 模拟保存文件
    return {"success": True, "url": f"/uploads/{exam_id}_{recording.filename}", "duration": 120}


@app.post("/exam/{exam_id}/complete")
async def complete_exam(exam_id: str):
    """完成考试 (对应 exam.js completeExam)"""
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="考试不存在")

    mock_db["exams"][exam_id]["status"] = "completed"
    mock_db["exams"][exam_id]["end_time"] = datetime.now().isoformat()

    # 添加到历史记录
    mock_db["history"].append({
        "examId": exam_id,
        "date": datetime.now().isoformat(),
        "score": 0,  # 待评分后更新
        "status": "pending_review"
    })

    return {"success": True, "examId": exam_id}


# --- 3. 评分核心接口 (/scoring) ---

@app.post("/scoring/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """语音转文字 (对应 scoring.js transcribeAudio)"""
    # 实际项目中这里调用 Whisper 或其他 ASR 服务
    # 这里模拟返回
    return {
        "text": "模拟转录文本：考生认为应该因地制宜，避免形式主义...",
        "duration": 45.5,
        "confidence": 0.95
    }


@app.post("/scoring/evaluate")
async def evaluate_answer(request: EvaluateRequest):
    """提交答案并获取评分 (对应 scoring.js evaluateAnswer)"""
    # 1. 获取题目 (模拟)
    question = {
        "id": request.questionId,
        "question": "模拟题目内容...",
        "keywords": ["因地制宜", "形式主义", "乡村振兴"],
        "score_criteria": {"logic": 30, "content": 40, "expression": 30}
    }

    # 2. 执行评分
    try:
        result = process_scoring_logic(question, request.answerText)

        # 3. 更新考试记录
        if request.examId in mock_db["exams"]:
            mock_db["exams"][request.examId]["answers"][request.questionId] = {
                "text": request.answerText,
                "score_result": result
            }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scoring/result/{exam_id}/{question_id}")
async def get_scoring_result(exam_id: str, question_id: str):
    """获取评分结果详情 (对应 scoring.js getScoringResult)"""
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="考试不存在")

    exam = mock_db["exams"][exam_id]
    if question_id not in exam.get("answers", {}):
        raise HTTPException(status_code=404, detail="该题目尚未评分")

    return exam["answers"][question_id]["score_result"]


# --- 4. 历史记录接口 (/history) ---

@app.get("/history")
async def get_history_list(page: int = 1, limit: int = 10):
    """获取历史列表 (对应 history.js getHistoryList)"""
    return mock_db["history"][(page - 1) * limit: page * limit]


@app.get("/history/{exam_id}")
async def get_history_detail(exam_id: str):
    """获取历史详情 (对应 history.js getHistoryDetail)"""
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="记录不存在")
    return mock_db["exams"][exam_id]


@app.get("/history/trend")
async def get_history_trend(days: int = 30):
    """获取趋势图数据 (对应 history.js getHistoryTrend)"""
    # 模拟数据
    return [
        {"date": "2023-10-01", "score": 75},
        {"date": "2023-10-05", "score": 78},
        {"date": "2023-10-10", "score": 82}
    ]


@app.get("/history/stats")
async def get_history_stats():
    """获取统计数据 (对应 history.js getHistoryStats)"""
    return {"total_exams": 12, "avg_score": 76.5, "best_score": 88}


# --- 5. 用户接口 (/user) ---

@app.get("/user/info")
async def get_user_info():
    """获取用户信息 (对应 user.js getUserInfo)"""
    return {
        "id": "u_001",
        "name": "考生用户",
        "avatar": "",
        "preferences": mock_db["users"]["preferences"]
    }


@app.put("/user/preferences")
async def update_preferences(data: UserPreferences):
    """更新用户偏好 (对应 user.js updatePreferences)"""
    mock_db["users"]["preferences"] = data.dict()
    return {"success": True}


@app.get("/user/provinces")
async def get_provinces():
    """获取省份列表 (对应 user.js getProvinces)"""
    return [{"code": "41", "name": "河南省"}, {"code": "11", "name": "北京市"}]


# ================= 启动入口 =================

if __name__ == "__main__":
    import uvicorn

    print("🚀 正在启动 API 服务...")
    print(f"📝 模式：{'Mock (模拟)' if USE_MOCK else 'Real API (真实)'}")
    print(f"🔗 地址：http://localhost:8000")
    print(f"📚 文档：http://localhost:8000/docs")

    uvicorn.run(app, host="0.0.0.0", port=8000)