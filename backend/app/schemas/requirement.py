"""需求解析结果的结构化 Schema（Pydantic 校验，防止模型输出不可用格式）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FieldSpec(BaseModel):
    name: str
    label: str = ""
    type: Literal["string", "number", "date", "enum", "boolean", "text"] = "string"
    required: bool = False
    options: list[str] = Field(default_factory=list)


class PageSpec(BaseModel):
    name: str
    type: Literal["table", "form", "detail", "config", "login", "dashboard"] = "table"
    description: str = ""
    fields: list[FieldSpec] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    apis: list[str] = Field(default_factory=list)
    priority: int = 1


class RequirementSpec(BaseModel):
    project_name: str = ""
    pages: list[PageSpec] = Field(default_factory=list)
    confidence: float = 0.6
    notes: str = ""


def spec_to_dict(spec: RequirementSpec) -> dict:
    return spec.model_dump()
