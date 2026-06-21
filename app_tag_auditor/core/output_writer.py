import os
from abc import ABC, abstractmethod
import openpyxl
from core.config import get_settings

class OutputWriter(ABC):
    """
    Abstract base class for writing audit validation outputs.
    Can be implemented for local Excel, Google Sheets, or databases.
    """
    @abstractmethod
    def ensure_headers(self, tab_name: str, headers: list[str]) -> None:
        """
        Ensures a worksheet/tab exists and contains the specified header list in row 1.
        """
        pass

    @abstractmethod
    def append_row(self, tab_name: str, row: dict) -> None:
        """
        Appends a dictionary row to the tab, mapping keys to headers.
        Raises ValueError if the row dict contains keys not defined in the headers.
        """
        pass

    @abstractmethod
    def read_all(self, tab_name: str) -> list[dict]:
        """
        Reads all rows from the specified tab and returns them as a list of dicts.
        """
        pass

    @abstractmethod
    def export_as_excel(self) -> bytes:
        """
        Exports the entire output repository as raw Excel (.xlsx) bytes.
        """
        pass


class LocalExcelWriter(OutputWriter):
    """
    Concrete implementation of OutputWriter that writes to a local Excel (.xlsx) file.
    """
    def __init__(self, file_path: str = None):
        if file_path is None:
            settings = get_settings()
            self.file_path = settings.LOCAL_OUTPUT_PATH
        else:
            self.file_path = file_path
            
        # Auto-create the parent directory of LOCAL_OUTPUT_PATH if it doesn't exist
        parent_dir = os.path.dirname(os.path.abspath(self.file_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    def _load_workbook(self) -> tuple[openpyxl.Workbook, bool]:
        if os.path.exists(self.file_path):
            try:
                wb = openpyxl.load_workbook(self.file_path)
                return wb, False
            except Exception:
                # If file exists but is corrupted/empty, treat as new
                wb = openpyxl.Workbook()
                return wb, True
        else:
            wb = openpyxl.Workbook()
            return wb, True

    def ensure_headers(self, tab_name: str, headers: list[str]) -> None:
        wb, is_new = self._load_workbook()
        
        if tab_name in wb.sheetnames:
            ws = wb[tab_name]
        else:
            if is_new and "Sheet" in wb.sheetnames and len(wb.sheetnames) == 1:
                ws = wb["Sheet"]
                ws.title = tab_name
            else:
                ws = wb.create_sheet(title=tab_name)
                
        # Read the first row to check for existing headers
        first_row = [cell.value for cell in ws[1] if cell.value is not None]
        
        if not first_row:
            for col_idx, header in enumerate(headers, 1):
                ws.cell(row=1, column=col_idx, value=header)
            wb.save(self.file_path)

    def append_row(self, tab_name: str, row: dict) -> None:
        wb, _ = self._load_workbook()
        if tab_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{tab_name}' does not exist. Call ensure_headers first.")
            
        ws = wb[tab_name]
        
        # Read headers from the first row
        headers = [cell.value for cell in ws[1] if cell.value is not None]
        if not headers:
            raise ValueError(f"No headers found in tab '{tab_name}'. Call ensure_headers first.")
            
        # Validate that all row keys exist in the headers
        for key in row.keys():
            if key not in headers:
                raise ValueError(f"Key '{key}' is not in the defined headers {headers} for tab '{tab_name}'.")
                
        # Construct the row aligned with the header order
        row_values = [row.get(h, None) for h in headers]
        ws.append(row_values)
        wb.save(self.file_path)

    def read_all(self, tab_name: str) -> list[dict]:
        if not os.path.exists(self.file_path):
            return []
            
        wb = openpyxl.load_workbook(self.file_path)
        if tab_name not in wb.sheetnames:
            return []
            
        ws = wb[tab_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
            
        headers = rows[0]
        # Filter out trailing None headers if any
        headers = [h for h in headers if h is not None]
        
        result = []
        for row in rows[1:]:
            if all(val is None for val in row):
                continue
            row_dict = {}
            for idx, h in enumerate(headers):
                val = row[idx] if idx < len(row) else None
                row_dict[h] = val
            result.append(row_dict)
            
        return result

    def export_as_excel(self) -> bytes:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"No Excel file found at '{self.file_path}' to export.")
        with open(self.file_path, 'rb') as f:
            return f.read()

if __name__ == "__main__":
    # Small test/demo block to verify LocalExcelWriter functionality
    print("Testing LocalExcelWriter...")
    test_file = "./output/test_audit_results.xlsx"
    
    # Cleanup previous test file if exists
    if os.path.exists(test_file):
        os.remove(test_file)
        
    writer = LocalExcelWriter(test_file)
    headers = ["event_name", "status", "timestamp"]
    tab = "TestTab"
    
    # Ensure headers
    writer.ensure_headers(tab, headers)
    print(f"Headers verified for tab '{tab}'")
    
    # Append rows
    row1 = {"event_name": "app_open", "status": "PASS", "timestamp": "2026-06-21T10:00:00"}
    row2 = {"event_name": "click_button", "status": "FAIL", "timestamp": "2026-06-21T10:01:00"}
    
    writer.append_row(tab, row1)
    writer.append_row(tab, row2)
    print("Test rows appended.")
    
    # Try appending invalid row (should raise ValueError)
    try:
        invalid_row = {"event_name": "login", "invalid_field": "error"}
        writer.append_row(tab, invalid_row)
    except ValueError as e:
        print(f"Expected validation error caught: {e}")
        
    # Read back rows
    data = writer.read_all(tab)
    print("Read back rows:")
    for row in data:
        print(row)
        
    # Export bytes
    content = writer.export_as_excel()
    print(f"Exported Excel bytes size: {len(content)} bytes")
    
    # Clean up test file
    if os.path.exists(test_file):
        os.remove(test_file)
        print("Cleanup done.")
