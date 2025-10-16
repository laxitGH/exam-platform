from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from fastapi import Depends, HTTPException

from app.models.user import User
from app.services.auth import get_current_user
from app.models.test_attempt import TestAttempt, TestType, TestStatus

from app.models.exam import Exam
from app.models.question import Question
from app.models.paper import Paper, PaperType
from app.services.rate_limit import limit_route


router = APIRouter()


@router.get("/upcoming")
def list_upcoming_exams():
    """PUBLIC: List exams with start_time in the future."""
    now = datetime.now(timezone.utc)
    # Filter for exams starting later than now; keep payload lightweight
    exams: list[Exam] = Exam.objects(start_time__gte=now)
    return [e.to_dict() for e in exams]


@router.get("/papers")
def list_available_papers():
    """PUBLIC: List mock/real papers not scheduled for a future exam."""
    now = datetime.now(timezone.utc)
    # Collect paper ids already tied to a future exam to exclude them
    future_exams: list[Exam] = Exam.objects(start_time__gte=now)
    future_exam_paper_ids = set(
        str(exam.paper.id) for exam in future_exams.only("paper")
    )

    allowed_types = [PaperType.MOCK.value, PaperType.REAL.value]
    papers: list[Paper] = Paper.objects(type__in=allowed_types, id__nin=list(future_exam_paper_ids)).order_by("name")
    return [p.to_dict() for p in papers]


class EnrollBody(BaseModel):
    exam_id: str

@router.post("/enroll")
def enroll(
    body: EnrollBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """PROTECTED: Enroll current user into an exam."""
    exam: Exam | None = Exam.objects(id=body.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    
    # Enforce one attempt per user per exam
    existing_test_attempt: TestAttempt | None = TestAttempt.objects(exam=exam, user=current_user).first()
    if existing_test_attempt:
        raise HTTPException(status_code=409, detail="Already enrolled")
    
    # Pre-create attempt; actual attempt starts when user begins
    test_attempt = TestAttempt(
        exam=exam,
        paper=exam.paper,
        user=current_user,
        type=TestType.COMPETITIVE.value,
        status=TestStatus.NOT_STARTED.value,
        enrolled_on=datetime.now(timezone.utc),
    )

    test_attempt.save()
    try:
        # Keep enrolled counter in sync for analytics
        exam.enrolled_count = int(exam.enrolled_count or 0) + 1
        exam.save()
    except Exception:
        pass
    return test_attempt.to_dict()


class NextQuestionBody(BaseModel):
    paper_id: str
    current_code: str | None = None


@router.post("/papers/questions/next", dependencies=[Depends(limit_route(5))])
def get_next_question(
    body: NextQuestionBody, 
    current_user: User = Depends(get_current_user),
) -> dict:
    """PROTECTED | RATE-LIMITED: Get next question code and payload for a paper."""
    paper: Paper | None = Paper.objects(id=body.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Determine next code based on order, defaulting to the first if none given
    ordered = sorted(paper.paper_questions, key=lambda pq: pq.order)
    codes = [pq.question.code for pq in ordered]

    next_code: str | None
    if body.current_code:
        try:
            idx = codes.index(body.current_code)
            next_code = codes[idx + 1] if idx + 1 < len(codes) else None
        except ValueError:
            next_code = codes[0] if codes else None
    else:
        next_code = codes[0] if codes else None

    if not next_code:
        return {"question": None, "next_code": None}

    # Fetch the full question payload for rendering
    question: Question | None = Question.objects(code=next_code).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    return {"question": question.to_output(), "next_code": next_code}