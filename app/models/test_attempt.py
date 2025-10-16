from mongoengine import ReferenceField, DateTimeField, StringField, IntField, ListField, FloatField, EmbeddedDocumentField

from app.models.exam import Exam
from app.models.user import User
from app.models.paper import Paper
from app.utils.base import BaseEnum, SubjectCode
from app.models.base import BaseDocument, BaseEmbeddedDocument


class TestType(BaseEnum):
    COMPETITIVE = "COMPETITIVE"
    PRACTICE = "PRACTICE"


class TestStatus(BaseEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TestSubjectScore(BaseEmbeddedDocument):
    """Embedded: per-subject score and standings for an attempt.

    Fields: 
    - subject_code (str), 
    - total_score (int), 
    - max_total_score (int),
    - percentile (float|None), 
    - rank (int|None).
    """
    total_score = IntField(required=True, null=False)
    subject_code = StringField(required=True, null=False, choices=SubjectCode.choices())
    max_total_score = IntField(required=True, null=False)
    percentile = FloatField(required=False, null=True)
    rank = IntField(required=False, null=True)


class TestAttempt(BaseDocument):
    """A user's attempt of a paper (optionally tied to an exam).

    Fields:
    - paper/user/exam (refs)
    - status/type and timestamps
    - total_score/max_total_score (int)
    - subject_scores (list[TestSubjectScore])
    - percentile/rank: computed in aftermath
    """
    paper = ReferenceField(document_type=Paper, required=True, null=False)
    user = ReferenceField(document_type=User, required=True, null=False)
    exam = ReferenceField(document_type=Exam, required=False, null=True)

    ended_on = DateTimeField(required=False, null=True)
    started_on = DateTimeField(required=False, null=True)
    enrolled_on = DateTimeField(required=False, null=True)
    concluded_on = DateTimeField(required=False, null=True)
    
    type = StringField(required=True, null=False, choices=TestType.choices())
    status = StringField(required=True, null=False, choices=TestStatus.choices())

    total_score = IntField(required=True, null=False, default=0)
    max_total_score = IntField(required=True, null=False, default=0)
    subject_scores = ListField(EmbeddedDocumentField(TestSubjectScore), required=True, default=list, null=False)
    percentile = FloatField(required=False, null=True)
    rank = IntField(required=False, null=True)

    meta = {
        "collection": "test_attempts",
        "indexes": [
            {"fields": ["exam", "user"], "unique": True, "partialFilterExpression": {"exam": {"$exists": True}}},
            {"fields": ["paper", "user", "started_on"]},
        ],
    }
