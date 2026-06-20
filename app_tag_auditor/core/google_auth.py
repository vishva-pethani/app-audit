from google.oauth2.credentials import Credentials

def credentials_from_access_token(access_token: str) -> Credentials:
    """
    Wraps a raw browser-obtained OAuth access token into a google.oauth2.credentials.Credentials object
    usable by Google Drive and Sheets API clients.
    
    This access token is obtained client-side via Google Identity Services in the frontend
    with scopes `https://www.googleapis.com/auth/drive.readonly` and 
    `https://www.googleapis.com/auth/spreadsheets`. It is then passed down to this backend module. 
    This module never performs its own OAuth flow or token refreshes.
    
    Args:
        access_token: The OAuth access token string retrieved client-side.
        
    Returns:
        A Credentials object configured with the provided access token.
    """
    return Credentials(token=access_token)
