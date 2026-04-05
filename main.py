"""
Refactored Civil Service Interview AI Scoring API (v2.1 - Pydantic V2 Fixed)
修复了 Pydantic V2 的 @validator 弃用警告
"""
import json
import os
import time
import uuid
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# --- Security: Load env vars first (P0.1) ---
load_dotenv()

# --- FastAPI & Pydantic V2 (P2.9) ---
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
# 注意：这里导入了 field_validator
from pydantic import BaseModel, Field, field_validator
from passlib.context import CryptContext
from jose import JWTError, jwt
import logging

# --- LLM & ASR (P0.3, P1.3) ---
from openai import OpenAI
import asyncio

# ================= Configuration =================
# --- Security: Moved to .env (P0.1) ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in .env file")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# API Keys
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

# --- CORS ---
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# --- Logging (P3.16) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= Database Placeholder =================
PERSISTENT_DB_PATH = "db.json"

def load_db():
    if os.path.exists(PERSISTENT_DB_PATH):
        try:
            with open(PERSISTENT_DB_PATH, 'r') as f:
                data = json.load(f)
                for key in ["questions", "exams", "history", "users"]:
                    if key not in data:
                        data[key] = []
                return data
        except Exception as e:
            logger.error(f"Failed to load DB: {e}")
    return {"questions": [], "exams": {}, "history": [], "users": {}}

def save_db(data):
    try:
        with open(PERSISTENT_DB_PATH, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to save DB: {e}")

mock_db = load_db()

# ================= Models (Pydantic V2) =================

# 模拟省份映射
PROVINCE_NAMES = {"zhejiang": "浙江", "national": "全国", "henan": "河南"}

class QuestionCreate(BaseModel):
    stem: str
    dimension: str = "analysis"
    province: str = "national"
    prepTime: int = 90
    answerTime: int = 180
    scoringPoints: List[Dict[str, Any]] = Field(default_factory=list)
    keywords: Dict[str, List[str]] = Field(default_factory=dict)

    # --- Pydantic V2 Style Validator (Fixed) ---
    @field_validator('stem')
    @classmethod
    def stem_not_empty(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('Stem cannot be empty')
        return v

class EvaluateRequest(BaseModel):
    questionId: str
    transcript: str
    examId: Optional[str] = None

    # --- Pydantic V2 Style Validator (Fixed) ---
    @field_validator('transcript')
    @classmethod
    def transcript_length(cls, v):
        if len(v) > 5000:
            raise ValueError('Transcript too long')
        return v

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None

    # --- Pydantic V2 Style Validator (Fixed) ---
    @field_validator('password')
    @classmethod
    def password_strength(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        return v

# ================= JWT & Auth =================
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class AuthUser(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(AuthUser):
    hashed_password: str

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# 模拟用户数据库
fake_users_db = {
    "testuser": {
        "username": "testuser",
        "full_name": "Test User",
        "email": "test@example.com",
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        "disabled": False,
    },
    "hanhan": {
        "username": "hanhan",
        "full_name": "hanhan",
        "email": "",
        "hashed_password": "$2b$12$stxYEqkAA2ZjahnaZRoPYO5f6FTbc7e.dhHvNN5eqm/Bcy8xYR3NG",
        "disabled": False,
    }
}

def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)

def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    # (P2.10) datetime.utcnow() -> datetime.now(timezone.utc)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

# ================= LLM Logic =================
client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)

def build_prompt(answer_text: str, question: Dict, province_name: str = "national") -> str:
    return f"""
    You are a strict civil service interview scoring expert for {province_name}.
    Evaluate the following answer based on the question and criteria.
    
    Question: {question.get('stem', '')}
    Expected Points: {json.dumps(question.get('scoringPoints', []))}
    
    Candidate Answer: {answer_text}
    
    Output JSON only with scores for each dimension.
    """

def call_llm_api(prompt: str, system_msg: str = None, temperature: float = 0.1, max_tokens: int = 2000) -> Optional[Dict]:
    if not QWEN_API_KEY:
        logger.error("[ERROR] API Key not configured")
        return None
    if system_msg is None:
        system_msg = "You are a civil service interview expert. Output JSON only."

    try:
        response = client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content)
    except Exception as e:
        logger.error(f"[ERROR] API call failed: {e}")
        return None

class LLMResponseSchema(BaseModel):
    total_score: float
    dimension_scores: Dict[str, float]
    rationale: str

def validate_llm_response(raw_json: Dict):
    try:
        return LLMResponseSchema(**raw_json)
    except Exception as e:
        logger.error(f"LLM Response validation error: {e}")
        return None

# ================= ASR Integration =================
async def transcribe_audio_file(audio_bytes: bytes) -> str:
    try:
        await asyncio.sleep(1) # 模拟处理延迟
        if b"noise" in audio_bytes:
            return "This is a noisy recording, I cannot hear clearly."
        # (P2.10) datetime.utcnow() -> datetime.now(timezone.utc)
        return f"Transcribed: Candidate is discussing a topic relevant to the exam. Dynamic transcript generated at {datetime.now(timezone.utc)}."
    except Exception as e:
        logger.error(f"ASR Error: {e}")
        raise HTTPException(status_code=500, detail="Transcription failed")

# ================= API App =================
app = FastAPI(title="Civil Service Interview AI Scoring API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 0. Auth ---
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register")
async def register_user(data: RegisterRequest):
    if data.username in fake_users_db:
        raise HTTPException(status_code=400, detail="Username already registered")
    fake_users_db[data.username] = {
        "username": data.username,
        "full_name": data.full_name or data.username,
        "email": data.email or "",
        "hashed_password": get_password_hash(data.password),
        "disabled": False,
    }
    save_db(mock_db)
    return {"success": True, "message": "User created successfully"}

# --- 1. Scoring & Exam Fixes ---
@app.post("/scoring/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    try:
        audio_bytes = await audio.read()
        transcript = await transcribe_audio_file(audio_bytes)
        return {
            "transcript": transcript,
            "duration": len(transcript) / 10
        }
    except Exception as e:
        logger.error(f"Transcription endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Transcription service error")

@app.post("/scoring/evaluate")
async def evaluate_answer(request: EvaluateRequest, current_user: AuthUser = Depends(get_current_user)):
    question = next((q for q in mock_db["questions"] if q["id"] == request.questionId), None)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    province_code = question.get("province", "national")
    province_name = PROVINCE_NAMES.get(province_code, province_code).title()

    prompt = build_prompt(request.transcript, question, province_name)
    raw_result = call_llm_api(prompt)

    if not raw_result:
        raise HTTPException(status_code=500, detail="LLM service unavailable")

    validated = validate_llm_response(raw_result)
    if not validated:
        raise HTTPException(status_code=500, detail="Invalid response format from AI")

    dim_scores = raw_result.get("dimension_scores", {})
    frontend_dims = []
    total = 0
    max_score = 30

    dim_mapping = {
        "analysis": "综合分析",
        "practical": "实务落地",
        "emergency": "应急应变",
        "legal": "法治思维",
        "logic": "逻辑结构",
        "expression": "语言表达"
    }

    for key, display_name in dim_mapping.items():
        score = dim_scores.get(key, dim_scores.get(display_name, 0))
        frontend_dims.append({
            "name": display_name,
            "key": key,
            "score": round(score, 2),
            "maxScore": 20 if key in ["analysis", "practical"] else 15,
            "lostReasons": []
        })
        total += score

    grade = "B"
    if total / max_score > 0.85:
        grade = "A"

    result = {
        "totalScore": round(total, 2),
        "maxScore": max_score,
        "grade": grade,
        "dimensions": frontend_dims,
        "aiComment": raw_result.get("rationale", "No comment"),
    }

    exam_id = request.examId
    if exam_id and exam_id in mock_db["exams"]:
        if "answers" not in mock_db["exams"][exam_id]:
            mock_db["exams"][exam_id]["answers"] = {}
        mock_db["exams"][exam_id]["answers"][request.questionId] = {
            "text": request.transcript,
            "score_result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        save_db(mock_db)

    return result

@app.post("/exam/{exam_id}/complete")
async def complete_exam(exam_id: str, current_user: AuthUser = Depends(get_current_user)):
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="Exam not found")

    exam = mock_db["exams"][exam_id]
    exam["status"] = "completed"
    exam["endTime"] = datetime.now(timezone.utc).isoformat()

    total_score = 0
    question_count = 0
    for q_id, answer_data in exam.get("answers", {}).items():
        score_data = answer_data.get("score_result", {})
        total_score += score_data.get("totalScore", 0)
        question_count += 1

    avg_score = total_score / question_count if question_count > 0 else 0

    history_record = {
        "examId": exam_id,
        "date": exam["endTime"],
        "questionCount": question_count,
        "totalScore": round(avg_score, 2),
        "maxScore": 100,
        "grade": "B",
        "province": "national",
        "dimensions": [],
        "questionSummary": f"Completed Exam: {exam_id}"
    }
    mock_db["history"].append(history_record)
    save_db(mock_db)

    return {"success": True, "finalScore": avg_score}

# --- User Profile APIs (Added) ---
class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None

@app.get("/user/info")
async def get_user_info(current_user: AuthUser = Depends(get_current_user)):
    """获取当前登录用户的信息"""
    if current_user.username not in fake_users_db:
        raise HTTPException(status_code=404, detail="用户未找到")
    user_data = fake_users_db[current_user.username]
    return {
        "id": user_data["username"],
        "name": user_data.get("full_name", user_data["username"]),
        "avatar": user_data.get("avatar", ""),
        "province": user_data.get("province", "national"),
        "email": user_data.get("email", "")
    }

@app.put("/user/profile")
async def update_user_profile(data: UserProfileUpdate, current_user: AuthUser = Depends(get_current_user)):
    """更新用户资料"""
    if current_user.username not in fake_users_db:
        raise HTTPException(status_code=404, detail="用户未找到")
    user_data = fake_users_db[current_user.username]
    if data.full_name is not None:
        user_data["full_name"] = data.full_name
    if data.email is not None:
        user_data["email"] = data.email
    return {"success": True, "message": "信息已更新"}

@app.put("/user/password")
async def change_password(data: dict, current_user: AuthUser = Depends(get_current_user)):
    """修改密码"""
    if current_user.username not in fake_users_db:
        raise HTTPException(status_code=404, detail="用户未找到")
    user_data = fake_users_db[current_user.username]
    # Verify old password
    if not verify_password(data.get("old_password"), user_data["hashed_password"]):
        raise HTTPException(status_code=400, detail="原密码错误")
    # Update password
    user_data["hashed_password"] = get_password_hash(data.get("new_password"))
    return {"success": True, "message": "密码修改成功"}

@app.get("/user/provinces")
async def get_provinces():
    """获取省份列表"""
    return [
        {"code": "national", "name": "国家公务员考试"},
        {"code": "beijing", "name": "北京"},
        {"code": "guangdong", "name": "广东"},
        {"code": "zhejiang", "name": "浙江"},
        {"code": "sichuan", "name": "四川"},
        {"code": "jiangsu", "name": "江苏"},
        {"code": "henan", "name": "河南"},
        {"code": "shandong", "name": "山东"}
    ]

@app.get("/user/me")
async def get_current_user_info(current_user: AuthUser = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "email": current_user.email
    }

@app.get("/history")
async def get_history(current: int = 1, pageSize: int = 10, total: int = 0, current_user: AuthUser = Depends(get_current_user)):
    """获取历史记录列表"""
    history_list = mock_db.get("history", [])
    # 分页
    start = (current - 1) * pageSize
    end = start + pageSize
    paginated = history_list[start:end]
    return {
        "list": paginated,
        "total": len(history_list),
        "current": current,
        "pageSize": pageSize
    }

@app.get("/history/stats")
async def get_history_stats(current_user: AuthUser = Depends(get_current_user)):
    """获取历史统计"""
    history_list = mock_db.get("history", [])

    # 维度定义（与前端 constants.js 对齐）
    dim_defs = [
        {"key": "legal", "name": "法治思维", "maxScore": 20},
        {"key": "practical", "name": "实务落地", "maxScore": 20},
        {"key": "logic", "name": "逻辑结构", "maxScore": 15},
        {"key": "expression", "name": "语言表达", "maxScore": 15},
        {"key": "analysis", "name": "综合分析", "maxScore": 15},
        {"key": "emergency", "name": "应急应变", "maxScore": 15},
    ]

    if not history_list:
        dimension_averages = [
            {"name": d["name"], "avg": 0, "maxScore": d["maxScore"]}
            for d in dim_defs
        ]
        return {
            "totalExams": 0,
            "avgScore": 0,
            "bestScore": 0,
            "weakestDimension": "",
            "dimensionAverages": dimension_averages,
        }

    scores = [h.get("totalScore", 0) for h in history_list]

    # 计算各维度平均分
    dim_totals = {d["name"]: [] for d in dim_defs}
    for h in history_list:
        for dim in h.get("dimensions", []):
            name = dim.get("name")
            if name in dim_totals:
                dim_totals[name].append(dim.get("score", 0))

    dimension_averages = []
    for d in dim_defs:
        vals = dim_totals[d["name"]]
        avg = round(sum(vals) / len(vals), 2) if vals else 0
        dimension_averages.append({
            "name": d["name"],
            "avg": avg,
            "maxScore": d["maxScore"],
        })

    # 找出薄弱维度（得分百分比最低的）
    weakest = ""
    lowest_pct = 100
    for da in dimension_averages:
        if da["maxScore"] > 0 and da["avg"] > 0:
            pct = da["avg"] / da["maxScore"] * 100
            if pct < lowest_pct:
                lowest_pct = pct
                weakest = da["name"]

    return {
        "totalExams": len(history_list),
        "avgScore": round(sum(scores) / len(scores), 2),
        "bestScore": max(scores) if scores else 0,
        "weakestDimension": weakest,
        "dimensionAverages": dimension_averages,
    }

@app.get("/history/trend")
async def get_history_trend(days: int = 30, current_user: AuthUser = Depends(get_current_user)):
    """获取历史趋势"""
    # 返回模拟趋势数据
    import random
    trend = []
    for i in range(min(days, 7)):
        trend.append({
            "date": (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d"),
            "score": random.randint(60, 95)
        })
    return trend[::-1]  # 倒序

if __name__ == "__main__":
    import uvicorn
    logger.info("[START] API server starting...")
    logger.info(f"[URL] http://localhost:8050")
    uvicorn.run(app, host="127.0.0.1", port=8050)