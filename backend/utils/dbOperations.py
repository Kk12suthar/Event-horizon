from sqlalchemy import or_, and_, text
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from database import get_db
from fastapi import Depends
import uuid

def get_projects_by_user_id(
    user_id: str, db: Session = Depends(get_db), include: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all projects a user has access to via the mtd_access table.
    
    Args:
        user_id (str): The ID of the user
        db (Session): Database session
        include (Optional[str]): Additional related data to include (not used currently)
        
    Returns:
        List[Dict[str, Any]]: List of projects with their details, including users and folders
    """
    try:
        # Convert user_id to binary if it's a valid UUID
        try:
            user_uuid = uuid.UUID(user_id)
            user_id_binary = user_uuid.bytes
            user_id_str = str(user_uuid).upper()
        except (ValueError, AttributeError):
            # If not a valid UUID, assume it's already in binary format
            user_id_binary = user_id if isinstance(user_id, bytes) else user_id.encode()
            user_id_str = user_id.decode() if isinstance(user_id, bytes) else user_id
            
        # Query to get all projects the user has access to along with their access level
        query = text("""
        SELECT DISTINCT 
            p.id,
            p.name,
            p.description,
            p.created_at,
            p.created_by,
            p.status,
            u.name as created_by_name,
            a.level as user_access_level
        FROM mtd_project p
        JOIN mtd_users u ON p.created_by = u.id
        JOIN mtd_access a ON p.id = a.entity_id
        WHERE a.user_id = :user_id 
          AND a.entity_type = 'project'
          AND (a.expiration_date IS NULL OR a.expiration_date > NOW())
        ORDER BY p.created_at DESC
        """)
        
        result = db.execute(
            query,
            {"user_id": user_id_binary}
        ).fetchall()
        
        # Convert SQLAlchemy Row objects to dictionaries and process binary fields
        projects = []
        for row in result:
            # Convert row to dictionary using _asdict() if available (SQLAlchemy 1.4+)
            if hasattr(row, '_asdict'):
                project_dict = row._asdict()
            else:
                # Fallback for older SQLAlchemy versions
                project_dict = dict(zip(row.keys(), row))
            
            # Convert binary fields to hex strings
            project_id = None
            for key, value in project_dict.items():
                if isinstance(value, (bytes, bytearray)):
                    project_dict[key] = value.hex()
                    if key == 'id':
                        project_id = project_dict[key]
            
            # Get users with access to this project (if admin)
            if project_dict.get('user_access_level') == 'admin':
                users_query = text("""
                SELECT DISTINCT u.id, u.name, u.email, u.role, a.level as access_level
                FROM mtd_access a
                JOIN mtd_users u ON a.user_id = u.id
                WHERE a.entity_type = 'project' 
                AND a.entity_id = UNHEX(REPLACE(:project_id, '-', ''))
                """)
                users_result = db.execute(
                    users_query,
                    {"project_id": project_id}
                ).fetchall()
                
                users = []
                for user_row in users_result:
                    user_dict = user_row._asdict() if hasattr(user_row, '_asdict') else dict(zip(user_row.keys(), user_row))
                    for k, v in user_dict.items():
                        if isinstance(v, (bytes, bytearray)):
                            user_dict[k] = v.hex()
                    users.append(user_dict)
                
                project_dict['users'] = users
            
            # Get folders the user has access to in this project
            folders_query = text("""
            SELECT f.*, u.name as created_by_name, a.level as user_access_level
            FROM mtd_folder f
            JOIN mtd_users u ON f.created_by = u.id
            JOIN mtd_access a ON f.id = a.entity_id
            WHERE f.project_id = UNHEX(REPLACE(:project_id, '-', ''))
            AND a.user_id = UNHEX(REPLACE(:user_id, '-', ''))
            AND a.entity_type = 'folder'
            AND (a.expiration_date IS NULL OR a.expiration_date > NOW())
            ORDER BY f.created_at DESC
            """)
            
            folders_result = db.execute(
                folders_query,
                {"project_id": project_id, "user_id": user_id_str}
            ).fetchall()
            
            folders = []
            for folder_row in folders_result:
                folder_dict = folder_row._asdict() if hasattr(folder_row, '_asdict') else dict(zip(folder_row.keys(), folder_row))
                for k, v in folder_dict.items():
                    if isinstance(v, (bytes, bytearray)):
                        folder_dict[k] = v.hex()
                folders.append(folder_dict)
            
            project_dict['folders'] = folders
            projects.append(project_dict)
            
        return projects
        
    except Exception as e:
        # Log the error and re-raise
        print(f"Error in get_projects_by_user_id: {str(e)}")
        raise
