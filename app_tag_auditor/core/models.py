from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

class ExpectedEvent(BaseModel):
    event_name: str
    screen: str
    expected_params: dict[str, Any] = Field(default_factory=dict)
    trigger_description: str
    keywords: list[str] = Field(default_factory=list)

class CodeLocation(BaseModel):
    event_name: str
    file_path: str
    line_number: int
    matched_snippet: str
    breadcrumb: list[str] = Field(default_factory=list)
    confidence: float

class CrawlStep(BaseModel):
    action_type: Literal["tap", "input", "swipe", "wait", "back"]
    target_selector: str
    value: Optional[str] = None
    step_order: int

class CrawlPlan(BaseModel):
    event_name: str
    steps: list[CrawlStep] = Field(default_factory=list)

class CapturedLog(BaseModel):
    event_name: str
    raw_params: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    source: Literal["logcat"]

class TelemetryValidationResult(BaseModel):
    event_name: str
    passed: bool
    mismatched_keys: list[str] = Field(default_factory=list)
    missing_keys: list[str] = Field(default_factory=list)
    extra_keys: list[str] = Field(default_factory=list)

class RuntimeValidationResult(BaseModel):
    event_name: str
    passed: bool
    expected_trigger: str
    actual_trigger_observed: bool
    notes: str

class FinalAuditRow(BaseModel):
    event_name: str
    screen: str
    telemetry_passed: bool
    runtime_passed: bool
    overall_status: Literal["PASS", "FAIL", "PARTIAL"]
    details: str
    timestamp: str
