import io
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from core.logger import get_logger

logger = get_logger(__name__)

class DriveClient:
    """
    DriveClient interacts with Google Drive using the provided credentials
    to download files (like the target APK) from Google Drive.
    """
    def __init__(self, credentials):
        self.credentials = credentials
        self.service = build('drive', 'v3', credentials=credentials)

    def download_file(self, file_id: str, dest_path: str) -> str:
        """
        Downloads a Google Drive file to the local filesystem path.
        
        Args:
            file_id: The ID of the file in Google Drive.
            dest_path: The local path to save the downloaded file.
            
        Returns:
            The local file path where the file was saved.
        """
        logger.info(f"Downloading Google Drive file '{file_id}' to '{dest_path}'")
        
        # Ensure destination parent directory exists
        dest_dir = os.path.dirname(os.path.abspath(dest_path))
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
            
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logger.info(f"Download progress: {int(status.progress() * 100)}%")
                
            with open(dest_path, 'wb') as f:
                f.write(fh.getvalue())
                
            logger.info(f"Download complete: '{dest_path}'")
            return dest_path
        except Exception as e:
            logger.error(f"Failed to download file '{file_id}': {e}")
            raise
