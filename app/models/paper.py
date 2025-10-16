from mongoengine import StringField, ReferenceField, ListField, IntField, BooleanField, EmbeddedDocumentField

from app.models.base import BaseDocument, BaseEmbeddedDocument
from app.utils.base import BaseEnum, SubjectCode
from app.models.question import Question


class PaperType(BaseEnum):
    REAL = "real"
    MOCK = "mock"
    INTERNAL = "internal"


class PaperQuestion(BaseEmbeddedDocument):
    """Embedded: configuration for a question within a paper.

    Fields: 
    - mandatory (bool), 
    - order (int), 
    - question (Ref[Question]),
    - negative_score (int), 
    - positive_score (int).
    """
    mandatory = BooleanField(required=True, null=False, default=False)
    order = IntField(required=True, null=False, default=0, min_value=0)
    question = ReferenceField(document_type=Question, required=True, null=False)
    negative_score = IntField(required=True, null=False)
    positive_score = IntField(required=True, null=False)


class PaperSubjectMaxScore(BaseEmbeddedDocument):
    """Embedded: maximum achievable score per subject within a paper."""
    subject_code = StringField(required=True, null=False, choices=SubjectCode.choices())
    max_score = IntField(required=True, null=False, default=0, min_value=0)


class Paper(BaseDocument):
    """Paper template.

    Fields:
    - name/code (str)
    - type (str): real/mock/internal
    - max_score (int): sum of positive_score of all paper_questions
    - subject_max_scores (list): per-subject max
    - duration_minutes (int)
    - paper_questions (list[PaperQuestion])
    """
    name = StringField(required=True, null=False)
    code = StringField(required=True, null=False, unique=True)
    max_score = IntField(required=True, null=False, default=0, min_value=0)
    type = StringField(required=True, null=False, choices=PaperType.choices())
    subject_max_scores = ListField(EmbeddedDocumentField(PaperSubjectMaxScore), null=False, default=list)
    duration_minutes = IntField(required=True, null=False)

    paper_questions = ListField(EmbeddedDocumentField(PaperQuestion), null=False, default=list)

    meta = {
        "collection": "papers",
        "indexes": [
            {"fields": ["code"], "unique": True},
            {"fields": ["name"]},
        ],
    }
