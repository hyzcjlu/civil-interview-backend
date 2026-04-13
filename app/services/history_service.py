"""History service: list, detail, stats, trend"""
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import HistoryRecord

DIM_DEFS = [
    {"name": "法治思维", "maxScore": 20},
    {"name": "实务落地", "maxScore": 20},
    {"name": "逻辑结构", "maxScore": 15},
    {"name": "语言表达", "maxScore": 15},
    {"name": "综合分析", "maxScore": 15},
    {"name": "应急应变", "maxScore": 15},
]


def _record_to_dict(r: HistoryRecord) -> dict:
    return {
        "examId": r.exam_id,
        "username": r.username,
        "questionCount": r.question_count,
        "totalScore": float(r.total_score or 0),
        "maxScore": float(r.max_score or 30),
        "grade": r.grade,
        "province": r.province or "national",
        "dimensions": r.dimensions or [],
        "completedAt": r.completed_at.isoformat() if r.completed_at else "",
    }


def get_history_list(db: Session, username: str, current: int = 1, page_size: int = 10) -> dict:
    query = db.query(HistoryRecord).filter(HistoryRecord.username == username)
    query = query.order_by(HistoryRecord.completed_at.desc())
    total = query.count()
    rows = query.offset((current - 1) * page_size).limit(page_size).all()
    return {
        "list": [_record_to_dict(r) for r in rows],
        "total": total,
        "current": current,
        "pageSize": page_size,
    }


def get_history_detail(db: Session, exam_id: str) -> dict:
    r = db.query(HistoryRecord).filter(HistoryRecord.exam_id == exam_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="历史记录未找到")
    return _record_to_dict(r)


def get_history_stats(db: Session, username: str) -> dict:
    rows = db.query(HistoryRecord).filter(HistoryRecord.username == username).all()
    empty = {
        "totalExams": 0, "avgScore": 0, "bestScore": 0,
        "weakestDimension": "",
        "dimensionAverages": [{"name": d["name"], "avg": 0, "maxScore": d["maxScore"]} for d in DIM_DEFS],
    }
    if not rows:
        return empty
    scores = [float(r.total_score or 0) for r in rows]
    totals = {d["name"]: [] for d in DIM_DEFS}
    for r in rows:
        for dim in (r.dimensions or []):
            name = dim.get("name")
            if name in totals:
                totals[name].append(dim.get("score", 0))
    avgs = []
    for d in DIM_DEFS:
        vals = totals[d["name"]]
        avgs.append({"name": d["name"], "avg": round(sum(vals) / len(vals), 2) if vals else 0, "maxScore": d["maxScore"]})
    weakest, lowest = "", 100
    for a in avgs:
        if a["avg"] > 0:
            pct = a["avg"] / a["maxScore"] * 100
            if pct < lowest:
                lowest, weakest = pct, a["name"]
    return {
        "totalExams": len(rows),
        "avgScore": round(sum(scores) / len(scores), 2),
        "bestScore": max(scores),
        "weakestDimension": weakest,
        "dimensionAverages": avgs,
    }


def get_history_trend(db: Session, username: str, days: int = 30) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
    rows = (
        db.query(HistoryRecord)
        .filter(HistoryRecord.username == username, HistoryRecord.completed_at >= cutoff)
        .order_by(HistoryRecord.completed_at.asc())
        .all()
    )
    return [
        {
            "index": i + 1,
            "label": f"第{i + 1}次",
            "score": float(r.total_score or 0),
            "date": r.completed_at.strftime("%Y-%m-%d") if r.completed_at else "",
        }
        for i, r in enumerate(rows)
    ]
