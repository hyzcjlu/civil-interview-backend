import json
import os
import time
import uuid
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# JWT auth
from passlib.context import CryptContext
from jose import JWTError, jwt

# FastAPI
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# LLM
from data_loader import load_question
from prompt_builder import build_prompt
from post_process import post_process
from mock_data import mock_llm_result
from openai import OpenAI

# ================= Config =================
USE_MOCK = False
API_PROVIDER = "QWEN"

# JWT config
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-your-deepseek-key")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "sk-7ce4eac74f4d4ee889c1132799e27ff8")
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen-plus"

# User DB (password: "secret")
fake_users_db = {
    "testuser": {
        "username": "testuser",
        "full_name": "Test User",
        "email": "test@example.com",
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        "disabled": False,
    }
}

# ================= Position Systems =================

POSITION_SYSTEMS = [
    {"code": "tax", "name": "税务系统", "focus": "税收政策执行、纳税服务、税法应用"},
    {"code": "customs", "name": "海关系统", "focus": "进出口监管、通关便利化、走私打击"},
    {"code": "police", "name": "公安系统", "focus": "社会治安、群众工作、执法规范化"},
    {"code": "court", "name": "法院系统", "focus": "司法公正、案件审理、法律适用"},
    {"code": "procurate", "name": "检察系统", "focus": "法律监督、公益诉讼、检察改革"},
    {"code": "market", "name": "市场监管", "focus": "市场秩序、食品安全、消费者权益"},
    {"code": "general", "name": "综合管理", "focus": "行政管理、政策执行、综合协调"},
    {"code": "township", "name": "乡镇基层", "focus": "基层治理、乡村振兴、群众服务"},
    {"code": "finance", "name": "银保监会", "focus": "金融监管、风险防控、金融消费者保护"},
    {"code": "diplomacy", "name": "外交系统", "focus": "外交礼仪、国际关系、跨文化沟通"},
]

PROVINCE_NAMES = {
    "national": "国考", "beijing": "北京", "shanghai": "上海",
    "guangdong": "广东", "jiangsu": "江苏", "zhejiang": "浙江",
    "shandong": "山东", "sichuan": "四川", "hubei": "湖北",
    "hunan": "湖南", "henan": "河南", "hebei": "河北",
    "fujian": "福建", "anhui": "安徽", "liaoning": "辽宁",
    "shaanxi": "陕西",
}

# ================= Sample Data =================

SAMPLE_QUESTIONS = [
    {
        "id": "q001",
        "stem": "某县看到另一个县的县长直播带货取得了成功，于是市里出台政策要求所有县都开展类似的直播带货活动，并进行排名通报。你怎么看待这一现象？",
        "dimension": "analysis",
        "province": "national",
        "prepTime": 90,
        "answerTime": 180,
        "scoringPoints": [
            {"content": "准确识别盲目跟风和形式主义的核心问题", "score": 8},
            {"content": "全面分析根源、危害和积极方面", "score": 7},
            {"content": "提出科学的、因地制宜的、可操作的措施（至少4条）", "score": 8},
            {"content": "逻辑清晰，语言规范，符合公务员表达标准", "score": 5},
            {"content": "有创新思维和独到见解", "score": 2}
        ],
        "synonyms": ["直播带货", "县长", "电商"],
        "keywords": {
            "scoring": ["政策创新", "政策执行", "县域经济", "为民服务", "因地制宜", "科学决策"],
            "deducting": ["一刀切", "形式主义", "盲目跟风", "为播而播"],
            "bonus": ["分类赋能", "第三方评估", "一播多效", "一县一策"]
        }
    },
    {
        "id": "q002",
        "stem": "请组织一次乡村振兴调研活动，你将如何策划和实施？",
        "dimension": "practical",
        "province": "national",
        "prepTime": 90,
        "answerTime": 180,
        "scoringPoints": [
            {"content": "调研目标和范围界定清晰", "score": 6},
            {"content": "团队组建和任务分工合理", "score": 6},
            {"content": "调研计划详细，包含时间线和方法", "score": 8},
            {"content": "数据分析和报告撰写方案完整", "score": 5},
            {"content": "风险管理和应急预案到位", "score": 5}
        ],
        "synonyms": ["乡村振兴", "调研", "调查研究"],
        "keywords": {
            "scoring": ["乡村振兴", "调研方案", "数据分析", "实地调查", "问卷调查"],
            "deducting": ["浮于表面", "形式化", "缺乏细节"],
            "bonus": ["创新方法", "数字化工具", "多方参与"]
        }
    },
    {
        "id": "q003",
        "stem": "作为一名社区工作者，小区内居民因噪音问题产生纠纷，你将如何处理？",
        "dimension": "emergency",
        "province": "national",
        "prepTime": 90,
        "answerTime": 180,
        "scoringPoints": [
            {"content": "快速评估情况并识别关键当事人", "score": 6},
            {"content": "展现共情能力和有效沟通技巧", "score": 7},
            {"content": "提出公平合理的调解方案", "score": 7},
            {"content": "跟进长效预防措施", "score": 5},
            {"content": "必要时的上报流程得当", "score": 5}
        ],
        "synonyms": ["社区", "噪音", "纠纷调解"],
        "keywords": {
            "scoring": ["调解", "沟通", "居民权益", "社区和谐", "依法治理"],
            "deducting": ["偏袒一方", "忽视居民", "缺乏同理心"],
            "bonus": ["居民公约", "志愿者团队", "智慧社区平台"]
        }
    },
    {
        "id": "q004",
        "stem": "请谈谈法治在基层治理中的重要性，以及如何有效推进基层法治建设？",
        "dimension": "legal",
        "province": "national",
        "prepTime": 90,
        "answerTime": 180,
        "scoringPoints": [
            {"content": "对法治原则有清晰理解", "score": 7},
            {"content": "准确识别当前基层治理中的挑战", "score": 6},
            {"content": "提出具体的推进措施", "score": 7},
            {"content": "法治与乡土习俗之间的平衡", "score": 5},
            {"content": "监督和评估机制完善", "score": 5}
        ],
        "synonyms": ["法治", "基层", "治理"],
        "keywords": {
            "scoring": ["依法治国", "法治意识", "基层治理", "法律援助", "公众参与"],
            "deducting": ["内容空泛", "缺乏法律依据", "不切实际"],
            "bonus": ["法律科技", "典型案例", "比较分析"]
        }
    }
]

# In-memory DB
mock_db = {
    "questions": SAMPLE_QUESTIONS,
    "exams": {},
    "history": [],
    "users": {
        "info": {
            "id": "user_001",
            "name": "考生A",
            "avatar": "",
            "province": "national"
        },
        "preferences": {
            "defaultPrepTime": 90,
            "defaultAnswerTime": 180,
            "enableVideo": True
        }
    }
}

# Pre-populate some history
for i in range(8):
    d = datetime.now() - timedelta(days=8 - i)
    mock_db["history"].append({
        "examId": f"exam_{1000 + i}",
        "date": d.isoformat(),
        "questionCount": random.randint(3, 5),
        "totalScore": random.randint(60, 95),
        "maxScore": 100,
        "grade": random.choice(["A", "B", "C"]),
        "province": "national",
        "dimensions": [
            {"name": "法治思维", "score": random.randint(10, 20), "maxScore": 20},
            {"name": "实务落地", "score": random.randint(10, 20), "maxScore": 20},
            {"name": "逻辑结构", "score": random.randint(8, 15), "maxScore": 15},
            {"name": "语言表达", "score": random.randint(8, 15), "maxScore": 15},
            {"name": "综合分析", "score": random.randint(8, 15), "maxScore": 15},
            {"name": "应急应变", "score": random.randint(8, 15), "maxScore": 15},
        ],
        "questionSummary": f"模拟练习 #{i + 1}"
    })

# ===========================================

app = FastAPI(title="Civil Service Interview AI Scoring API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================= Pydantic Models =================

class QuestionCreate(BaseModel):
    stem: str
    dimension: str = "analysis"
    province: str = "national"
    prepTime: int = 90
    answerTime: int = 180
    scoringPoints: List[Dict[str, Any]] = []
    keywords: Dict[str, List[str]] = {}


class QuestionUpdate(BaseModel):
    stem: Optional[str] = None
    dimension: Optional[str] = None
    province: Optional[str] = None
    keywords: Optional[Dict[str, List[str]]] = None


class ExamStartRequest(BaseModel):
    questionIds: List[str]


class EvaluateRequest(BaseModel):
    questionId: str
    transcript: str
    examId: Optional[str] = None


class UserPreferences(BaseModel):
    defaultPrepTime: Optional[int] = 90
    defaultAnswerTime: Optional[int] = 180
    enableVideo: Optional[bool] = True


# ================= JWT Auth =================

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


def get_user(db, username: str):
    if username in db:
        return UserInDB(**db[username])


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
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
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=username)
    if user is None:
        raise credentials_exception
    return user


# ================= LLM Logic =================

def call_llm_api(prompt: str, system_msg: str = None, temperature: float = 0.1, max_tokens: int = 2000) -> Optional[Dict]:
    if API_PROVIDER == "DEEPSEEK":
        api_key, base_url, model = DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    else:
        api_key, base_url, model = QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL

    if not api_key or api_key.startswith("sk-your"):
        print("[ERROR] API Key not configured")
        return None

    if system_msg is None:
        system_msg = "You are a strict civil service interview scoring expert. Output JSON only."

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"): content = content[7:]
        if content.endswith("```"): content = content[:-3]
        return json.loads(content)
    except Exception as e:
        print(f"[ERROR] API call failed: {e}")
        return None


def build_focus_prompt(province_name: str, position_name: str, position_focus: str) -> str:
    """构建定向备面重点分析的 LLM prompt"""
    return f"""你是一位资深的公务员面试培训专家，精通全国各省公务员面试的考情和命题规律。

请针对以下省份和岗位，分析面试重点和备考策略：

【省份】{province_name}
【岗位系统】{position_name}
【岗位核心职能】{position_focus}

请输出一个标准 JSON 对象，结构如下：
{{
    "coreFocus": [
        {{
            "name": "重点能力名称",
            "weight": 权重百分比（整数，所有权重之和为100）,
            "desc": "简要说明为什么这是面试重点"
        }}
    ],
    "highFreqTypes": [
        {{
            "type": "题型名称（如综合分析、组织管理、应急应变等）",
            "frequency": "高/中/低",
            "example": "一道典型例题的题干"
        }}
    ],
    "hotTopics": ["近期热门考试话题1", "热门话题2", "热门话题3"],
    "strategy": ["备考建议1", "备考建议2", "备考建议3"]
}}

要求：
1. coreFocus 包含3-5项，按权重从高到低排列
2. highFreqTypes 包含3-4种高频题型
3. hotTopics 包含3-5个近期热门话题，结合该省份和岗位特点
4. strategy 包含3-4条具体的备考建议
5. 所有内容必须紧密围绕该省份和岗位的特点，不要泛泛而谈
6. 仅输出 JSON，不要有任何其他文字"""


def build_question_generate_prompt(province_name: str, position_name: str, position_focus: str, count: int) -> str:
    """构建动态题目生成的 LLM prompt"""
    return f"""你是一位资深的公务员面试命题专家，请为以下省份和岗位生成{count}道高质量面试模拟题。

【省份】{province_name}
【岗位系统】{position_name}
【岗位核心职能】{position_focus}

请输出一个 JSON 数组，每个元素结构如下：
[
    {{
        "stem": "面试题目的完整题干",
        "dimension": "主要考察维度（analysis/practical/emergency/legal 之一）",
        "scoringPoints": [
            {{"content": "采分点描述", "score": 分值（整数）}}
        ],
        "keywords": {{
            "scoring": ["核心采分关键词"],
            "deducting": ["扣分陷阱关键词"],
            "bonus": ["加分亮点关键词"]
        }}
    }}
]

要求：
1. 题目必须紧密结合{province_name}{position_name}的实际工作场景
2. 每道题的 scoringPoints 分值总和为30分，包含3-5个采分点
3. dimension 必须是 analysis、practical、emergency、legal 之一
4. 题目涵盖不同的 dimension 类型
5. 关键词要具体、与题目紧密相关
6. 仅输出 JSON 数组，不要有任何其他文字"""


def build_training_prompt(dimension_name: str, count: int) -> str:
    """构建专项训练题目生成的 LLM prompt"""
    dim_desc = {
        "legal": "法治思维：考察考生对法律法规的理解和运用能力",
        "practical": "实务落地：考察考生将理论转化为实际工作方案的能力",
        "logic": "逻辑结构：考察考生答题的条理性和逻辑性",
        "expression": "语言表达：考察考生的口头表达能力和用词规范性",
        "analysis": "综合分析：考察考生全面分析问题的能力",
        "emergency": "应急应变：考察考生应对突发事件的能力"
    }
    desc = dim_desc.get(dimension_name, f"维度：{dimension_name}")

    return f"""你是一位资深的公务员面试命题专家，请针对以下能力维度生成{count}道专项训练题目。

【训练维度】{desc}

请输出一个 JSON 数组，每个元素结构如下：
[
    {{
        "stem": "面试题目的完整题干",
        "dimension": "{dimension_name}",
        "scoringPoints": [
            {{"content": "采分点描述", "score": 分值（整数）}}
        ],
        "keywords": {{
            "scoring": ["核心采分关键词"],
            "deducting": ["扣分陷阱关键词"],
            "bonus": ["加分亮点关键词"]
        }}
    }}
]

要求：
1. 每道题必须集中考察"{desc}"维度
2. 每道题的 scoringPoints 分值总和为30分，包含3-5个采分点
3. 题目难度适中，适合备考训练
4. 关键词要具体、与题目紧密相关
5. 仅输出 JSON 数组，不要有任何其他文字"""


def process_scoring_logic(question: Dict, answer_text: str) -> Dict:
    prompt = build_prompt(answer_text, question)

    if USE_MOCK:
        raw_result = mock_llm_result
    else:
        raw_result = call_llm_api(prompt)
        if not raw_result:
            raise HTTPException(status_code=500, detail="LLM scoring service unavailable")

    return post_process(raw_result, answer_text, question)


def transform_llm_to_frontend(llm_result: Dict, question: Dict) -> Dict:
    """Transform LLM/post_process result to frontend-expected format."""
    dim_scores = llm_result.get("dimension_scores", {})
    matched = llm_result.get("matched_keywords", {})

    dimensions = []
    dim_keys = ["legal", "practical", "logic", "expression", "analysis", "emergency"]
    for i, (name, score) in enumerate(dim_scores.items()):
        key = dim_keys[i] if i < len(dim_keys) else f"dim_{i}"
        max_score = 20 if i < 2 else 15
        lost = []
        for detail in llm_result.get("deduction_details", []):
            if name in detail or (i == 0 and detail):
                lost.append(detail)
        dimensions.append({
            "name": name,
            "key": key,
            "score": score,
            "maxScore": max_score,
            "lostReasons": lost if lost else ["无明显问题"]
        })

    total = llm_result.get("total_score", sum(dim_scores.values()))
    max_score = question.get("fullScore", 100)

    ratio = total / max_score if max_score > 0 else 0
    if ratio >= 0.85:
        grade = "A"
    elif ratio >= 0.7:
        grade = "B"
    elif ratio >= 0.5:
        grade = "C"
    else:
        grade = "D"

    scoring_kw = [{"word": w, "inTranscript": True, "score": 3} for w in matched.get("core", [])]
    deducting_kw = [{"word": w, "inTranscript": True, "penalty": -2} for w in matched.get("penalty", [])]
    bonus_kw = [{"word": w, "inTranscript": True, "bonus": 2} for w in matched.get("bonus", [])]

    return {
        "totalScore": total,
        "maxScore": max_score,
        "grade": grade,
        "dimensions": dimensions,
        "matchedKeywords": {
            "scoring": scoring_kw,
            "deducting": deducting_kw,
            "bonus": bonus_kw
        },
        "aiComment": llm_result.get("rationale", ""),
        "highlightedTranscript": ""
    }


# ================= API Routes =================

# --- 0. Auth (JWT Login & Register) ---

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None


class TargetedFocusRequest(BaseModel):
    province: str
    position: str


class QuestionGenerateRequest(BaseModel):
    province: str
    position: str
    count: int = 5


class TrainingGenerateRequest(BaseModel):
    dimension: str
    count: int = 3


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
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
        raise HTTPException(status_code=400, detail="用户名已存在")
    if not data.username or not data.password:
        raise HTTPException(status_code=400, detail="请填写完整信息")
    fake_users_db[data.username] = {
        "username": data.username,
        "full_name": data.full_name or data.username,
        "email": data.email or "",
        "hashed_password": get_password_hash(data.password),
        "disabled": False,
    }
    return {"success": True, "message": "注册成功"}


# --- 1. Questions ---

@app.get("/questions")
async def get_questions(
    province: Optional[str] = None,
    dimension: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    pageSize: int = 10
):
    questions = mock_db["questions"]
    if province and province != "all":
        questions = [q for q in questions if q.get("province") == province]
    if dimension:
        questions = [q for q in questions if q.get("dimension") == dimension]
    if keyword:
        questions = [q for q in questions if keyword.lower() in q.get("stem", "").lower()]

    total = len(questions)
    start = (page - 1) * pageSize
    paged = questions[start:start + pageSize]

    return {"list": paged, "total": total, "page": page, "pageSize": pageSize}


@app.get("/questions/random")
async def get_random_questions(count: int = 3, province: Optional[str] = None):
    questions = mock_db["questions"]
    if province and province != "all":
        questions = [q for q in questions if q.get("province") == province]
    picked = random.sample(questions, min(count, len(questions)))
    return picked


@app.get("/questions/{question_id}")
async def get_question_by_id(question_id: str):
    for q in mock_db["questions"]:
        if q["id"] == question_id:
            return q
    raise HTTPException(status_code=404, detail="题目未找到")

@app.post("/questions")
async def create_question(data: QuestionCreate):
    new_q = data.dict()
    new_q["id"] = f"q_{uuid.uuid4().hex[:8]}"
    mock_db["questions"].append(new_q)
    return new_q


@app.put("/questions/{question_id}")
async def update_question(question_id: str, data: QuestionUpdate):
    for q in mock_db["questions"]:
        if q["id"] == question_id:
            updates = data.dict(exclude_unset=True)
            q.update(updates)
            return q
    raise HTTPException(status_code=404, detail="题目未找到")

@app.delete("/questions/{question_id}")
async def delete_question(question_id: str):
    mock_db["questions"] = [q for q in mock_db["questions"] if q["id"] != question_id]
    return {"success": True, "id": question_id}


@app.post("/questions/import")
async def import_questions(file: UploadFile = File(...)):
    return {"imported": 10, "failed": 0, "filename": file.filename}


# --- 1.5. Targeted Prep & Question Generation ---

@app.get("/positions")
async def get_positions():
    """返回岗位系统列表"""
    return [{"code": p["code"], "name": p["name"]} for p in POSITION_SYSTEMS]


@app.post("/targeted/focus")
async def get_targeted_focus(request: TargetedFocusRequest):
    """定向备面：分析面试重点"""
    province_name = PROVINCE_NAMES.get(request.province, request.province)
    position_info = next((p for p in POSITION_SYSTEMS if p["code"] == request.position), None)
    if not position_info:
        raise HTTPException(status_code=400, detail="未知的岗位系统")

    position_name = position_info["name"]
    position_focus = position_info["focus"]

    if USE_MOCK:
        return {
            "coreFocus": [
                {"name": f"{position_name}核心业务能力", "weight": 30, "desc": f"考察考生对{position_focus}的理解和实际应用能力"},
                {"name": "为民服务意识", "weight": 25, "desc": "考察为群众提供优质服务的意识和方法"},
                {"name": "廉政风险防范", "weight": 20, "desc": "考察在执法过程中的廉洁自律意识"},
                {"name": "团队协作能力", "weight": 15, "desc": "考察与同事协作、沟通协调的能力"},
                {"name": "学习创新能力", "weight": 10, "desc": "考察持续学习和创新工作方法的意识"}
            ],
            "highFreqTypes": [
                {"type": "综合分析", "frequency": "高", "example": f"谈谈你对{province_name}{position_name}改革的看法"},
                {"type": "应急应变", "frequency": "高", "example": f"在{position_name}工作中遇到群众情绪激动，你如何处理？"},
                {"type": "组织管理", "frequency": "中", "example": f"请组织一次{position_name}领域的专项整治活动"},
                {"type": "人际沟通", "frequency": "中", "example": "同事对你的工作方式有意见，你怎么办？"}
            ],
            "hotTopics": [f"{province_name}营商环境优化", f"{position_name}数字化转型", "基层减负增效"],
            "strategy": [
                f"熟悉{position_name}的最新政策和法规",
                f"关注{province_name}经济发展重点和社会热点",
                f"练习{position_name}相关的服务类和执法类场景题",
                "强化应急应变能力训练，注意答题结构完整性"
            ]
        }

    prompt = build_focus_prompt(province_name, position_name, position_focus)
    result = call_llm_api(
        prompt,
        system_msg="你是一位资深的公务员面试培训专家，精通各省公务员面试考情。请输出标准JSON。",
        temperature=0.3,
        max_tokens=3000
    )
    if not result:
        raise HTTPException(status_code=500, detail="AI分析服务暂时不可用")
    return result


@app.post("/questions/generate")
async def generate_questions(request: QuestionGenerateRequest):
    """定向备面：LLM 动态生成面试题"""
    province_name = PROVINCE_NAMES.get(request.province, request.province)
    position_info = next((p for p in POSITION_SYSTEMS if p["code"] == request.position), None)
    if not position_info:
        raise HTTPException(status_code=400, detail="未知的岗位系统")

    position_name = position_info["name"]
    position_focus = position_info["focus"]
    count = min(request.count, 10)  # 限制最多10题

    if USE_MOCK:
        dims = ["analysis", "practical", "emergency", "legal"]
        questions = []
        for i in range(count):
            dim = dims[i % len(dims)]
            questions.append({
                "id": f"gen_{uuid.uuid4().hex[:8]}",
                "stem": f"[{province_name}·{position_name}] 模拟题{i+1}：请结合{position_name}的实际工作，谈谈你对{position_focus.split('、')[0]}的理解和看法。",
                "dimension": dim,
                "province": request.province,
                "prepTime": 90,
                "answerTime": 180,
                "scoringPoints": [
                    {"content": "准确把握核心问题", "score": 8},
                    {"content": "分析全面有深度", "score": 7},
                    {"content": "措施具体可操作", "score": 8},
                    {"content": "语言规范，逻辑清晰", "score": 7}
                ],
                "keywords": {
                    "scoring": ["因地制宜", "科学决策", "为民服务"],
                    "deducting": ["一刀切", "形式主义"],
                    "bonus": ["创新举措", "数据支撑"]
                }
            })
        return questions

    prompt = build_question_generate_prompt(province_name, position_name, position_focus, count)
    result = call_llm_api(
        prompt,
        system_msg="你是一位资深的公务员面试命题专家。请输出标准JSON数组。",
        temperature=0.7,
        max_tokens=4000
    )
    if not result:
        raise HTTPException(status_code=500, detail="题目生成服务暂时不可用")

    # 为每道题补充 id、province、prepTime、answerTime
    if isinstance(result, list):
        for q in result:
            q["id"] = f"gen_{uuid.uuid4().hex[:8]}"
            q["province"] = request.province
            q["prepTime"] = q.get("prepTime", 90)
            q["answerTime"] = q.get("answerTime", 180)
    return result


@app.post("/training/generate")
async def generate_training_questions(request: TrainingGenerateRequest):
    """专项训练：按维度生成训练题"""
    count = min(request.count, 10)

    if USE_MOCK:
        dim_names = {
            "legal": "法治思维", "practical": "实务落地",
            "logic": "逻辑结构", "expression": "语言表达",
            "analysis": "综合分析", "emergency": "应急应变"
        }
        dim_name = dim_names.get(request.dimension, request.dimension)
        questions = []
        for i in range(count):
            questions.append({
                "id": f"train_{uuid.uuid4().hex[:8]}",
                "stem": f"[{dim_name}专项] 训练题{i+1}：请就{dim_name}相关的实际工作场景进行分析和阐述。",
                "dimension": request.dimension,
                "province": "national",
                "prepTime": 90,
                "answerTime": 180,
                "scoringPoints": [
                    {"content": f"{dim_name}运用准确", "score": 10},
                    {"content": "分析有深度", "score": 10},
                    {"content": "表达清晰规范", "score": 10}
                ],
                "keywords": {
                    "scoring": ["准确把握", "全面分析"],
                    "deducting": ["偏离主题", "逻辑混乱"],
                    "bonus": ["独到见解", "案例引用"]
                }
            })
        return questions

    prompt = build_training_prompt(request.dimension, count)
    result = call_llm_api(
        prompt,
        system_msg="你是一位资深的公务员面试命题专家。请输出标准JSON数组。",
        temperature=0.7,
        max_tokens=4000
    )
    if not result:
        raise HTTPException(status_code=500, detail="训练题生成服务暂时不可用")

    if isinstance(result, list):
        for q in result:
            q["id"] = f"train_{uuid.uuid4().hex[:8]}"
            q["dimension"] = request.dimension
            q["province"] = "national"
            q["prepTime"] = q.get("prepTime", 90)
            q["answerTime"] = q.get("answerTime", 180)
    return result


# --- 2. Exam ---

@app.post("/exam/start")
async def start_exam(request: ExamStartRequest):
    exam_id = f"exam_{int(time.time() * 1000)}"
    mock_db["exams"][exam_id] = {
        "id": exam_id,
        "questionIds": request.questionIds,
        "status": "in_progress",
        "startTime": datetime.now().isoformat(),
        "answers": {}
    }
    return {
        "examId": exam_id,
        "questionIds": request.questionIds,
        "startTime": datetime.now().isoformat()
    }


@app.post("/exam/{exam_id}/upload")
async def upload_recording(exam_id: str, recording: UploadFile = File(...)):
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="考试未找到")
    return {"success": True, "fileUrl": f"/uploads/{exam_id}_{recording.filename}"}


@app.post("/exam/{exam_id}/complete")
async def complete_exam(exam_id: str):
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="考试未找到")

    exam = mock_db["exams"][exam_id]
    exam["status"] = "completed"
    exam["endTime"] = datetime.now().isoformat()

    total_score = 0
    answer_count = len(exam.get("answers", {}))
    for ans in exam.get("answers", {}).values():
        sr = ans.get("score_result", {})
        total_score += sr.get("totalScore", 0)

    mock_db["history"].append({
        "examId": exam_id,
        "date": datetime.now().isoformat(),
        "questionCount": len(exam.get("questionIds", [])),
        "totalScore": total_score,
        "maxScore": answer_count * 100 if answer_count else 100,
        "grade": "B",
        "province": "national",
        "dimensions": [
            {"name": "法治思维", "score": random.randint(10, 20), "maxScore": 20},
            {"name": "实务落地", "score": random.randint(10, 20), "maxScore": 20},
            {"name": "逻辑结构", "score": random.randint(8, 15), "maxScore": 15},
            {"name": "语言表达", "score": random.randint(8, 15), "maxScore": 15},
            {"name": "综合分析", "score": random.randint(8, 15), "maxScore": 15},
            {"name": "应急应变", "score": random.randint(8, 15), "maxScore": 15},
        ],
        "questionSummary": f"考试 {exam_id}"
    })

    return {"success": True}


# --- 3. Scoring ---

@app.post("/scoring/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    # TODO: 集成真实ASR（Whisper等）
    return {
        "transcript": "考生认为我们应该因地制宜，"
                      "避免形式主义，确保政策落到实处。"
                      "县长直播带货可以是有效的手段，但不能成为一刀切的指令。"
                      "每个县应该根据自身的经济条件和资源禀赋制定发展策略，"
                      "真正做到为民服务、科学决策。",
        "duration": 165
    }


@app.post("/scoring/evaluate")
async def evaluate_answer(request: EvaluateRequest):
    # Find question data
    question = None
    for q in mock_db["questions"]:
        if q["id"] == request.questionId:
            question = q
            break

    if not question:
        question = {
            "id": request.questionId,
            "question": "未知题目",
            "fullScore": 30,
            "dimensions": [
                {"name": "现象解读", "score": 8},
                {"name": "原因分析", "score": 7},
                {"name": "科学措施", "score": 8},
                {"name": "语言逻辑", "score": 5},
                {"name": "创新思维", "score": 2}
            ],
            "coreKeywords": [],
            "penaltyKeywords": [],
            "bonusKeywords": [],
            "scoringCriteria": []
        }
    else:
        # Convert frontend question format to LLM format
        question = {
            "id": question["id"],
            "question": question.get("stem", ""),
            "fullScore": 30,
            "dimensions": [
                {"name": sp["content"][:20], "score": sp["score"]}
                for sp in question.get("scoringPoints", [])
            ],
            "coreKeywords": question.get("keywords", {}).get("scoring", []),
            "penaltyKeywords": question.get("keywords", {}).get("deducting", []),
            "bonusKeywords": question.get("keywords", {}).get("bonus", []),
            "scoringCriteria": [sp["content"] for sp in question.get("scoringPoints", [])]
        }

    try:
        raw_result = process_scoring_logic(question, request.transcript)
        result = transform_llm_to_frontend(raw_result, question)

        if request.examId and request.examId in mock_db["exams"]:
            mock_db["exams"][request.examId]["answers"][request.questionId] = {
                "text": request.transcript,
                "score_result": result
            }

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scoring/result/{exam_id}/{question_id}")
async def get_scoring_result(exam_id: str, question_id: str):
    if exam_id not in mock_db["exams"]:
        raise HTTPException(status_code=404, detail="考试未找到")
    exam = mock_db["exams"][exam_id]
    if question_id not in exam.get("answers", {}):
        raise HTTPException(status_code=404, detail="该题目尚未评分")
    return exam["answers"][question_id]["score_result"]


# --- 4. History ---

@app.get("/history")
async def get_history_list(page: int = 1, pageSize: int = 10, province: Optional[str] = None):
    records = mock_db["history"]
    if province and province != "all":
        records = [r for r in records if r.get("province") == province]

    total = len(records)
    records_sorted = sorted(records, key=lambda x: x.get("date", ""), reverse=True)
    start = (page - 1) * pageSize
    paged = records_sorted[start:start + pageSize]

    return {"list": paged, "total": total, "page": page, "pageSize": pageSize}


@app.get("/history/trend")
async def get_history_trend(days: int = 30):
    records = mock_db["history"]
    trend = []
    for r in sorted(records, key=lambda x: x.get("date", "")):
        trend.append({
            "date": r["date"][:10],
            "score": r.get("totalScore", 0)
        })
    return trend


@app.get("/history/stats")
async def get_history_stats():
    records = mock_db["history"]
    if not records:
        return {
            "totalExams": 0,
            "avgScore": 0,
            "bestScore": 0,
            "weakestDimension": "",
            "dimensionAverages": []
        }

    scores = [r.get("totalScore", 0) for r in records]
    dim_totals = {}
    dim_counts = {}
    dim_max = {}

    for r in records:
        for d in r.get("dimensions", []):
            name = d["name"]
            dim_totals[name] = dim_totals.get(name, 0) + d["score"]
            dim_counts[name] = dim_counts.get(name, 0) + 1
            dim_max[name] = d.get("maxScore", 20)

    dim_avgs = []
    worst_name = ""
    worst_ratio = 999
    for name in dim_totals:
        avg = round(dim_totals[name] / dim_counts[name], 1)
        ms = dim_max.get(name, 20)
        dim_avgs.append({"name": name, "avg": avg, "maxScore": ms})
        ratio = avg / ms if ms > 0 else 0
        if ratio < worst_ratio:
            worst_ratio = ratio
            worst_name = name

    return {
        "totalExams": len(records),
        "avgScore": round(sum(scores) / len(scores)),
        "bestScore": max(scores),
        "weakestDimension": worst_name,
        "dimensionAverages": dim_avgs
    }


@app.get("/history/{exam_id}")
async def get_history_detail(exam_id: str):
    for r in mock_db["history"]:
        if r["examId"] == exam_id:
            return r
    if exam_id in mock_db["exams"]:
        return mock_db["exams"][exam_id]
    raise HTTPException(status_code=404, detail="记录未找到")


# --- 5. User ---

@app.get("/user/me")
async def get_current_user_info(current_user: AuthUser = Depends(get_current_user)):
    """验证 token 并返回用户信息"""
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "email": current_user.email
    }

@app.get("/user/info")
async def get_user_info():
    return mock_db["users"]["info"]


@app.put("/user/preferences")
async def update_preferences(data: UserPreferences):
    mock_db["users"]["preferences"] = data.dict(exclude_unset=True)
    return {"success": True}


@app.get("/user/provinces")
async def get_provinces():
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


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


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
async def change_password(data: PasswordChange, current_user: AuthUser = Depends(get_current_user)):
    """修改密码"""
    if current_user.username not in fake_users_db:
        raise HTTPException(status_code=404, detail="用户未找到")
    user_data = fake_users_db[current_user.username]
    if not verify_password(data.old_password, user_data["hashed_password"]):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少6位")
    user_data["hashed_password"] = get_password_hash(data.new_password)
    return {"success": True, "message": "密码修改成功"}


# ================= Entry =================

if __name__ == "__main__":
    import uvicorn

    print("[START] API server starting...")
    print(f"[MODE] {'Mock' if USE_MOCK else 'Real API'}")
    print(f"[URL] http://localhost:8050")
    print(f"[DOCS] http://localhost:8050/docs")

    uvicorn.run(app, host="127.0.0.1", port=8050)
