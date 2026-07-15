"""Pydantic request/response schemas for all routers.
These models improve FastAPI documentation and runtime validation.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Any, List
import uuid

# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    message: str = Field(..., description="Status or info message")
    data: Optional[Any] = Field(None, description="Returned data, if any")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    name: Optional[str] = Field(None, description="User name")
    email: Optional[str] = Field(None, description="User email")
    role: Optional[str] = Field(
        None, description="User role", pattern="^(ADMIN|ANALYST|VIEWER)$"
    )


class UserCreate(UserBase):
    id: str = Field(..., description="User GUID")
    name: str = Field(...)
    email: str = Field(...)
    role: str = Field(...)


class UserEdit(UserBase):
    id: str = Field(..., description="User GUID")


class UserDelete(BaseModel):
    id: str = Field(..., description="User GUID")


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    access_level: Optional[str] = None


# ---------------------------------------------------------------------------
# Folder
# ---------------------------------------------------------------------------


class FolderBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(ACTIVE|ARCHIVED|DELETED)$")
    entities: Optional[Any] = None


class FolderCreate(FolderBase):
    id: str
    name: str
    created_at: str
    created_by: str
    status: str
    project_id: str


class FolderEdit(FolderBase):
    id: str


class FolderDelete(BaseModel):
    id: str


class FolderOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: str
    created_by: str
    created_by_name: Optional[str] = None
    status: str
    project_id: str
    entities: Optional[Any] = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(ACTIVE|ARCHIVED|DELETED)$")
    layout_config: Optional[Any] = None


class DashboardCreate(DashboardBase):
    id: str
    name: str
    created_at: str
    created_by: str
    status: str
    parent_folder_id: str


class DashboardEdit(DashboardBase):
    id: str


class DashboardDelete(BaseModel):
    id: str


class DashboardOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: str
    created_by: str
    status: str
    parent_folder_id: str
    layout_config: Optional[Any]


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class ProjectBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(ACTIVE|ARCHIVED|DELETED)$")


class ProjectCreate(ProjectBase):
    id: str
    name: str
    created_at: str
    created_by: str
    status: str


class ProjectEdit(ProjectBase):
    id: str


class ProjectDelete(BaseModel):
    id: str


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: str
    created_by: str
    status: str
    created_by_name: Optional[str] = None
    user_access_level: Optional[str] = None
    folders: Optional[Any] = None
    users: Optional[Any] = None


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------


class FileBase(BaseModel):
    name: Optional[str] = None
    originalName: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(UPLOADED|PROCESSED|FAILED)$")


class FileCreate(FileBase):
    id: str
    name: str
    created_at: str
    uploaded_by: str
    status: str
    parent_folder_id: str
    size_bytes: int = Field(..., gt=0)


class FileEdit(FileBase):
    id: str


class FileDelete(BaseModel):
    id: str


class FileOut(BaseModel):
    id: str
    name: str
    created_at: str
    uploaded_by: str
    status: str
    parent_folder_id: str
    originalName: Optional[str] = None
    size_bytes: int = 0


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class SessionBase(BaseModel):
    status: Optional[str] = Field(
        None, description="Session status", pattern="^(ACTIVE|ARCHIVED|DELETED)$"
    )
    app_name: Optional[str] = Field(
        None, description="Name of application that created the session"
    )
    folder_id: Optional[str] = Field(None, description="Parent folder GUID")
    entities: Optional[Any] = Field(
        None, description="Optional JSON blob of mined entities"
    )


class SessionCreate(SessionBase):
    id: str = Field(..., description="Session GUID")
    created_at: str = Field(..., description="ISO date-time when session was created")
    created_by: str = Field(..., description="User GUID who created the session")
    status: str = Field(...)
    folder_id: str = Field(...)
    app_name: str = Field(...)


class SessionEdit(SessionBase):
    id: str = Field(..., description="Session GUID")


class SessionDelete(BaseModel):
    id: str = Field(..., description="Session GUID")


class SessionOut(BaseModel):
    id: str
    created_at: str
    created_by: str
    status: str
    folder_id: str
    app_name: str
    entities: Optional[Any] = None


class SessionWorkspaceSelection(BaseModel):
    session_id: str = Field(..., description="Active session UUID")
    folder_id: str = Field(..., description="Folder UUID that owns the session")
    table_id: str = Field(..., description="Stable ID of an agent-created prepared table")


class SessionArtifactUpsert(BaseModel):
    session_id: str = Field(..., description="Active session UUID")
    folder_id: str = Field(..., description="Folder UUID that owns the session")
    artifact: dict[str, Any] = Field(..., description="Typed chart, report, or report-draft artifact")


class SessionArtifactDelete(BaseModel):
    session_id: str = Field(..., description="Active session UUID")
    folder_id: str = Field(..., description="Folder UUID that owns the session")
    artifact_id: str = Field(..., description="Artifact UUID")


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


class TableBase(BaseModel):
    id: str = Field(..., description="Table GUID")
    name: str = Field(..., description="Table name")
    created_at: str = Field(..., description="ISO date-time when table was created")
    created_by: str = Field(..., description="User GUID who created the table")
    status: str = Field(..., description="Table status")
    parent_id: str = Field(..., description="Parent folder GUID")
    type: str = Field(..., description="Table type")


class TableCreate(TableBase):
    id: str = Field(..., description="Table GUID")
    created_at: str = Field(..., description="ISO date-time when table was created")
    created_by: str = Field(..., description="User GUID who created the table")
    status: str = Field(..., description="Table status")
    parent_id: str = Field(..., description="Parent folder GUID")
    type: str = Field(..., description="Table type")


class TableEdit(BaseModel):
    id: str = Field(..., description="Table GUID")
    name: str = Field(..., description="Table name")
    status: str = Field(..., description="Table status")


class TableDelete(BaseModel):
    id: str = Field(..., description="Table GUID")


class TableOut(BaseModel):
    id: str = Field(..., description="Table GUID")
    name: str = Field(..., description="Table name")
    created_at: str = Field(..., description="ISO date-time when table was created")
    created_by: str = Field(..., description="User GUID who created the table")
    status: str = Field(..., description="Table status")
    parent_id: str = Field(..., description="Parent folder GUID")
    type: str = Field(..., description="Table type")


# ---------------------------------------------------------------------------
# User Invitations
# ---------------------------------------------------------------------------


class InvitationCreate(BaseModel):
    email: str = Field(..., description="Email address to invite")
    role: str = Field(default="VIEWER", description="User role", pattern="^(ADMIN|ANALYST|VIEWER)$")
    invited_by: str = Field(..., description="User ID of the inviter (UUID or Firebase UID)")

    @validator('invited_by')
    def validate_user_id(cls, v):
        # Accept either UUID or Firebase UID format
        try:
            uuid.UUID(v)  # Try standard UUID format first
            return v
        except ValueError:
            if len(v) in (22, 28):  # Firebase UID length
                return v
            raise ValueError('must be a valid UUID or Firebase UID')


class InvitationVerify(BaseModel):
    token: str = Field(..., description="Invitation token")


class InvitationAccept(BaseModel):
    token: str = Field(..., description="Invitation token")
    username: str = Field(..., description="User's full name")
    password: str = Field(..., description="User password", min_length=6)


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    invited_by: str
    invite_token: str
    status: str
    created_at: str
    expires_at: str
    accepted_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Backup History
# ---------------------------------------------------------------------------


class BackupSaveRequest(BaseModel):
    """Request schema for saving a backup entry (called by unified_snapshot_monitor)"""
    table_id: str = Field(..., description="Table UUID")
    table_name: Optional[str] = Field(None, description="Table name (actual table_id in DB)")
    backup_type: str = Field(
        ...,
        description="Backup type",
        pattern="^(ORIGINAL|INCREMENTAL|CHANGE|PERIODIC)$"
    )
    backup_file_path: str = Field(..., description="Full path to the .sql file")
    backup_file_name: str = Field(..., description="Backup filename")
    wal_lsn: Optional[str] = Field(None, description="PostgreSQL WAL LSN")
    shadow_table_name: Optional[str] = Field(None, description="Shadow table name for incremental backups")
    change_count: Optional[int] = Field(None, description="Number of changes in incremental backup")
    file_size_bytes: Optional[int] = Field(None, description="Backup file size in bytes")
    notes: Optional[str] = Field(None, description="Additional notes")
    status: Optional[str] = Field("created", description="Backup status")


class BackupViewRequest(BaseModel):
    """Request schema for viewing a backup entry by table_id and timestamp"""
    table_id: str = Field(..., description="Table UUID")
    created_at: str = Field(..., description="Backup creation timestamp (ISO format)")


class BackupRemoveRequest(BaseModel):
    """Request schema for removing a backup entry"""
    table_id: str = Field(..., description="Table UUID")
    created_at: str = Field(..., description="Backup creation timestamp (ISO format)")
    deleted_reason: Optional[str] = Field(None, description="Reason for deletion")


class BackupMatchCheckpointRequest(BaseModel):
    """Request schema for matching a backup to a message/invocation checkpoint"""
    table_id: str = Field(..., description="Table UUID")
    timestamp: str = Field(..., description="Target timestamp (ISO format)")
    invocation_id: str = Field(..., description="Invocation identifier")
    session_id: str = Field(..., description="Session UUID")
    folder_id: str = Field(..., description="Folder UUID")


class BackupRestoreCheckpointRequest(BaseModel):
    """Request schema for restoring a backup checkpoint by invocation_id"""
    invocation_id: str = Field(..., description="Invocation identifier to restore")
    session_id: str = Field(..., description="Session UUID")
    folder_id: str = Field(..., description="Folder UUID")


class BackupHistoryOut(BaseModel):
    """Response schema for backup history entries"""
    backup_id: int
    table_id: str
    table_name: Optional[str]
    backup_type: str
    backup_file_path: str
    backup_file_name: str
    created_at: str
    status: str
    wal_lsn: Optional[str] = None
    shadow_table_name: Optional[str] = None
    change_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    invocation_id: Optional[str] = None
    session_id: Optional[str] = None
    folder_id: Optional[str] = None
    deleted_at: Optional[str] = None
    deleted_reason: Optional[str] = None
