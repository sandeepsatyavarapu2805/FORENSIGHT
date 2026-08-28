import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class CaseWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class CaseCreate(CaseWrite):
    pass


class CaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_null_or_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("name must not be null")
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class CaseResponse(CaseWrite):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_identifier: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SourceCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("label")
    @classmethod
    def label_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("label must not be blank")
        return value


class SourceUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("label")
    @classmethod
    def label_must_not_be_null_or_blank(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("label must not be null")
        value = value.strip()
        if not value:
            raise ValueError("label must not be blank")
        return value


class SourceResponse(SourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
