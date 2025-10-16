from mongoengine import StringField, ListField, URLField, ValidationError, BooleanField, IntField, EmbeddedDocumentField

from app.utils.base import BaseEnum, SubjectCode
from app.models.base import BaseDocument, BaseEmbeddedDocument


class QuestionType(BaseEnum):
    SINGLE_CORRECT = "single_correct"
    MULTIPLE_CORRECT = "multiple_correct"


class OptionType(BaseEnum):
    TEXT = "text"
    IMAGE = "image"


class QuestionOption(BaseEmbeddedDocument):
    """Embedded: an option for a question.

    Fields: 
    - correct (bool), 
    - order (int), 
    - weight (0-100 if correct),
    - type (text/image), 
    - code (str), 
    - image_url/text.
    """
    correct = BooleanField(required=True, null=False)
    order = IntField(required=True, null=False, default=0, min_value=0)
    weight = IntField(required=True, null=False, default=0, min_value=0, max_value=100)
    type = StringField(required=True, null=False, choices=OptionType.choices())
    code = StringField(required=True, null=False, unique=True)
    image_url = URLField(required=False, null=True)
    text = StringField(required=False, null=True)


class Question(BaseDocument):
    """Question bank entry.

    Fields: 
    - statement (str), 
    - code (str, unique), 
    - subject_code (str), 
    - type (single_correct/multiple_correct),
    - question_options (list[QuestionOption]).
    Validate enforces total weight of correct options equals 100.
    """
    code = StringField(required=True, null=False, unique=True)
    type = StringField(required=True, null=False, choices=QuestionType.choices())
    subject_code = StringField(required=True, null=False, choices=SubjectCode.choices())

    statement = StringField(required=True, null=False)
    question_options = ListField(EmbeddedDocumentField(QuestionOption), null=False, required=True, default=list)

    meta = {
        "collection": "questions",
        "indexes": [
            {"fields": ["code"], "unique": True},
            {"fields": ["subject_code"]},
        ],
    }

    def validate(self, clean=True):
        super().validate(clean)
        if not self.question_options:
            raise ValidationError("Options are required")
        
        total_weight = sum(option.weight if option.correct else 0 for option in self.question_options)
        if total_weight != 100:
            raise ValidationError("Total weight of correct options should be 100")

    def to_output(self, fields=None, exclude=None):
        output = super().to_output(fields, exclude)
        
        new_question_options = []
        question_options = output.pop("question_options")
        for option in question_options:
            option.pop("correct")
            option.pop("weight")
            new_question_options.append(option)
        
        output["question_options"] = new_question_options
        return output
