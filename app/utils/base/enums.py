from enum import Enum


class BaseEnum(Enum):
    @classmethod
    def choices(cls):
        return [(item.value, item.name) for item in cls]


class SubjectCode(BaseEnum):
    MATHS = "maths"
    SCIENCE = "science"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    GENERAL_KNOWLEDGE = "general_knowledge"
