from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.common import AuthUser, EvaluateRequest
from app.services.scoring_service import transcribe, evaluate_answer, get_scoring_result

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/transcribe")
async def scoring_transcribe(audio: UploadFile = File(...), current_user: AuthUser = Depends(get_current_user)):
    audio_bytes = await audio.read()
    return await transcribe(audio_bytes)


@router.post("/evaluate")
async def scoring_evaluate(data: EvaluateRequest, current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return await evaluate_answer(db, data.questionId, data.transcript, data.examId)


@router.get("/result/{exam_id}/{question_id}")
def scoring_result(exam_id: str, question_id: str, current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_scoring_result(db, exam_id, question_id)
