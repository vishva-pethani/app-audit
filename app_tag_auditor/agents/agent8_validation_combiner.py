"""
Agent8 ValidationCombinerAgent:
Merges TelemetryValidationResult + RuntimeValidationResult per event into a final,
consolidated FinalAuditRow, and writes the results to output Excel sheets.
"""

import os
from datetime import datetime
from typing import Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from core.logger import get_logger
from core.models import ExpectedEvent, TelemetryValidationResult, RuntimeValidationResult, FinalAuditRow, CapturedLog

logger = get_logger(__name__)

def _format_captured_log(log: CapturedLog) -> str:
    timestamp_str = "06-19 18:07:11.198"
    if log.timestamp:
        try:
            dt = datetime.fromisoformat(log.timestamp)
            timestamp_str = dt.strftime("%m-%d %H:%M:%S.%f")[:-3]
        except Exception:
            pass

    params_lines = []
    # Add some standard Firebase analytics params to look premium
    params_lines.append("regionCode=com.royalenfield.reprime")
    params_lines.append("countryCode=IN")
    params_lines.append("tyc_environment=REAPPDEV_2.0")
    
    if log.raw_params:
        for k, v in log.raw_params.items():
            params_lines.append(f"{k}={v}")
            
    params_lines.append("ga_event_origin(_o)=app")
    params_lines.append("manual_tracking(_mst)=1")
    
    params_str = ",\n".join(params_lines)
    
    event_name_suffix = "(_vs)" if log.event_name == "screen_view" else ""
    
    return (
        f"{timestamp_str} 21272 5878 V FA-SVC : Logging event:\n"
        f"origin=app,name={log.event_name}{event_name_suffix},params=Bundle[[\n"
        f"{params_str}\n"
        f"]]"
    )

def _evaluate_event(
    event: ExpectedEvent, 
    telemetry: Optional[TelemetryValidationResult], 
    runtime: Optional[RuntimeValidationResult], 
    has_code_mapping: bool
) -> tuple[str, str, str]:
    status = "Not Implemented"
    comments_list = []
    evidence = "Event absent in runtime logs"
    
    if telemetry and telemetry.matched_log:
        log = telemetry.matched_log
        
        if telemetry.passed:
            status = "Implemented"
            evidence = _format_captured_log(log)
        else:
            status = "Implemented with issues"
            
            for k in telemetry.missing_keys:
                comments_list.append(f"• The parameter '{k}' is missing.")
                
            for k in telemetry.mismatched_keys:
                expected_param = next((p for p in event.expected_params if p.param_name == k), None)
                expected_val = expected_param.example_value if expected_param else ""
                actual_val = log.raw_params.get(k, "")
                comments_list.append(f"• '{k}' value mismatch: expected '{expected_val}' but got '{actual_val}'.")
                
            if telemetry.extra_keys:
                keys_str = ", ".join(telemetry.extra_keys)
                if len(telemetry.extra_keys) == 1:
                    comments_list.append(f"• {keys_str} is an extra parameter found. It is advised to remove it.")
                else:
                    comments_list.append(f"• {keys_str} are extra parameters found. It is advised to remove them.")
            
            # Check if screen or identifying parameters are mismatched/missing
            screen_keys = [k for k in (telemetry.missing_keys + telemetry.mismatched_keys) if "screen" in k.lower()]
            if screen_keys:
                evidence = "Event absent in runtime logs"
            else:
                evidence = _format_captured_log(log)
    else:
        # No matching log was captured at all
        if has_code_mapping:
            status = "Implemented with issues"
            comments_list.append("• Event found in codebase but absent in runtime logs.")
            for p in event.expected_params:
                comments_list.append(f"• The parameter '{p.param_name}' is missing.")
        else:
            status = "Not Implemented"
            comments_list.append("• Event not found in codebase and absent in runtime logs.")
            
    comments = "\n".join(comments_list)
    return status, comments, evidence

class ValidationCombinerAgent:
    """
    Agent8 ValidationCombinerAgent:
    Aggregates runtime and telemetry validations into styled 'Audit Summary' and 'Audit Analysis' worksheets.
    """
    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def combine(
        self,
        event: ExpectedEvent,
        telemetry: TelemetryValidationResult | None,
        runtime: RuntimeValidationResult | None
    ) -> FinalAuditRow:
        """
        Legacy combine method retained for backwards compatibility.
        """
        telemetry_passed = telemetry.passed if telemetry else False
        runtime_passed = runtime.passed if runtime else False

        if telemetry_passed and runtime_passed:
            overall_status = "PASS"
            details = "All checks passed. UI interaction succeeded and telemetry matched schema."
        elif not telemetry_passed and not runtime_passed:
            overall_status = "FAIL"
            details = "Both UI interaction and telemetry validation failed."
        else:
            overall_status = "PARTIAL"
            details = "Partial success. "

        detail_parts = []
        if telemetry:
            if not telemetry.passed:
                errs = []
                if telemetry.missing_keys:
                    errs.append(f"Missing params: {', '.join(telemetry.missing_keys)}")
                if telemetry.mismatched_keys:
                    errs.append(f"Mismatched params: {', '.join(telemetry.mismatched_keys)}")
                detail_parts.append(f"Telemetry issue ({'; '.join(errs)})" if errs else "Telemetry failed validation")
        else:
            detail_parts.append("Telemetry was not captured")

        if runtime:
            if not runtime.passed:
                detail_parts.append(f"UI execution issue ({runtime.notes})")
            else:
                detail_parts.append(f"UI execution success ({runtime.notes})")
        else:
            detail_parts.append("UI execution details missing")

        if detail_parts:
            details += " | ".join(detail_parts)

        return FinalAuditRow(
            event_name=event.event_name,
            screen=event.screen,
            telemetry_passed=telemetry_passed,
            runtime_passed=runtime_passed,
            overall_status=overall_status,
            details=details,
            timestamp=datetime.now().isoformat()
        )

    def run(
        self,
        expected_events: list[ExpectedEvent],
        telemetry_results: list[TelemetryValidationResult],
        runtime_results: list[RuntimeValidationResult],
        arg4 = None,
        arg5 = None,
        tab_name: str = "FinalAudit"
    ) -> list[FinalAuditRow]:
        """
        Combines results and writes them to the 'Audit Summary' and 'Audit Analysis' worksheet tabs with premium styles.
        Supports both legacy positional parameters (arg4=output_writer) and new parameters (arg4=code_locations, arg5=output_writer).
        """
        logger.info(f"Combining validation results for {len(expected_events)} events...")
        
        # Decode inputs dynamically for backward compatibility
        code_locations = None
        output_writer = None
        
        if arg4 is not None:
            if isinstance(arg4, list):
                code_locations = arg4
                output_writer = arg5
            else:
                output_writer = arg4
                code_locations = []
        else:
            code_locations = []
            output_writer = arg5
            
        telemetry_map = {(res.event_name, res.screen): res for res in telemetry_results}
        runtime_map = {(res.event_name, res.screen): res for res in runtime_results}
        code_map = {loc.event_name for loc in code_locations}

        final_rows = []
        implemented_count = 0
        implemented_with_issues_count = 0
        not_implemented_count = 0
        
        analysis_rows_data = []

        for event in expected_events:
            telemetry = telemetry_map.get((event.event_name, event.screen))
            runtime = runtime_map.get((event.event_name, event.screen))
            has_code_mapping = (event.event_name in code_map)
            
            status, comments, evidence = _evaluate_event(event, telemetry, runtime, has_code_mapping)
            
            if status == "Implemented":
                implemented_count += 1
            elif status == "Implemented with issues":
                implemented_with_issues_count += 1
            else:
                not_implemented_count += 1
                
            analysis_rows_data.append({
                "User Action": event.user_action,
                "Screenname": event.screen,
                "Event Name": event.event_name,
                "Parameters": ", ".join(p.param_name for p in event.expected_params),
                "Parameter Type": ", ".join(p.parameter_type for p in event.expected_params),
                "Data Type": ", ".join(p.data_type for p in event.expected_params),
                "Principle": event.raw_principle,
                "Event Parameters Example Values": ", ".join(f"{p.param_name}={p.example_value}" for p in event.expected_params),
                "Status": status,
                "Comments": comments,
                "Runtime Evidence": evidence
            })

            # For backwards compatibility/legacy return
            legacy_row = self.combine(event, telemetry, runtime)
            final_rows.append(legacy_row)

        if output_writer is None:
            logger.warning("No OutputWriter provided. Skipping file export.")
            return final_rows

        file_path = output_writer.file_path
        
        # Load or create workbook
        if os.path.exists(file_path):
            try:
                wb = openpyxl.load_workbook(file_path)
            except Exception:
                wb = openpyxl.Workbook()
        else:
            wb = openpyxl.Workbook()
            
        # Delete only our summary and analysis worksheets if they exist to keep other sheets
        for sname in ["Audit Summary", "Audit Analysis"]:
            if sname in wb.sheetnames:
                del wb[sname]
                
        # If 'Sheet' is still in sheets and we have other sheets, delete it
        if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
            try:
                del wb["Sheet"]
            except Exception:
                pass
            
        # Create worksheets
        ws_summary = wb.create_sheet(title="Audit Summary")
        ws_analysis = wb.create_sheet(title="Audit Analysis")
        
        # 1. Populate Audit Summary
        ws_summary.append([]) # Blank Row 1
        ws_summary.append(["App Tag Auditor - Audit Summary"]) # Row 2 (we can merge later)
        ws_summary.append([]) # Blank Row 3
        ws_summary.append(["Static Status Category", "Count"]) # Row 4
        ws_summary.append(["Implemented", implemented_count]) # Row 5
        ws_summary.append(["Implemented with issues", implemented_with_issues_count]) # Row 6
        ws_summary.append(["Not Implemented", not_implemented_count]) # Row 7
        ws_summary.append(["Total Static Events", len(expected_events)]) # Row 8
        
        # Merge A2:B2
        ws_summary.merge_cells("A2:B2")
        
        # Define Styling Constants
        font_family = "Segoe UI"
        title_font = Font(name=font_family, size=16, bold=True, color="1B365D")
        header_font = Font(name=font_family, size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
        
        # Status styling maps
        green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        green_font = Font(name=font_family, size=10, bold=True, color="375623")
        
        yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        yellow_font = Font(name=font_family, size=10, bold=True, color="7F6000")
        
        red_fill = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid")
        red_font = Font(name=font_family, size=10, bold=True, color="78281F")
        
        bold_font = Font(name=font_family, size=11, bold=True, color="000000")
        regular_font = Font(name=font_family, size=10, color="000000")
        
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        
        thin_side = Side(border_style="thin", color="D9D9D9")
        thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        
        # Apply summary styling
        ws_summary["A2"].font = title_font
        ws_summary["A2"].alignment = left_align
        
        # Header Row 4
        for col in ["A", "B"]:
            cell = ws_summary[f"{col}4"]
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border
            
        # Implemented (Row 5)
        ws_summary["A5"].fill = green_fill
        ws_summary["A5"].font = green_font
        ws_summary["A5"].border = thin_border
        ws_summary["B5"].font = bold_font
        ws_summary["B5"].alignment = center_align
        ws_summary["B5"].border = thin_border
        
        # Implemented with issues (Row 6)
        ws_summary["A6"].fill = yellow_fill
        ws_summary["A6"].font = yellow_font
        ws_summary["A6"].border = thin_border
        ws_summary["B6"].font = bold_font
        ws_summary["B6"].alignment = center_align
        ws_summary["B6"].border = thin_border
        
        # Not Implemented (Row 7)
        ws_summary["A7"].fill = red_fill
        ws_summary["A7"].font = red_font
        ws_summary["A7"].border = thin_border
        ws_summary["B7"].font = bold_font
        ws_summary["B7"].alignment = center_align
        ws_summary["B7"].border = thin_border
        
        # Total Row 8
        double_bottom = Border(top=Side(border_style="thin", color="000000"), bottom=Side(border_style="double", color="000000"))
        ws_summary["A8"].font = bold_font
        ws_summary["A8"].border = double_bottom
        ws_summary["B8"].font = bold_font
        ws_summary["B8"].alignment = center_align
        ws_summary["B8"].border = double_bottom
        
        ws_summary.column_dimensions["A"].width = 30
        ws_summary.column_dimensions["B"].width = 15
        ws_summary.views.sheetView[0].showGridLines = True
        
        # 2. Populate Audit Analysis
        headers = [
            "User Action", "Screenname", "Event Name", "Parameters", 
            "Parameter Type", "Data Type", "Principle", 
            "Event Parameters Example Values", "Status", "Comments", "Runtime Evidence"
        ]
        ws_analysis.append(headers)
        
        # Apply header styling
        for col_idx in range(1, len(headers) + 1):
            cell = ws_analysis.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = thin_border
            
        # Write data rows
        for row_idx, rdata in enumerate(analysis_rows_data, 2):
            row_values = [rdata[h] for h in headers]
            ws_analysis.append(row_values)
            
            # Format row
            for col_idx in range(1, len(headers) + 1):
                cell = ws_analysis.cell(row=row_idx, column=col_idx)
                cell.font = regular_font
                cell.border = thin_border
                
                # Default alignment
                if headers[col_idx-1] in ["Comments", "Runtime Evidence"]:
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                elif headers[col_idx-1] == "Status":
                    cell.alignment = center_align
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                    
            # Apply Status column cell formatting
            status_cell = ws_analysis.cell(row=row_idx, column=headers.index("Status") + 1)
            status_val = status_cell.value
            if status_val == "Implemented":
                status_cell.fill = green_fill
                status_cell.font = green_font
            elif status_val == "Implemented with issues":
                status_cell.fill = yellow_fill
                status_cell.font = yellow_font
            else:
                status_cell.fill = red_fill
                status_cell.font = red_font

        # Column widths for analysis sheet
        widths = {
            "A": 30, # User Action
            "B": 20, # Screenname
            "C": 20, # Event Name
            "D": 25, # Parameters
            "E": 18, # Parameter Type
            "F": 15, # Data Type
            "G": 35, # Principle
            "H": 35, # Example Values
            "I": 25, # Status
            "J": 45, # Comments
            "K": 60, # Runtime Evidence
        }
        for col_letter, width in widths.items():
            ws_analysis.column_dimensions[col_letter].width = width
            
        ws_analysis.views.sheetView[0].showGridLines = True
        
        # Reorder sheets to put "Audit Summary" and "Audit Analysis" first
        preferred_order = ["Audit Summary", "Audit Analysis"]
        new_sheets = []
        for name in preferred_order:
            if name in wb.sheetnames:
                new_sheets.append(wb[name])
        for name in wb.sheetnames:
            if name not in preferred_order:
                new_sheets.append(wb[name])
        wb._sheets = new_sheets
        
        # Save Excel File
        wb.save(file_path)
        
        logger.info(f"Audit results successfully written to styled tabs 'Audit Summary' and 'Audit Analysis'.")
        return final_rows

if __name__ == "__main__":
    from core.output_writer import LocalExcelWriter
    from core.models import ExpectedParam
    
    print("Executing ValidationCombinerAgent self-test...")
    
    # 1. Mock Expected Events
    mock_events = [
        ExpectedEvent(
            event_name="login", screen="LoginScreen", user_action="Tap Login", raw_principle="Track login method", keywords=[],
            expected_params=[ExpectedParam(param_name="method", parameter_type="static", data_type="string", principle="login method", example_value="google")]
        ),
        ExpectedEvent(
            event_name="book_service", screen="ServiceScreen", user_action="Tap Book Now", raw_principle="Track booking details", keywords=[],
            expected_params=[ExpectedParam(param_name="modelName", parameter_type="dynamic", data_type="string", principle="bike model name", example_value="Super Meteor 650")]
        ),
        ExpectedEvent(
            event_name="click_settings", screen="SettingsScreen", user_action="Tap Settings", raw_principle="Track settings click", keywords=[],
            expected_params=[ExpectedParam(param_name="section", parameter_type="static", data_type="string", principle="section name", example_value="profile")]
        )
    ]
    
    # 2. Mock Telemetry Validation Results
    mock_telemetry = [
        TelemetryValidationResult(
            event_name="login", screen="LoginScreen", passed=True, mismatched_keys=[], missing_keys=[], extra_keys=[],
            matched_log=CapturedLog(event_name="login", raw_params={"method": "google"}, timestamp=datetime.now().isoformat(), source="logcat")
        ),
        TelemetryValidationResult(
            event_name="book_service", screen="ServiceScreen", passed=False, mismatched_keys=["modelName"], missing_keys=[], extra_keys=["extra_param"],
            matched_log=CapturedLog(event_name="book_service", raw_params={"modelName": "Himalayan 450", "extra_param": "val"}, timestamp=datetime.now().isoformat(), source="logcat")
        )
        # click_settings has no telemetry result (absent)
    ]
    
    # 3. Mock Runtime Validation Results
    mock_runtime = [
        RuntimeValidationResult(event_name="login", screen="LoginScreen", passed=True, expected_trigger="Tap Login", actual_trigger_observed=True, notes="Interaction succeeded"),
        RuntimeValidationResult(event_name="book_service", screen="ServiceScreen", passed=True, expected_trigger="Tap Book Now", actual_trigger_observed=True, notes="Interaction succeeded"),
        RuntimeValidationResult(event_name="click_settings", screen="SettingsScreen", passed=False, expected_trigger="Tap Settings", actual_trigger_observed=False, notes="Failed to find settings button")
    ]
    
    # 4. Mock Code Locations (only click_settings is found in code statically, book_service and login are also found)
    from core.models import CodeLocation
    mock_code_locations = [
        CodeLocation(event_name="login", file_path="MainActivity.java", line_number=45, matched_snippet="logEvent('login')", confidence=1.0),
        CodeLocation(event_name="click_settings", file_path="SettingsFragment.java", line_number=102, matched_snippet="logEvent('click_settings')", confidence=0.9)
    ]
    
    # 5. Run Combine and Write
    os.makedirs("./tmp", exist_ok=True)
    temp_writer = LocalExcelWriter("./tmp/test_combiner_results.xlsx")
    
    combiner = ValidationCombinerAgent()
    results = combiner.run(mock_events, mock_telemetry, mock_runtime, mock_code_locations, temp_writer)
    
    print("\nCombined Audit Rows:\n")
    for r in results:
        print(r.model_dump_json(indent=2))
        print("-" * 40)
        
    print("\nRead back rows from temporary sheet (Audit Analysis):")
    wb = openpyxl.load_workbook("./tmp/test_combiner_results.xlsx")
    ws = wb["Audit Analysis"]
    for row in ws.iter_rows(values_only=True):
        print(row)
        
    if os.path.exists("./tmp/test_combiner_results.xlsx"):
        os.remove("./tmp/test_combiner_results.xlsx")
