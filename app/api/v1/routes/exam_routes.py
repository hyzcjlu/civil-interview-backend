from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.common import AuthUser, ExamStartRequest
from app.services.exam_service import start_exam, upload_recording, complete_exam

router = APIRouter(prefix="/exam", tags=["exam"])


@router.post("/start")
def exam_start(data: ExamStartRequest, current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return start_exam(db, data, current_user.username)


@router.post("/{exam_id}/upload")
async def exam_upload(exam_id: str, recording: UploadFile = File(...), current_user: AuthUser = Depends(get_current_user)):
    filename = f"{exam_id}_{recording.filename}"
    await recording.read()  # consume without storing
    return upload_recording(exam_id, filename)


@router.post("/{exam_id}/complete")
def exam_complete(exam_id: str, current_user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return complete_exam(db, exam_id)
