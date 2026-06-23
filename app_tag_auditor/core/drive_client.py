import os
import requests
from core.logger import get_logger

logger = get_logger(__name__)

class DriveClient:
    """
    DriveClient interacts with Google Drive using the provided credentials
    to download files (like the target APK) from Google Drive.
    """
    def __init__(self, credentials):
        self.credentials = credentials
        try:
            from googleapiclient.discovery import build
            self.service = build('drive', 'v3', credentials=credentials)
        except Exception as e:
            logger.warning(f"Could not build Google Drive service client: {e}")
            self.service = None

    def download_file(self, file_id: str, dest_path: str) -> str:
        """
        Downloads a Google Drive file to the local filesystem path.
        
        Args:
            file_id: The ID of the file in Google Drive.
            dest_path: The local path to save the downloaded file.
            
        Returns:
            The local file path where the file was saved.
        """
        logger.info(f"Downloading Google Drive file '{file_id}' to '{dest_path}' via direct HTTP")
        
        # Ensure destination parent directory exists
        dest_dir = os.path.dirname(os.path.abspath(dest_path))
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
            
        try:
            token = getattr(self.credentials, 'token', None)
            if not token:
                raise ValueError("Credentials do not contain a valid OAuth token.")
                
            download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
            headers = {"Authorization": f"Bearer {token}"}
            
            with requests.get(download_url, headers=headers, stream=True) as response:
                if response.status_code != 200:
                    raise Exception(f"Failed to download file {file_id}: HTTP {response.status_code} - {response.text}")
                
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024): # 1MB chunks
                        if chunk:
                            f.write(chunk)
                            
            logger.info(f"Download complete: '{dest_path}'")
            return dest_path
        except Exception as e:
            logger.error(f"Failed to download file '{file_id}': {e}")
            raise

    def list_files(self, q: str = None) -> list:
        """
        Lists files from Google Drive matching the query.
        
        Args:
            q: The search query string for Google Drive (e.g., mimeType = 'application/vnd.android.package-archive').
            
        Returns:
            A list of dicts, each containing 'id', 'name', 'mimeType', etc.
        """
        try:
            token = getattr(self.credentials, 'token', None)
            if not token:
                raise ValueError("Credentials do not contain a valid OAuth token.")
                
            headers = {"Authorization": f"Bearer {token}"}
            url = "https://www.googleapis.com/drive/v3/files"
            params = {
                "pageSize": 50,
                "fields": "nextPageToken, files(id, name, mimeType, iconLink, thumbnailLink)",
                "orderBy": "name,modifiedTime desc"
            }
            if q:
                params["q"] = q
                
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.json().get("files", [])
            else:
                logger.error(f"Failed to list files: HTTP {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []


