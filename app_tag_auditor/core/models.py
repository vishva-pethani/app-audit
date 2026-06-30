from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

class ExpectedParam(BaseModel):
    param_name: str
    parameter_type: str
    data_type: str
    principle: str
    example_value: str

class ExpectedEvent(BaseModel):
    event_name: str
    screen: str
    user_action: str
    expected_params: list[ExpectedParam] = Field(default_factory=list)
    raw_principle: str
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
    selector_strategy: Literal["text", "resource_id", "content_desc", "accessibility_id"] = "text"

class CrawlPlan(BaseModel):
    event_name: str
    screen: str = ""
    steps: list[CrawlStep] = Field(default_factory=list)
    navigation_resolved: bool = True


class CapturedLog(BaseModel):
    event_name: str
    raw_params: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    source: Literal["logcat"]

class EventRuntimeCapture(BaseModel):
    event_name: str
    trigger_timestamp: str
    captured_logs: list[CapturedLog]
    detected_screen_after: Optional[str]
    detection_source: Literal["signature", "activity", "unknown"]
    detected_screen_immediately: Optional[str] = None
    detection_source_immediate: Literal["signature", "activity", "unknown"] = "unknown"

class TelemetryValidationResult(BaseModel):
    event_name: str
    screen: str = ""
    passed: bool
    mismatched_keys: list[str] = Field(default_factory=list)
    missing_keys: list[str] = Field(default_factory=list)
    extra_keys: list[str] = Field(default_factory=list)
    matched_log: Optional[CapturedLog] = None

class RuntimeValidationResult(BaseModel):
    event_name: str
    screen: str = ""
    passed: bool
    expected_trigger: str
    actual_trigger_observed: bool
    notes: str
    fire_count: int = 0
    not_implemented: bool = False
    double_fired: bool = False
    screen_check_status: Literal["correct", "incorrect", "unknown"] = "unknown"
    unexpected_co_fired_events: list[str] = Field(default_factory=list)

class FinalAuditRow(BaseModel):
    event_name: str
    screen: str
    telemetry_passed: bool
    runtime_passed: bool
    overall_status: Literal["PASS", "FAIL", "PARTIAL"]
    details: str
    timestamp: str


class ExpectedEcomEvent(BaseModel):
    event_name: str
    user_action: str
    event_param_names: list[str]
    required_item_param_names: list[str]
    min_items: int
    keywords: list[str]


class CapturedEcomLog(BaseModel):
    event_name: str
    top_level_params: dict
    items: list[dict]
    timestamp: str
    source: Literal["logcat"]


class EcomTelemetryValidationResult(BaseModel):
    event_name: str
    passed: bool
    missing_event_keys: list[str]
    extra_event_keys: list[str]
    mismatched_event_keys: list[str]
    item_count_found: int
    item_count_expected_min: int
    item_count_passed: bool
    items_with_missing_keys: list[dict]
    items_with_type_errors: list[dict]
    items_with_custom_params: list[dict]
    items_with_discount_revenue_errors: list[dict]

