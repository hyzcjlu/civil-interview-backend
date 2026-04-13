"""Exam service: start, upload, complete"""
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import Exam, ExamAnswer, HistoryRecord
from app.schemas.common import ExamStartRequest


def start_exam(db: Session, data: ExamStartRequest, username: str) -> dict:
    exam_id = f"exam_{uuid.uuid4().hex[:8]}"
    exam = Exam(
        id=exam_id,
        user_id=username,
        question_ids=data.questionIds,
        status="in_progress",
        start_time=datetime.now(timezone.utc),
    )
    db.add(exam)
    db.commit()
    return {
        "examId": exam_id,
        "questionIds": data.questionIds,
        "startTime": exam.start_time.isoformat(),
    }


def upload_recording(exam_id: str, filename: str) -> dict:
    """Just acknowledge the upload — audio file stored in memory"""
    return {"success": True, "fileUrl": f"/uploads/{filename}"}


def complete_exam(db: Session, exam_id: str) -> dict:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="考试未找到")
    exam.status = "completed"
    exam.end_time = datetime.now(timezone.utc)

    answers = db.query(ExamAnswer).filter(ExamAnswer.exam_id == exam_id).all()
    total_score, question_count, dimensions = 0.0, 0, []
    for ans in answers:
        sr = ans.score_result or {}
        total_score += sr.get("totalScore", 0)
        question_count += 1
        if sr.get("dimensions"):
            dimensions = sr["dimensions"]

    avg = round(total_score / question_count, 2) if question_count else 0
    max_score = 100
    grade = "A" if avg / max_score > 0.85 else "B" if avg / max_score >= 0.75 else "C" if avg / max_score >= 0.60 else "D"

    # Upsert history record
    record = db.query(HistoryRecord).filter(HistoryRecord.exam_id == exam_id).first()
    if not record:
        record = HistoryRecord(exam_id=exam_id, username=exam.user_id)
        db.add(record)
    record.question_count = question_count
    record.total_score = avg
    record.max_score = max_score
    record.grade = grade
    record.province = exam.province if hasattr(exam, "province") else "national"
    record.dimensions = dimensions
    record.completed_at = exam.end_time
    db.commit()

    return {"success": True, "finalScore": avg}
