from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_MESSAGES = 12
MAX_MESSAGE_CHARACTERS = 4_000


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARACTERS)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message content must not be blank.")
        return content


class ChatContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_player_id: int | None = Field(default=None, gt=0)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    context: ChatContext | None = None

    @model_validator(mode="after")
    def latest_message_must_be_from_user(self) -> ChatRequest:
        if self.messages[-1].role != "user":
            raise ValueError("The most recent chat message must be from the user.")
        return self


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
