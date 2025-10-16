from datetime import datetime, timezone
from typing import Any
from bson.objectid import ObjectId
from mongoengine import Document, DictField, DateTimeField, EmbeddedDocument


class BaseDocumentMixin:
    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, Document):
            return value.to_output() if hasattr(value, "to_output") else str(value.id)
        elif isinstance(value, EmbeddedDocument):
            value = {k: self._sanitize_value(getattr(value, k)) for k in value._fields}
        if isinstance(value, list):
            return [self._sanitize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, ObjectId):
            return str(value)
        return value

    def to_output(self, fields=None, exclude=None):
        data: dict[str, Any] = {}
        exclude = exclude or []
        fields = fields or self._fields.keys()

        for field in fields:
            if field in exclude:
                continue
            value = getattr(self, field)
            data[field] = self._sanitize_value(value)

        data["id"] = str(self.id)
        return data

    def to_dict(self, fields=None, exclude=None):
        return self.to_output(fields=fields, exclude=exclude)

class BaseEmbeddedDocument(EmbeddedDocument, BaseDocumentMixin):
    meta = {
        "abstract": True,
    }


class BaseDocument(Document, BaseDocumentMixin):
    metadata = DictField(default=dict, null=False)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc), null=False)
    updated_at = DateTimeField(default=lambda: datetime.now(timezone.utc), null=False)

    meta = {
        "abstract": True,
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)
