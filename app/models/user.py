from mongoengine import EmailField, StringField
from app.models.base import BaseDocument


class User(BaseDocument):
    """User document.

    Fields:
    - name (str): Full name
    - email (EmailStr, unique): Login identifier
    - password (str, hashed): Bcrypt-hashed password
    - token_version (str): Incremented on logout to invalidate tokens
    """
    name = StringField(required=True, null=False)
    password = StringField(required=True, null=False)
    email = EmailField(required=True, null=False, unique=True)
    token_version = StringField(required=True, null=False, default="1")

    meta = {
        "collection": "users",
        "indexes": [
            {"fields": ["email"], "unique": True},
        ],
    }
