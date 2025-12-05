from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class DriveFolder(Base):
    __tablename__ = "google_drive_folders"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(String, index=True)
    entity_type = Column(String, index=True) # company, lead, deal, contact
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
