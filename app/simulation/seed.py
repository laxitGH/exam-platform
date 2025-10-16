from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.connections.mongo import init_mongo, close_mongo
from app.models.question import Question, QuestionType, QuestionOption
from app.models.paper import Paper, PaperType, PaperQuestion, PaperSubjectMaxScore
from app.models.exam import Exam, ExamStatus
from app.models.user import User
from app.services.auth import hash_password
from app.utils.base import SubjectCode


def _ensure_users() -> list[User]:
    users: list[User] = []
    fixtures = [
        ("Alice Example", "alice@example.com", "Secret123!"),
        ("Bob Example", "bob@example.com", "Secret123!"),
        ("Carol Example", "carol@example.com", "Secret123!"),
    ]
    for name, email, pwd in fixtures:
        user = User.objects(email=email).first()
        if not user:
            user = User(name=name, email=email, password=hash_password(pwd))
            user.save()
        users.append(user)
    return users


def _ensure_questions() -> tuple[list[Question], list[Question]]:
    singles: list[Question] = []
    multis: list[Question] = []

    subjects = [s.value for s in SubjectCode]

    # Create 100 single-correct
    for i in range(1, 101):
        code = f"S{i:03d}"
        q = Question.objects(code=code).first()
        if not q:
            opts = []
            correct_index = random.randint(0, 3)
            for idx in range(4):
                opts.append(QuestionOption(
                    correct=(idx == correct_index),
                    order=idx,
                    weight=100 if idx == correct_index else 0,
                    type="text",
                    code=f"{code}-O{idx+1}",
                    text=f"Option {idx+1} for {code}",
                ))
            q = Question(
                code=code,
                type=QuestionType.SINGLE_CORRECT.value,
                subject_code=subjects[(i - 1) % len(subjects)],
                statement=f"Single-correct question {i}",
                question_options=opts,
            )
            q.save()
        singles.append(q)

    # Create 25 multi-correct
    for i in range(1, 26):
        code = f"M{i:03d}"
        q = Question.objects(code=code).first()
        if not q:
            opts = []
            # choose 2-3 correct options, weights sum to 100
            num_correct = random.choice([2, 3])
            corrects = set(random.sample(range(4), k=num_correct))
            # simple even split of weight among corrects
            per = 100 // len(corrects)
            for idx in range(4):
                opts.append(QuestionOption(
                    correct=(idx in corrects),
                    order=idx,
                    weight=per if idx in corrects else 0,
                    type="text",
                    code=f"{code}-O{idx+1}",
                    text=f"Option {idx+1} for {code}",
                ))
            q = Question(
                code=code,
                type=QuestionType.MULTIPLE_CORRECT.value,
                subject_code=subjects[(i - 1) % len(subjects)],
                statement=f"Multi-correct question {i}",
                question_options=opts,
            )
            q.save()
        multis.append(q)

    return singles, multis


def _ensure_papers(singles: list[Question], multis: list[Question]) -> list[Paper]:
    papers: list[Paper] = []
    all_questions = singles + multis
    for i in range(1, 26):
        code = f"PAPER{i:02d}"
        p = Paper.objects(code=code).first()
        if not p:
            # choose 10 questions, ensure some multis may appear; questions can repeat across papers
            selected = random.sample(all_questions, k=10)
            pq = []
            order = 1
            for q in selected:
                pq.append(PaperQuestion(
                    mandatory=False,
                    order=order,
                    question=q,
                    negative_score=1,
                    positive_score=4,
                ))
                order += 1
            # compute paper-level maxes
            subject_max: dict[str, int] = {}
            total_max = 0
            for pqe in pq:
                total_max += int(pqe.positive_score or 0)
                subj = str(pqe.question.subject_code)
                subject_max[subj] = int(subject_max.get(subj, 0)) + int(pqe.positive_score or 0)

            p = Paper(
                name=f"Mock Paper {i}",
                code=code,
                type=PaperType.MOCK.value,
                max_score=int(total_max),
                subject_max_scores=[PaperSubjectMaxScore(subject_code=k, max_score=v) for k, v in subject_max.items()],
                duration_minutes=60,
                paper_questions=pq,
            )
            p.save()
        papers.append(p)
    return papers


def _ensure_exams(papers: list[Paper]) -> list[Exam]:
    # Use 5 papers for 5 exams within next week; remaining papers stay for mock practice
    exams: list[Exam] = []
    now = datetime.now(timezone.utc)
    chosen = random.sample(papers, k=5)
    for idx, paper in enumerate(chosen, start=1):
        start = now + timedelta(days=idx, hours=9)
        end = start + timedelta(hours=2)
        e = Exam.objects(paper=paper, date=start.date(), start_time=start).first()
        if not e:
            e = Exam(
                paper=paper,
                status=ExamStatus.UPCOMING.value,
                start_time=start,
                end_time=end,
                date=start.date(),
            )
            e.save()
        exams.append(e)
    return exams


def seed() -> None:
    init_mongo()
    try:
        # Purge existing data in an order that respects references
        from app.models.submission import Submission
        from app.models.test_attempt import TestAttempt
        from app.models.exam import Exam
        from app.models.paper import Paper
        from app.models.question import Question
        Submission.drop_collection()
        TestAttempt.drop_collection()
        Exam.drop_collection()
        Paper.drop_collection()
        Question.drop_collection()
        User.drop_collection()

        # create users and domain data
        _ensure_users()
        singles, multis = _ensure_questions()
        papers = _ensure_papers(singles, multis)
        _ensure_exams(papers)
        print("Seed completed.")
    finally:
        close_mongo()


if __name__ == "__main__":
    seed()


