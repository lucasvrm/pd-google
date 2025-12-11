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
    entity_type = Column(String, index=True)  # company, lead, deal, contact
    folder_id = Column(String, unique=True, index=True)  # ID in Google Drive (Mocked)

    # URL amigável da pasta no Drive
    folder_url = Column(String)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Soft delete fields
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(String, nullable=True)  # user_id who deleted
    delete_reason = Column(String, nullable=True)


class DriveFile(Base):
    __tablename__ = "drive_files"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String, unique=True, index=True)  # ID in Google Drive (Mocked)
    parent_folder_id = Column(String, index=True)  # Folder ID in Drive
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
    entity_type = Column(String, index=True)  # company, lead, deal, etc.
    active = Column(Boolean, default=True)

    nodes = relationship("DriveStructureNode", back_populates="template")


class DriveStructureNode(Base):
    __tablename__ = "drive_structure_nodes"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("drive_structure_templates.id"))
    parent_id = Column(Integer, ForeignKey("drive_structure_nodes.id"), nullable=True)
    name = Column(String)  # Folder name, can contain placeholders like {{year}}
    order = Column(Integer, default=0)

    template = relationship("DriveStructureTemplate", back_populates="nodes")


# Roles & Permissions (Simplified for MVP)
class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # ID from Supabase Auth
    role = Column(String)  # admin, manager, sales


# --- SUPABASE INTEGRATION MODELS ---
# These models map to existing tables in the main application database (Supabase)
# We define them here to allow SQLAlchemy to query them for names and relationships.


class Company(Base):
    __tablename__ = "companies"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String)  # Razão Social or Name


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String, nullable=True)


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)


class LeadStatus(Base):
    """
    Mapeia a tabela public.lead_statuses criada nas migrations do Supabase:

    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text UNIQUE NOT NULL,
    label       text NOT NULL,
    description text,
    is_active   boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
    """
    __tablename__ = "lead_statuses"

    id = Column(String, primary_key=True)
    code = Column(String, nullable=False)
    label = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LeadOrigin(Base):
    """
    Mapeia a tabela public.lead_origins criada nas migrations do Supabase:

    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text UNIQUE NOT NULL,
    label       text NOT NULL,
    description text,
    is_active   boolean NOT NULL DEFAULT true,
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
    """
    __tablename__ = "lead_origins"

    id = Column(String, primary_key=True)
    code = Column(String, nullable=False)
    label = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True)  # UUID
    # Map 'title' attribute to 'legal_name' column
    title = Column("legal_name", String)
    trade_name = Column(String, nullable=True)
    lead_status_id = Column(String, ForeignKey("lead_statuses.id"), nullable=True)
    lead_origin_id = Column(String, ForeignKey("lead_origins.id"), nullable=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    qualified_company_id = Column(String, ForeignKey("companies.id"), nullable=True)
    qualified_master_deal_id = Column(String, ForeignKey("master_deals.id"), nullable=True)
    address_city = Column(String, nullable=True)
    address_state = Column(String, nullable=True)
    last_interaction_at = Column(DateTime(timezone=True), nullable=True, index=True)
    priority_score = Column(Integer, default=0, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    owner = relationship("User", foreign_keys=[owner_user_id])
    lead_status = relationship("LeadStatus", foreign_keys=[lead_status_id])
    lead_origin = relationship("LeadOrigin", foreign_keys=[lead_origin_id])
    qualified_master_deal = relationship("Deal", foreign_keys=[qualified_master_deal_id])
    activity_stats = relationship("LeadActivityStats", back_populates="lead", uselist=False)
    tags = relationship("Tag", secondary="lead_tags", back_populates="leads")

    @property
    def legal_name(self):
        return self.title


class Tag(Base):
    __tablename__ = "tags"

    id = Column(String, primary_key=True, index=True)  # UUID
    name = Column(String, unique=True)
    color = Column(String, nullable=True)

    leads = relationship("Lead", secondary="lead_tags", back_populates="tags")


class LeadTag(Base):
    __tablename__ = "lead_tags"

    lead_id = Column(String, ForeignKey("leads.id"), primary_key=True)
    tag_id = Column(String, ForeignKey("tags.id"), primary_key=True)


class LeadActivityStats(Base):
    __tablename__ = "lead_activity_stats"

    lead_id = Column(String, ForeignKey("leads.id"), primary_key=True)
    engagement_score = Column(Integer, default=0)
    last_interaction_at = Column(DateTime(timezone=True), nullable=True)
    last_email_at = Column(DateTime(timezone=True), nullable=True)
    last_event_at = Column(DateTime(timezone=True), nullable=True)
    total_emails = Column(Integer, default=0)
    total_events = Column(Integer, default=0)
    total_interactions = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lead = relationship("Lead", back_populates="activity_stats")


class Deal(Base):
    __tablename__ = "master_deals"

    id = Column(String, primary_key=True)  # UUID
    # Map 'title' attribute to 'client_name' column
    title = Column("client_name", String)

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

    attendees = Column(Text)  # Storing as JSON string for maximum compatibility

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
