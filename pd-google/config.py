import os

class Config:
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    USE_MOCK_DRIVE = os.getenv("USE_MOCK_DRIVE", "false").lower() == "true"
    DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", None) # Optional: if we want to jail everything in a folder

config = Config()
