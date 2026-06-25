import os
import re
import requests
from googleapiclient.discovery import build
from core.logger import get_logger

logger = get_logger(__name__)

class SheetsClient:
    """
    SheetsClient interacts with Google Sheets using the provided credentials
    to read event sheets, write/append validation results, and export files.
    """
    def __init__(self, credentials):
        self.credentials = credentials
        self.service = build('sheets', 'v4', credentials=credentials)

    def ensure_headers(self, sheet_id: str, tab_name: str, headers: list[str]) -> None:
        """
        Ensures that a specific tab exists and has the specified headers in the first row.
        """
        logger.info(f"Ensuring headers in sheet: {sheet_id}, tab: {tab_name}, headers: {headers}")
        
        try:
            # Check existing tabs
            spreadsheet = self.service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            sheets = [s['properties']['title'] for s in spreadsheet.get('sheets', [])]
        except Exception as e:
            logger.error(f"Failed to fetch spreadsheet metadata: {e}")
            raise

        if tab_name not in sheets:
            # Create the tab if it doesn't exist
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': tab_name
                        }
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
            logger.info(f"Created tab '{tab_name}'")

        # Read first row
        range_name = f"'{tab_name}'!1:1"
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            rows = result.get('values', [])
        except Exception as e:
            logger.error(f"Failed to retrieve values from sheet: {e}")
            rows = []

        if not rows or rows[0] != headers:
            # Write headers in the first row
            body = {
                'values': [headers]
            }
            self.service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            logger.info(f"Set headers on tab '{tab_name}' to: {headers}")

    def append_row(self, sheet_id: str, tab_name: str, row: dict) -> None:
        """
        Appends a row to the specified tab. The row dictionary keys are matched
        against the header columns in the sheet to build the row list.
        """
        logger.info(f"Appending row to sheet: {sheet_id}, tab: {tab_name}")
        
        # Read the headers first to maintain column order
        range_name = f"'{tab_name}'!1:1"
        result = self.service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        if not values or not values[0]:
            raise ValueError(f"No headers found in tab '{tab_name}'. Run ensure_headers first.")
            
        headers = values[0]
        row_values = [row.get(h, '') for h in headers]
        
        body = {
            'values': [row_values]
        }
        self.service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A:A",
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        logger.info("Successfully appended row")

    def read_sheet(self, sheet_id: str, tab_name: str) -> list[dict]:
        """
        Reads all values from the specified tab and returns them as a list of dicts.
        """
        logger.info(f"Reading sheet: {sheet_id}, tab: {tab_name}")
        range_name = f"'{tab_name}'!A:ZZ"
        
        result = self.service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=range_name
        ).execute()
        
        rows = result.get('values', [])
        if not rows:
            return []
            
        headers = rows[0]
        data = []
        for row in rows[1:]:
            # Pad row values if it's shorter than headers
            padded_row = row + [''] * (len(headers) - len(row))
            data.append(dict(zip(headers, padded_row)))
            
        return data

    def export_as_excel(self, sheet_id: str) -> bytes:
        """
        Exports the entire spreadsheet as Excel (.xlsx) file bytes.
        """
        logger.info(f"Exporting spreadsheet: {sheet_id} as Excel")
        token = getattr(self.credentials, 'token', None)
        if not token:
            raise ValueError("Credentials do not contain a valid OAuth token.")

        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. Try Drive v3 Export API
        export_url = f"https://www.googleapis.com/drive/v3/files/{sheet_id}/export?mimeType=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        try:
            response = requests.get(export_url, headers=headers)
            if response.status_code == 200:
                logger.info("Successfully exported spreadsheet via Drive API v3")
                return response.content
            else:
                logger.warning(f"Drive API v3 export returned status code {response.status_code}: {response.text}")
        except Exception as e:
            logger.warning(f"Error calling Drive API v3 export: {e}")

        # 2. Fallback to direct export link
        logger.info("Attempting direct spreadsheet export fallback link")
        fallback_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        response = requests.get(fallback_url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to export spreadsheet {sheet_id} using both APIs: HTTP {response.status_code} - {response.text}")
            
        return response.content

    def download_sheet_as_excel(self, sheet_id: str, dest_path: str) -> str:
        """
        Downloads a Google Sheet as an Excel (.xlsx) file to the local filesystem path.
        """
        logger.info(f"Downloading Google Sheet '{sheet_id}' to '{dest_path}'")
        excel_bytes = self.export_as_excel(sheet_id)
        
        dest_dir = os.path.dirname(os.path.abspath(dest_path))
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
            
        with open(dest_path, 'wb') as f:
            f.write(excel_bytes)
            
        logger.info(f"Excel export saved: '{dest_path}'")
        return dest_path

    @staticmethod
    def extract_sheet_id_from_url(url: str) -> str:
        """
        Extracts spreadsheet ID from a Google Sheets URL or returns the input if it's already an ID.
        """
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        return url

