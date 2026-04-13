"""Scoring service: transcribe, evaluate (two-stage), get result"""
import logging
import random
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.ai import call_llm_api_async, transcribe_audio_file, PROVINCE_NAMES, DIMENSION_NAMES
from app.models.entities import Question, Exam, ExamAnswer

# Import two-stage scoring utilities (same directory as before)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from two_stage_scoring import (
    build_evidence_extraction_prompt,
    build_evidence_based_scoring_prompt,
    validate_evidence,
    validate_scoring_result,
    fallback_scoring,
)

logger = logging.getLogger(__name__)

DIM_MAPPING = {
    "analysis": "综合分析",
    "practical": "实务落地",
    "emergency": "应急应变",
    "legal": "法治思维",
    "logic": "逻辑结构",
    "expression": "语言表达",
}


async def transcribe(audio_bytes: bytes) -> dict:
    transcript = await transcribe_audio_file(audio_bytes)
    return {"transcript": transcript, "duration": round(len(transcript) / 10, 1)}


async def evaluate_answer(db: Session, question_id: str, transcript: str, exam_id: Optional[str]) -> dict:
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Build question dict compatible with two_stage_scoring
    q_dict = {
        "question": question.stem,
        "type": DIM_MAPPING.get(question.dimension, "综合分析"),
        "stem": question.stem,
        "scoringPoints": [sp.get("content", "") for sp in (question.scoring_points or [])],
        "keywords": question.keywords or {},
        "dimensions": [
            {"name": "综合分析", "score": 20},
            {"name": "实务落地", "score": 20},
            {"name": "应急应变", "score": 15},
            {"name": "法治思维", "score": 15},
            {"name": "逻辑结构", "score": 15},
            {"name": "语言表达", "score": 15},
        ],
    }

    # Stage 1: Evidence extraction
    logger.info("Stage 1: Evidence extraction")
    evidence_prompt = build_evidence_extraction_prompt(transcript, q_dict)
    evidence_raw = await call_llm_api_async(evidence_prompt)
    evidence = {"present": [], "absent": [], "penalty": [], "bonus": []}
    if evidence_raw and isinstance(evidence_raw, dict):
        evidence = evidence_raw.get("evidence", evidence)
        evidence = validate_evidence(evidence, transcript)

    # Stage 2: Evidence-based scoring
    logger.info("Stage 2: Evidence-based scoring")
    scoring_prompt = build_evidence_based_scoring_prompt(evidence, q_dict)
    scoring_raw = await call_llm_api_async(scoring_prompt)
    dim_scores, rationale = {}, ""

    if scoring_raw and isinstance(scoring_raw, dict):
        max_scores = {d["name"]: d["score"] for d in q_dict["dimensions"]}
        is_valid, errors, scoring_result = validate_scoring_result(scoring_raw, evidence, max_scores)
        if is_valid:
            dim_scores = scoring_result.get("dimension_scores", {})
            rationale = scoring_result.get("overall_rationale", "")

    if not dim_scores:
        logger.warning("Two-stage scoring failed, using fallback")
        fb = fallback_scoring(transcript, q_dict, evidence)
        dim_scores = fb.get("dimension_scores", {})
        rationale = fb.get("overall_rationale", "评分完成")

    frontend_dims = []
    total = 0.0
    max_score = 100

    for key, display_name in DIM_MAPPING.items():
        score = dim_scores.get(display_name, dim_scores.get(key, 0))
        capped = max(0, min(score, 20 if key in ["analysis", "practical"] else 15))
        frontend_dims.append({
            "name": display_name,
            "key": key,
            "score": round(capped, 2),
            "maxScore": 20 if key in ["analysis", "practical"] else 15,
            "lostReasons": [],
        })
        total += capped

    grade = "A" if total / max_score > 0.85 else "B" if total / max_score >= 0.75 else "C" if total / max_score >= 0.60 else "D"

    result = {
        "totalScore": round(total, 2),
        "maxScore": max_score,
        "grade": grade,
        "dimensions": frontend_dims,
        "aiComment": rationale or "评分完成",
    }

    # Persist to exam_answers
    if exam_id:
        ans = db.query(ExamAnswer).filter(
            ExamAnswer.exam_id == exam_id,
            ExamAnswer.question_id == question_id,
        ).first()
        if not ans:
            ans = ExamAnswer(exam_id=exam_id, question_id=question_id)
            db.add(ans)
        ans.transcript = transcript
        ans.score_result = result
        ans.answered_at = datetime.now(timezone.utc)
        db.commit()

    return result


def get_scoring_result(db: Session, exam_id: str, question_id: str) -> dict:
    ans = db.query(ExamAnswer).filter(
        ExamAnswer.exam_id == exam_id,
        ExamAnswer.question_id == question_id,
    ).first()
    if not ans or not ans.score_result:
        raise HTTPException(status_code=404, detail="评分结果未找到")
    return ans.score_result
