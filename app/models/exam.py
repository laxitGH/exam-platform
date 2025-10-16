from mongoengine import DateTimeField, DateField, ReferenceField, StringField, IntField

from app.models.base import BaseDocument
from app.models.paper import Paper
from app.utils.base import BaseEnum


class ExamStatus(BaseEnum):
    COMPLETED = "completed"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"


class Exam(BaseDocument):
    """Exam document.

    Links a `paper` to a scheduled window. Tracks enrollment and aggregated outcomes.

    Fields:
    - paper (Ref[Paper])
    - status (str): upcoming/ongoing/completed
    - start_time/end_time/date (datetime/date): schedule
    - concluded_on (datetime|None): when results were finalized
    - enrolled_count/attempted_count (int): counters
    - highest_score/lowest_score/max_score (int): exam-level scoring aggregates
    """
    paper = ReferenceField(document_type=Paper, required=True, null=False)
    status = StringField(required=True, null=False, choices=ExamStatus.choices())
    start_time = DateTimeField(required=True, null=False)
    end_time = DateTimeField(required=True, null=False)
    date = DateField(required=True, null=False)

    concluded_on = DateTimeField(required=False, null=True)
    enrolled_count = IntField(required=True, null=False, default=0)
    attempted_count = IntField(required=True, null=False, default=0)
    highest_score = IntField(required=True, null=False, default=0)
    lowest_score = IntField(required=True, null=False, default=0)
    max_score = IntField(required=True, null=False, default=0)

    meta = {
        "collection": "exams",
        "indexes": [
            {"fields": ["paper", "date", "start_time"],
             "unique": True},
            {"fields": ["date"]},
            {"fields": ["paper"]},
        ],
    }
