from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, Tuple, Callable, List
from datetime import datetime, timezone
from jose import jwt, JWTError

from app.models.user import User
from app.utils.config import settings
from app.models.exam import Exam
from app.models.submission import Submission
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question, QuestionType
from app.models.test_attempt import TestAttempt, TestStatus, TestType, TestSubjectScore
from app.services.auth import TokenPair, verify_password, create_tokens, hash_password
from app.services.exam_conclusion import conclude_exam


_STATE_PATH = Path(__file__).with_name("state.json")


def _load_state() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    _STATE_PATH.write_text(json.dumps(state, indent=2))


def _ensure_section(state: dict, section: str) -> dict:
    if section not in state or not isinstance(state.get(section), dict):
        state[section] = {}
    if "input" not in state[section] or not isinstance(state[section].get("input"), dict):
        state[section]["input"] = {}
    if "output" not in state[section] or not isinstance(state[section].get("output"), dict):
        state[section]["output"] = {}
    return state[section]


def signup_user(name: str, email: str, password: str) -> TokenPair:
    existing = User.objects(email=email).first()
    if existing:
        raise ValueError("Email already registered")
    user = User(name=name, email=email, password=hash_password(password))
    user.save()
    return create_tokens(user)


def login_user(email: str, password: str) -> TokenPair:
    user = User.objects(email=email).first()
    if not user or not verify_password(password, user.password):
        raise ValueError("Invalid credentials")
    return create_tokens(user)


def logout_user(access_token: str) -> Dict[str, bool]:
    try:
        payload = jwt.decode(access_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("typ")
        if not user_id or token_type != "access":
            raise ValueError("Invalid token")
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    user = User.objects(id=user_id).first()
    if not user:
        raise ValueError("User not found")

    user.token_version = str(int(user.token_version) + 1)
    user.save()
    return {"status": True}


def sim_signup_user() -> None:
    state = _load_state()
    section = _ensure_section(state, "signup_user")
    inp = section["input"]
    try:
        name = inp.get("name")
        email = inp.get("email")
        password = inp.get("password")
        if not all([name, email, password]):
            raise ValueError("signup_user.input requires name, email, password")
        tokens = signup_user(name=name, email=email, password=password)
        user = User.objects(email=email).first()
        section["output"] = {
            "user_id": str(user.id) if user else None,
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
        }
    except Exception as exc:
        section["output"] = {"error": str(exc)}
    _save_state(state)


def sim_login_user() -> None:
    state = _load_state()
    section = _ensure_section(state, "login_user")
    inp = section["input"]
    try:
        email = inp.get("email")
        password = inp.get("password")
        # fallback to last signup if not provided
        if not email or not password:
            last = state.get("signup_user", {}).get("input", {})
            email = email or last.get("email")
            password = password or last.get("password")
        if not email or not password:
            raise ValueError("login_user.input requires email and password (or rely on signup_user.input)")
        tokens = login_user(email=email, password=password)
        section["output"] = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
        }
    except Exception as exc:
        section["output"] = {"error": str(exc)}
    _save_state(state)


def sim_logout_user() -> None:
    state = _load_state()
    section = _ensure_section(state, "logout_user")
    inp = section["input"]
    try:
        access_token = inp.get("access_token")
        # fallback to login output, then signup output
        if not access_token:
            access_token = state.get("login_user", {}).get("output", {}).get("access_token")
        if not access_token:
            access_token = state.get("signup_user", {}).get("output", {}).get("access_token")
        if not access_token:
            raise ValueError("logout_user.input requires access_token or run login_user first")
        result = logout_user(access_token)
        section["output"] = result
    except Exception as exc:
        section["output"] = {"error": str(exc)}
    _save_state(state)


def run_from_state() -> None:
    state = _load_state()
    funcs = state.get("funcs_to_run") or []
    name_to_func: Dict[str, Callable[[], None]] = {
        "signup_user": sim_signup_user,
        "login_user": sim_login_user,
        "logout_user": sim_logout_user,
    }
    for name in funcs:
        func = name_to_func.get(name)
        if not func:
            continue
        func()


# ----------------------------- Exam simulation helpers ----------------------------- #

def _score_submission(paper: Paper, question: Question, options_chosen: List[str]) -> Tuple[int, int]:
    """Mirror API scoring: returns (score, max_score) for this question in paper."""
    by_code = {opt.code: opt for opt in question.question_options}
    chosen_set = set(options_chosen or [])
    correct_set = {opt.code for opt in question.question_options if getattr(opt, "correct", False)}

    for pq in paper.paper_questions:
        if pq.question.code != question.code:
            continue
        # Any invalid or wrong selection yields negative
        if any(code not in by_code for code in chosen_set):
            return (-int(pq.negative_score), pq.positive_score)
        if chosen_set - correct_set:
            return (-int(pq.negative_score), pq.positive_score)

        qtype = str(question.type)
        if qtype == QuestionType.SINGLE_CORRECT.value:
            if not chosen_set:
                return (0, pq.positive_score)
            return (int(pq.positive_score), pq.positive_score)
        if qtype == QuestionType.MULTIPLE_CORRECT.value:
            total_weight = 0
            for code in chosen_set:
                opt = by_code.get(code)
                if getattr(opt, "correct", False):
                    total_weight += int(getattr(opt, "weight", 0) or 0)
            score = (total_weight * pq.positive_score) / 100
            return (int(score), pq.positive_score)
        return (0, pq.positive_score)
    # Not in paper
    return (0, 0)


def _random_choices_for_question(question: Question) -> List[str]:
    """Pick random options for a question (may be right or wrong)."""
    codes = [opt.code for opt in question.question_options]
    if str(question.type) == QuestionType.SINGLE_CORRECT.value:
        return [random.choice(codes)]
    # multiple-correct: choose 1..len(codes)
    k = random.randint(1, len(codes))
    return random.sample(codes, k=k)


def simulate_exam_for_dummy_users(exam_id: str) -> dict:
    """Enroll 3 dummy users into an exam, answer randomly, and end attempts."""
    exam: Exam | None = Exam.objects(id=exam_id).first()
    if not exam:
        raise ValueError("Exam not found")
    paper: Paper | None = exam.paper
    if not paper:
        raise ValueError("Exam paper not found")

    # Ensure three users exist; pick the first 3 by created time
    users = list(User.objects.order_by("created_at").limit(3))
    if len(users) < 3:
        raise ValueError("Not enough users to simulate")

    results: dict[str, str] = {}
    for user in users:
        # Enroll if missing
        attempt: TestAttempt | None = TestAttempt.objects(exam=exam, user=user).first()
        if not attempt:
            attempt = TestAttempt(
                exam=exam,
                paper=paper,
                user=user,
                type=TestType.COMPETITIVE.value,
                status=TestStatus.NOT_STARTED.value,
                enrolled_on=datetime.now(timezone.utc),
            )
            attempt.save()

        # Start attempt
        attempt.started_on = datetime.now(timezone.utc)
        attempt.status = TestStatus.IN_PROGRESS.value
        attempt.save()

        # Answer all questions in order with random choices
        for pq in sorted(paper.paper_questions, key=lambda x: x.order):
            question: Question = pq.question
            choices = _random_choices_for_question(question)
            score, max_score = _score_submission(paper, question, choices)
            sub = Submission(
                score=int(score),
                user=user,
                question=question,
                max_score=int(max_score),
                test_attempt=attempt,
                options_chosen=choices,
                subject_code=str(question.subject_code),
            )
            try:
                sub.save()
            except Exception:
                # duplicate for same question; skip
                continue

            # Lightweight aggregate updates (mirror API)
            attempt.total_score = int(attempt.total_score or 0) + int(score)
            paper_max = int(getattr(paper, "max_score", 0) or 0)
            if int(attempt.max_total_score or 0) != paper_max:
                attempt.max_total_score = paper_max

            subj_code = str(question.subject_code)
            subj_max_map = {ps.subject_code: int(ps.max_score or 0) for ps in (paper.subject_max_scores or [])}
            subj_max = subj_max_map.get(subj_code, 0)
            by_subj = {ss.subject_code: ss for ss in (attempt.subject_scores or [])}
            current = by_subj.get(subj_code)
            if current:
                current.total_score = int(getattr(current, "total_score", 0) or 0) + int(score)
                current.max_total_score = int(subj_max)
            else:
                attempt.subject_scores.append(TestSubjectScore(
                    subject_code=subj_code,
                    total_score=int(score),
                    max_total_score=int(subj_max),
                ))
            attempt.save()

        # End attempt
        attempt.status = TestStatus.COMPLETED.value
        attempt.ended_on = datetime.now(timezone.utc)
        attempt.save()
        results[str(user.id)] = str(attempt.id)

    return {"attempts": results}


def trigger_aftermath_now(exam_id: str) -> dict:
    """Manually execute aftermath computation synchronously for an exam."""
    conclude_exam(exam_id)
    return {"status": True}


