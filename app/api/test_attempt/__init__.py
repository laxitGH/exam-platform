from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.models.exam import Exam
from app.models.user import User
from app.models.submission import Submission
from app.services.auth import get_current_user
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question, QuestionType
from app.models.test_attempt import TestAttempt, TestStatus, TestType, TestSubjectScore
from app.services.rate_limit import limit_route


router = APIRouter()


class StartTestBody(BaseModel):
    paper_id: str
    exam_id: str | None = None

@router.post("/start")
def start_test(
    body: StartTestBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """PROTECTED: Start a test attempt for exam or practice."""
    paper: Paper | None = Paper.objects(id=body.paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    if body.exam_id:
        exam: Exam | None = Exam.objects(id=body.exam_id).first()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found")
    else:
        exam = None
    
    if exam:
        # Exam flow: enforce paper match and window before resuming attempt
        if exam.paper != paper:
            raise HTTPException(status_code=409, detail="Exam paper mismatch")
        if exam.start_time > datetime.now(timezone.utc) or exam.end_time < datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="Exam window not open")
        
        # Find pre-enrolled attempt; users enroll first and start later
        test_attempt: TestAttempt | None = TestAttempt.objects(exam=exam, user=current_user, paper=paper).first()
        if not test_attempt:
            raise HTTPException(status_code=404, detail="TestAttempt session not found")

        test_attempt.started_on = datetime.now(timezone.utc)
        test_attempt.status = TestStatus.IN_PROGRESS.value
        test_attempt.save()
    else:
        # Practice flow: create a fresh attempt immediately
        test_attempt = TestAttempt(
            exam=exam,
            paper=paper,
            user=current_user,
            started_on=datetime.now(timezone.utc),
            status=TestStatus.IN_PROGRESS.value,
            type=TestType.PRACTICE.value,
        )

        test_attempt.save()
    
    return test_attempt.to_dict()


class EndTestBody(BaseModel):
    user_test_id: str

@router.post("/end")
def end_test(
    body: EndTestBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """PROTECTED: Mark a test attempt as completed."""
    test_attempt: TestAttempt | None = TestAttempt.objects(id=body.user_test_id, user=current_user).first()
    if not test_attempt:
        raise HTTPException(status_code=404, detail="TestAttempt session not found")
    
    now = datetime.now(timezone.utc)
    # Transition to COMPLETED; aftermath will compute final standings
    test_attempt.status = TestStatus.COMPLETED.value
    test_attempt.ended_on = now
    test_attempt.save()
    return test_attempt.to_dict()


class SubmitAnswerBody(BaseModel):
    question_id: str
    user_test_id: str
    options_chosen: list[str]

def _within_time_window(
    user_test: TestAttempt,
) -> bool:
    """Validate if submission is within allowed time window for this attempt."""
    now = datetime.now(timezone.utc)
    if user_test.type == TestType.COMPETITIVE.value:
        return bool(user_test.exam and user_test.exam.start_time <= now <= user_test.exam.end_time)
    if user_test.type == TestType.PRACTICE.value:
        return bool(user_test.started_on and (now - user_test.started_on).total_seconds() <= user_test.paper.duration_minutes * 60)
    return False

def _score_submission(
    paper: Paper,
    question: Question,
    options_chosen: list[str],
) -> tuple[int, int]:
    """Score a submission based on paper rules and question type, returns (score, max_score)."""
    by_code = {opt.code: opt for opt in question.question_options}
    chosen_set = set(options_chosen or [])
    correct_set = {opt.code for opt in question.question_options if getattr(opt, "correct", False)}

    paper_questions: list[PaperQuestion] = paper.paper_questions
    for pq in paper_questions:
        if pq.question.code != question.code:
            continue

        if not chosen_set and pq.mandatory:
            # Mandatory questions must be answered
            raise HTTPException(status_code=409, detail="Mandatory question needs to be answered")

        if any(code not in by_code for code in chosen_set):
            # Any invalid code counts as a wrong selection
            return (-int(pq.negative_score), pq.positive_score)

        if chosen_set - correct_set:
            # Any wrong selection in the set yields negative marks
            return (-int(pq.negative_score), pq.positive_score)

        qtype = str(question.type)
        if qtype == QuestionType.SINGLE_CORRECT.value:
            # Single-correct: full positive if answered correctly, zero if blank
            if not chosen_set:
                return (0, pq.positive_score)
            return (int(pq.positive_score), pq.positive_score)

        if qtype == QuestionType.MULTIPLE_CORRECT.value:
            # Multiple-correct: proportional to sum of weights of chosen correct options
            total_weight = 0
            for code in chosen_set:
                opt = by_code.get(code)
                if getattr(opt, "correct", False):
                    total_weight += int(getattr(opt, "weight", 0) or 0)
            score = (total_weight * pq.positive_score) / 100
            return (score, pq.positive_score)

        return (0, pq.positive_score)

    raise HTTPException(status_code=404, detail="Question not found in paper")

@router.post("/submit", dependencies=[Depends(limit_route(5))])
def submit_answer(
    body: SubmitAnswerBody,
    current_user: User = Depends(get_current_user),
) -> dict:
    """PROTECTED | RATE-LIMITED: Submit an answer for a question within an in-progress attempt."""
    # Resolve the attempt and ensure user owns it
    test_attempt: TestAttempt | None = TestAttempt.objects(id=body.user_test_id, user=current_user).first()
    if not test_attempt or test_attempt.status != TestStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=409, detail="User test not in progress")
    # Also protect against submissions outside allowed time window
    if not _within_time_window(test_attempt):
        raise HTTPException(status_code=403, detail="Submission outside allowed window")

    paper: Paper | None = test_attempt.paper
    question: Question | None = Question.objects(id=body.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    score, max_score = _score_submission(
        options_chosen=body.options_chosen,
        question=question, 
        paper=paper, 
    )

    # Record immutable submission; unique index prevents duplicates
    submission = Submission(
        score=score,
        user=current_user,
        question=question,
        max_score=max_score,
        test_attempt=test_attempt,
        options_chosen=body.options_chosen,
        subject_code=str(question.subject_code),
    )
    try:
        submission.save()
    except Exception:
        raise HTTPException(status_code=409, detail="Already submitted for this question")

    try:
        # Maintain lightweight aggregates for live progress
        test_attempt.total_score = int(test_attempt.total_score or 0) + int(score)
        if paper is not None:
            paper_max = int(getattr(paper, "max_score", 0) or 0)
            if int(test_attempt.max_total_score or 0) != paper_max:
                test_attempt.max_total_score = paper_max

        # Ensure subject bucket reflects this submission's subject
        subject_max_map = {ps.subject_code: int(ps.max_score or 0) for ps in (getattr(paper, "subject_max_scores", []) or [])}
        subj_code = str(question.subject_code)
        subj_max = subject_max_map.get(subj_code, 0)

        by_subj = {ss.subject_code: ss for ss in (test_attempt.subject_scores or [])}
        current = by_subj.get(subj_code)
        if current:
            current.total_score = int(getattr(current, "total_score", 0) or 0) + int(score)
            current.max_total_score = int(subj_max)
        else:
            test_attempt.subject_scores.append(TestSubjectScore(
                subject_code=subj_code,
                total_score=int(score),
                max_total_score=int(subj_max),
            ))

        # Persist aggregates; ignore transient failures to keep submission path fast
        test_attempt.save()
    except Exception:
        pass

    return submission.to_dict()

