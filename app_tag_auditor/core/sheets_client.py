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
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        headers = {"Authorization": f"Bearer {self.credentials.token}"}
        
        response = requests.get(export_url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to export spreadsheet {sheet_id}: {response.text}")
            
        return response.content

    @staticmethod
    def extract_sheet_id_from_url(url: str) -> str:
        """
        Extracts spreadsheet ID from a Google Sheets URL or returns the input if it's already an ID.
        """
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        return url
