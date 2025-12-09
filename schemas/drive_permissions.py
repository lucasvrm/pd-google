from typing import Literal, Optional
from pydantic import BaseModel, EmailStr


class DrivePermission(BaseModel):
    id: Optional[str]
    role: Literal["owner", "organizer", "fileOrganizer", "writer", "reader"]
    type: Literal["user", "group", "domain", "anyone"]
    emailAddress: Optional[EmailStr] = None


class DrivePermissionCreate(BaseModel):
    email: EmailStr
    role: Literal["writer", "reader", "commenter", "fileOrganizer", "organizer"]
    type: Literal["user", "group", "domain", "anyone"] = "user"


class DrivePermissionUpdate(BaseModel):
    role: Literal["writer", "reader", "commenter", "fileOrganizer", "organizer"]


class MoveDriveItemRequest(BaseModel):
    destination_parent_id: str
