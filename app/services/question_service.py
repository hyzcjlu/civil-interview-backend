"""Question service: CRUD, random, import, generate"""
import json
import random
import uuid
from typing import Optional, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Question
from app.schemas.common import QuestionCreate, QuestionUpdate
from app.core.ai import call_llm_api_async, PROVINCE_NAMES, POSITION_NAMES, DIMENSION_NAMES


def _q_to_dict(q: Question) -> dict:
    return {
        "id": q.id,
        "stem": q.stem,
        "dimension": q.dimension,
        "province": q.province,
        "prepTime": q.prep_time,
        "answerTime": q.answer_time,
        "scoringPoints": q.scoring_points or [],
        "keywords": q.keywords or {"scoring": [], "deducting": [], "bonus": []},
    }


def list_questions(
    db: Session,
    keyword: str = "",
    dimension: str = "",
    province: str = "",
    current: int = 1,
    page_size: int = 10,
) -> dict:
    query = db.query(Question)
    if keyword:
        query = query.filter(Question.stem.contains(keyword))
    if dimension:
        query = query.filter(Question.dimension == dimension)
    if province and province != "all":
        query = query.filter(Question.province.in_([province, "national"]))
    total = query.count()
    rows = query.offset((current - 1) * page_size).limit(page_size).all()
    return {
        "list": [_q_to_dict(q) for q in rows],
        "total": total,
        "current": current,
        "pageSize": page_size,
    }


def get_random_questions(db: Session, province: str = "national", count: int = 5) -> List[dict]:
    query = db.query(Question)
    if province and province != "all":
        query = query.filter(Question.province.in_([province, "national"]))
    all_qs = query.all()
    count = min(count, len(all_qs))
    return [_q_to_dict(q) for q in random.sample(all_qs, count)] if all_qs else []


def get_question(db: Session, question_id: str) -> dict:
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目未找到")
    return _q_to_dict(q)


def create_question(db: Session, data: QuestionCreate) -> dict:
    q = Question(
        id=f"q_{uuid.uuid4().hex[:8]}",
        stem=data.stem,
        dimension=data.dimension,
        province=data.province,
        prep_time=data.prepTime,
        answer_time=data.answerTime,
        scoring_points=data.scoringPoints,
        keywords=data.keywords,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _q_to_dict(q)


def update_question(db: Session, question_id: str, data: QuestionUpdate) -> dict:
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目未找到")
    q.stem = data.stem
    q.dimension = data.dimension
    q.province = data.province
    q.prep_time = data.prepTime
    q.answer_time = data.answerTime
    q.scoring_points = data.scoringPoints
    q.keywords = data.keywords
    db.commit()
    db.refresh(q)
    return _q_to_dict(q)


def delete_question(db: Session, question_id: str) -> dict:
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="题目未找到")
    db.delete(q)
    db.commit()
    return {"success": True}


def import_questions(db: Session, content: bytes, filename: str) -> dict:
    imported, failed = 0, 0
    fname = filename.lower() if filename else ""

    try:
        if fname.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            if not isinstance(data, list):
                raise HTTPException(status_code=400, detail="JSON 文件应包含题目数组")
            for item in data:
                try:
                    stem = (item.get("stem") or "").strip()
                    if not stem:
                        failed += 1
                        continue
                    q = Question(
                        id=f"q_{uuid.uuid4().hex[:8]}",
                        stem=stem,
                        dimension=item.get("dimension", "analysis"),
                        province=item.get("province", "national"),
                        prep_time=item.get("prepTime", 90),
                        answer_time=item.get("answerTime", 180),
                        scoring_points=item.get("scoringPoints", []),
                        keywords=item.get("keywords", {"scoring": [], "deducting": [], "bonus": []}),
                    )
                    db.add(q)
                    imported += 1
                except Exception:
                    failed += 1
            db.commit()

        elif fname.endswith((".xlsx", ".xls")):
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                raise HTTPException(status_code=400, detail="Excel 文件为空")
            headers = [str(h).strip().lower() if h else "" for h in rows[0]]
            col = {}
            mapping = {
                "stem": ["题干", "stem"],
                "dimension": ["所属维度", "dimension"],
                "province": ["省份", "province"],
                "prepTime": ["准备时间", "preptime"],
                "answerTime": ["作答时间", "answertime"],
                "scoringPoints": ["采分点", "scoringpoints"],
                "scoringKeywords": ["得分关键词", "scoringkeywords"],
                "deductingKeywords": ["扣分关键词", "deductingkeywords"],
                "bonusKeywords": ["加分关键词", "bonuskeywords"],
            }
            for field, aliases in mapping.items():
                for i, h in enumerate(headers):
                    if h in aliases:
                        col[field] = i
                        break
            if "stem" not in col:
                raise HTTPException(status_code=400, detail="Excel 缺少题干列")
            for row in rows[1:]:
                try:
                    stem = str(row[col["stem"]]).strip() if row[col["stem"]] else ""
                    if not stem:
                        failed += 1
                        continue
                    kw = {"scoring": [], "deducting": [], "bonus": []}
                    for ktype, kcol in [("scoring", "scoringKeywords"), ("deducting", "deductingKeywords"), ("bonus", "bonusKeywords")]:
                        if kcol in col and row[col[kcol]]:
                            val = str(row[col[kcol]]).strip()
                            kw[ktype] = json.loads(val) if val.startswith("[") else [w.strip() for w in val.split(",") if w.strip()]
                    sp = []
                    if "scoringPoints" in col and row[col["scoringPoints"]]:
                        val = str(row[col["scoringPoints"]]).strip()
                        if val.startswith("["):
                            sp = json.loads(val)
                    q = Question(
                        id=f"q_{uuid.uuid4().hex[:8]}",
                        stem=stem,
                        dimension=str(row[col["dimension"]]).strip() if "dimension" in col and row[col["dimension"]] else "analysis",
                        province=str(row[col["province"]]).strip() if "province" in col and row[col["province"]] else "national",
                        prep_time=int(row[col["prepTime"]]) if "prepTime" in col and row[col["prepTime"]] else 90,
                        answer_time=int(row[col["answerTime"]]) if "answerTime" in col and row[col["answerTime"]] else 180,
                        scoring_points=sp,
                        keywords=kw,
                    )
                    db.add(q)
                    imported += 1
                except Exception:
                    failed += 1
            db.commit()
            wb.close()
        else:
            raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .json 或 .xlsx")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    return {"imported": imported, "failed": failed}


async def generate_questions_by_position(
    db: Session, province: str, position: str, count: int = 5
) -> List[dict]:
    count = min(count, 10)
    position_name = POSITION_NAMES.get(position, position)
    prompt = f"""请为"{position_name}"岗位生成{count}道公务员面试题目。
每道题以JSON对象表示，所有题目放在一个JSON数组中返回。
每道题包含字段：
- stem: 题目内容(字符串)
- dimension: 所属维度(analysis/practical/emergency/legal/logic/expression 之一)
返回纯JSON数组，不要有其他内容。"""
    result = await call_llm_api_async(prompt, system_msg="你是公务员面试命题专家，请只输出JSON数组。", max_tokens=3000)
    generated = []
    if result and isinstance(result, list):
        for q in result[:count]:
            generated.append({
                "id": f"gen_{uuid.uuid4().hex[:8]}",
                "stem": q.get("stem", ""),
                "dimension": q.get("dimension", "analysis"),
                "province": province,
                "prepTime": 90, "answerTime": 180,
                "scoringPoints": q.get("scoringPoints", [{"content": "观点明确，分析深入", "score": 7}, {"content": "措施具体可行", "score": 8}, {"content": "逻辑清晰，表达流畅", "score": 5}]),
                "keywords": q.get("keywords", {"scoring": [], "deducting": [], "bonus": []}),
            })
        if generated:
            return generated
    # fallback: random from db
    query = db.query(Question)
    if province and province != "all":
        query = query.filter(Question.province.in_([province, "national"]))
    all_qs = query.all()
    sample = random.sample(all_qs, min(count, len(all_qs))) if all_qs else []
    return [{**_q_to_dict(q), "id": f"gen_{uuid.uuid4().hex[:8]}"} for q in sample]


async def generate_training_questions(db: Session, dimension: str, count: int = 3) -> List[dict]:
    count = min(count, 10)
    dim_name = DIMENSION_NAMES.get(dimension, dimension)
    prompt = f"""请生成{count}道考察"{dim_name}"能力的公务员面试题目。
每道题以JSON对象表示，放在一个JSON数组中返回。
每道题包含字段：
- stem: 题目内容(字符串)
- scoringPoints: 采分点数组，每项含 content 和 score
- keywords: 含 scoring/deducting/bonus 三个字符串数组
返回纯JSON数组，不要有其他内容。"""
    result = await call_llm_api_async(prompt, system_msg="你是公务员面试命题专家，请只输出JSON数组。", max_tokens=3000)
    generated = []
    if result and isinstance(result, list):
        for q in result[:count]:
            generated.append({
                "id": f"train_{uuid.uuid4().hex[:8]}",
                "stem": q.get("stem", ""),
                "dimension": dimension,
                "province": "national",
                "prepTime": 90, "answerTime": 180,
                "scoringPoints": q.get("scoringPoints", [{"content": f"对{dim_name}有清晰理解", "score": 7}, {"content": "结合实际提出措施", "score": 8}, {"content": "逻辑清晰表达规范", "score": 5}]),
                "keywords": q.get("keywords", {"scoring": [], "deducting": [], "bonus": []}),
            })
        if generated:
            return generated
    # fallback
    query = db.query(Question).filter(Question.dimension == dimension)
    all_qs = query.all() or db.query(Question).all()
    sample = random.sample(all_qs, min(count, len(all_qs))) if all_qs else []
    return [{**_q_to_dict(q), "id": f"train_{uuid.uuid4().hex[:8]}", "dimension": dimension} for q in sample]
