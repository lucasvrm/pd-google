from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class DriveWebhookChannel(Base):
    """
    Stores Google Drive webhook notification channels.
    These channels are registered with Google Drive to receive real-time notifications
    about changes to files and folders.
    """
    __tablename__ = "drive_webhook_channels"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, unique=True, index=True)  # Unique channel identifier
    resource_id = Column(String, index=True)  # Resource ID returned by Google
    resource_type = Column(String, default="folder")  # "folder" or "file"
    watched_resource_id = Column(String, index=True)  # ID of the Drive folder/file being watched
    expires_at = Column(DateTime(timezone=True))  # Channel expiration timestamp
    active = Column(Boolean, default=True, index=True)  # Whether channel is active
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DriveFolder(Base):
    __tablename__ = "google_drive_folders"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(String, index=True)
    entity_type = Column(String, index=True) # company, lead, deal, contact
    folder_id = Column(String, unique=True, index=True) # ID in Google Drive (Mocked)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Soft delete fields
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String, nullable=True)  # user_id who deleted
    delete_reason = Column(String, nullable=True)


class DriveFile(Base):
    __tablename__ = "drive_files"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String, unique=True, index=True) # ID in Google Drive (Mocked)
    parent_folder_id = Column(String, index=True) # Folder ID in Drive
    name = Column(String)
    mime_type = Column(String)
    size = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Soft delete fields
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String, nullable=True)  # user_id who deleted
    delete_reason = Column(String, nullable=True)

# Template Structures
class DriveStructureTemplate(Base):
    __tablename__ = "drive_structure_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    entity_type = Column(String, index=True) # company, lead, deal, etc.
    active = Column(Boolean, default=True)

    nodes = relationship("DriveStructureNode", back_populates="template")

class DriveStructureNode(Base):
    __tablename__ = "drive_structure_nodes"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("drive_structure_templates.id"))
    parent_id = Column(Integer, ForeignKey("drive_structure_nodes.id"), nullable=True)
    name = Column(String) # Folder name, can contain placeholders like {{year}}
    order = Column(Integer, default=0)

    template = relationship("DriveStructureTemplate", back_populates="nodes")
    # Simplification: For now just one level deep for MVP, or fix self-referential
    # We will omit 'children' explicit prop for now to fix the seeding error quickly.

# Roles & Permissions (Simplified for MVP)
class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True) # ID from Supabase Auth
    role = Column(String) # admin, manager, sales

# --- SUPABASE INTEGRATION MODELS ---
# These models map to existing tables in the main application database (Supabase)
# We define them here to allow SQLAlchemy to query them for names and relationships.

class Company(Base):
    __tablename__ = "companies"

    id = Column(String, primary_key=True) # UUID
    name = Column(String) # Razão Social or Name
    fantasy_name = Column(String, nullable=True) # Nome Fantasia
    # Add other fields if necessary, but we only need names for folder naming

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True) # UUID
    title = Column(String) # Lead name/title
    company_id = Column(String, ForeignKey("companies.id"), nullable=True)

    # Relationship (optional, but helpful)
    company = relationship("Company")

class Deal(Base):
    __tablename__ = "deals"

    id = Column(String, primary_key=True) # UUID
    title = Column(String) # Deal name/title
    company_id = Column(String, ForeignKey("companies.id"), nullable=True)

    # Relationship
    company = relationship("Company")


class DriveChangeLog(Base):
    """
    Audit log for Drive changes received via webhooks.
    Records all change notifications received from Google Drive.
    """
    __tablename__ = "drive_change_logs"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, index=True)  # Channel that received the notification
    resource_id = Column(String, index=True)  # Resource ID from Google
    resource_state = Column(String)  # "sync", "add", "remove", "update", "trash", "untrash", "change"
    changed_resource_id = Column(String, index=True, nullable=True)  # Drive file/folder ID that changed
    event_type = Column(String, nullable=True)  # Additional event information
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    raw_headers = Column(Text, nullable=True)  # JSON string of all webhook headers for debugging


class CalendarSyncState(Base):
    """
    Stores sync tokens for Google Calendar channels.
    Used to perform incremental syncs (fetching only what changed).
    """
    __tablename__ = "calendar_sync_states"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(String)  # Resource ID returned by Google
    channel_id = Column(String, unique=True, index=True)  # Our UUID for the webhook channel
    calendar_id = Column(String, default='primary')  # ID of the monitored calendar
    sync_token = Column(String)  # Token for fetching next changes
    expiration = Column(DateTime(timezone=True))  # Channel expiration
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CalendarEvent(Base):
    """
    Local mirror of Google Calendar events.
    """
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    google_event_id = Column(String, unique=True, index=True, nullable=False)
    calendar_id = Column(String, default='primary')

    # Main Data
    summary = Column(String)
    description = Column(Text)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))

    # Important Links
    meet_link = Column(String)
    html_link = Column(String)

    # Metadata
    status = Column(String)  # confirmed, tentative, cancelled
    organizer_email = Column(String)

    # Attendees (stored as JSON for simplicity in MVP)
    # Using String/Text for SQLite compatibility if needed, but JSON type for PG is better
    # For compatibility with both, we use JSON from sqlalchemy.dialects.postgresql if available,
    # but since this project supports SQLite dev, we might use a generic JSON type or Text.
    # Given the requirements.txt has psycopg2, we can assume PG is target, but let's be safe.
    # We will import JSON from sqlalchemy.types which works on recent SQLAlchemy versions for both.
    attendees = Column(Text) # Storing as JSON string for maximum compatibility

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
