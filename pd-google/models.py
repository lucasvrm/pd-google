from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base

class DriveFolder(Base):
    __tablename__ = "google_drive_folders"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(String, index=True)
    entity_type = Column(String, index=True) # client, lead, deal, pf, pj
    folder_id = Column(String, unique=True, index=True) # ID in Google Drive (Mocked)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DriveFile(Base):
    __tablename__ = "drive_files"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String, unique=True, index=True) # ID in Google Drive (Mocked)
    parent_folder_id = Column(String, index=True) # Folder ID in Drive
    name = Column(String)
    mime_type = Column(String)
    size = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
