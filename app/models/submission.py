from datetime import datetime, timezone
from mongoengine import ReferenceField, StringField, DateTimeField, ListField, IntField

from app.models.user import User
from app.models.paper import Paper
from app.models.question import Question
from app.models.test_attempt import TestAttempt
from app.models.base import BaseDocument
from app.utils.base import SubjectCode


class Submission(BaseDocument):
    """Atomic answer record for a question within an attempt.

    Fields: 
    - user/paper/question/test_attempt (refs), 
    - options_chosen (list[str]),
    - subject_code (str), 
    - submitted_at (datetime), 
    - score/max_score (int).
    Unique per (test_attempt, question, user).
    """
    user = ReferenceField(document_type=User, required=True, null=False)
    paper = ReferenceField(document_type=Paper, required=True, null=False)
    question = ReferenceField(document_type=Question, required=True, null=False)
    test_attempt = ReferenceField(document_type=TestAttempt, required=True, null=False) 

    options_chosen = ListField(StringField(), required=False, null=True)
    subject_code = StringField(required=True, null=False, choices=SubjectCode.choices())
    submitted_at = DateTimeField(default=lambda: datetime.now(timezone.utc), null=False)
    max_score = IntField(required=True, null=False, default=0, min_value=0)
    score = IntField(required=True, null=False, default=0, min_value=0)

    meta = {
        "collection": "submissions",
        "indexes": [
            {"fields": ["test_attempt", "question", "user"], "unique": True},
            {"fields": ["user", "paper"]},
            {"fields": ["test_attempt"]},
            {"fields": ["subject_code"]},
        ],
        "unique_together": (("test_attempt", "question", "user"),),
    }