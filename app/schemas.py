from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    logical_key: str
    heading: str
    level: int
    body_text: str
    content_hash: str
    change_status: str
    parent_id: int | None
    order_index: int

class SelectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    node_ids: list[int] = Field(min_length=1)
    version: int | None = None

class TestCase(BaseModel):
    title: str = Field(min_length=4, max_length=300)
    objective: str = Field(min_length=5)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=5)
    priority: Literal["Low", "Medium", "High", "Critical"] = "Medium"
    requirement_refs: list[str] = Field(default_factory=list)

class GenerationPayload(BaseModel):
    selection_id: int
    test_cases: list[TestCase] = Field(min_length=3, max_length=5)
    model: str = "local-fallback"

class GenerationIn(BaseModel):
    selection_id: int
    force_new: bool = False
