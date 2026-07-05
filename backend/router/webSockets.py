from fastapi import Depends, APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
import json
import uuid
import os
from env import load_environment
import requests
from fastapi import HTTPException
from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from utils.logConfig import logger
from utils.file_uploader import FileUploader, DatabaseConfig
from pathlib import Path
from .tables import (
    create_table,
    get_table,
    get_tables_by_parent_id,
    edit_table,
    delete_table,
    parse_iso_datetime,
)
from schemas import TableCreate, TableEdit, TableDelete, TableOut, MessageResponse
from datetime import datetime

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
load_environment()






def process_file_sync(file_uploader, file_info):
    """
    Synchronous helper to process a single file.
    Runs in a thread pool to avoid blocking the asyncio event loop.
    """
    result = {
        "success": False,
        "table_created": False,
    }
    
    try:
        # Connect to database first
        if file_uploader.connect_to_database():
            # Validate the file
            if file_uploader.validate_file(str(file_info["file_path"])):
                # Read the file into a DataFrame
                df = file_uploader.read_file(str(file_info["file_path"]))
                if df is not None:
                    # Log the actual number of rows in the DataFrame to verify
                    print(f"DataFrame contains {len(df)} rows before table creation")
                    # Create the table
                    table_created = file_uploader.create_table(
                        file_info["table_id"], df
                    )
                    # Insert data if table was created successfully
                    if table_created:
                        # Use the same DataFrame instance to prevent any duplication
                        data_inserted = file_uploader.insert_data(
                            file_info["table_id"], df
                        )
                        result["table_created"] = table_created and data_inserted
                        
                        # Trigger the monitor BEFORE disconnecting
                        if result["table_created"]:
                            file_uploader._trigger_monitor(file_info["table_id"])
                            result["success"] = True
            
            # Disconnect from database
            file_uploader.disconnect_from_database()
        else:
             print(f"Failed to connect to database for {file_info['table_name']}")
             
    except Exception as e:
        print(f"Error processing {file_info['table_name']} inside thread: {str(e)}")
        # Ensure we disconnect on error
        try:
            file_uploader.disconnect_from_database()
        except:
            pass
            
    return result


def create_session_id():
    return str(str(uuid.uuid4()).replace("-", ""))


router = APIRouter(prefix="/api/v1/webSockets", tags=["webSockets"])


# WebSocket endpoint for file uploads
@router.websocket("/file-upload")
async def websocket_file_upload(websocket: WebSocket):
    """
    WebSocket endpoint for handling file uploads and table creation.
    
    **Protocol:** WebSocket
    **Path:** /api/v1/webSockets/file-upload
    
    **Message Types:**
    
    1. **start_upload** - Initialize upload session
       ```json
       {
         "type": "start_upload",
         "totalFiles": 3,
         "userId": "user-123",
         "sessionId": "optional-existing-session-id"
       }
       ```
    
    2. **metadata** - Send file metadata
       ```json
       {
         "type": "metadata",
         "fileIndex": 0,
         "fileName": "sales_data.csv",
         "fileId": "550e8400-e29b-41d4-a716-446655440000",
         "projectId": "proj-123",
         "folderId": "folder-456"
       }
       ```
    
    3. **data** - Send file chunk data
       ```json
       {
         "type": "data",
         "fileIndex": 0,
         "data": "base64-encoded-data",
         "encoding": "base64",
         "chunkIndex": 0
       }
       ```
    
    4. **file_complete** - Mark file upload as complete
       ```json
       {
         "type": "file_complete",
         "fileIndex": 0
       }
       ```
    
    5. **process_files** - Trigger file processing and table creation
       ```json
       {
         "type": "process_files",
         "sessionId": "optional-session-id"
       }
       ```
    
    **Response Messages:**
    - upload_started - Upload session initialized
    - file_processed - Individual file processed
    - table_progress - Table creation progress update
    - session_created - Session created with table metadata
    - all_tables_created - All tables successfully created
    - error - Error occurred during processing
    
    **Database Operations:**
    - Creates tables in PostgreSQL using uploads schema
    - Stores table metadata in instance01.mtd_table
    - Updates session entities with new tables/files
    """
    await websocket.accept()
    print("WebSocket connection established")

    # Track upload progress and files
    uploaded_files = {}  # Key: fileIndex, Value: file details
    files_to_process = []
    total_files = 0
    processed_files = 0
    created_tables = []  # Track successfully created table names
    user_id = None  # Will be set from frontend via start_upload message
    files_dict = {}
    # Create DatabaseConfig object for FileUploader
    db_config = DatabaseConfig()
    file_uploader_object = FileUploader(db_config, schema="uploads")

    # Track folder lock state
    locked_folder_id = None
    lock_acquired = False

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "start_upload":
                # Reset state for new upload batch
                total_files = message["totalFiles"]
                processed_files = 0
                created_tables = []
                session_id = message.get("sessionId")
                user_id = message.get("userId")  # Get userId from frontend

                if not user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "userId is required in start_upload message"
                    })
                    continue

                # Persist the incoming sessionId (if any) for use later in the flow
                global_session_id = session_id = message.get("sessionId")
                if session_id:
                    print(f"Adding files to existing session: {session_id}")
                else:
                    print("Creating a new session for file uploads")
                await websocket.send_json(
                    {
                        "type": "upload_started",
                        "totalFiles": total_files,
                        "sessionId": session_id,
                    }
                )

            elif message["type"] == "metadata":
                file_index = message["fileIndex"]
                folder_id = message.get("folderId")
                
                # Mark lock as acquired on first metadata
                # Frontend has already acquired the upload lock before sending files
                if not lock_acquired and folder_id:
                    lock_acquired = True
                    locked_folder_id = folder_id
                    print(f"🔒 Upload lock assumed acquired by frontend for {folder_id}")
                
                # Store file metadata
                uploaded_files[file_index] = {
                    "file_path": os.path.join(
                        UPLOAD_DIR,
                        message["projectId"],
                        folder_id,
                        message["fileName"],
                    ),
                    "file_id": message["fileId"],
                    "table_id": str(uuid.uuid4()).replace("-", ""),
                    "table_name": os.path.splitext(message["fileName"])[0],
                }
                files_dict[message["fileId"]] = message["fileName"]
                os.makedirs(
                    os.path.dirname(uploaded_files[file_index]["file_path"]),
                    exist_ok=True,
                )

            elif message["type"] == "data":
                file_index = message["fileIndex"]
                # Determine if this is the first chunk of data for this file
                # If it's the first chunk, use 'wb' to create/overwrite the file
                # If it's a subsequent chunk, use 'ab' to append to the existing file
                file_mode = "wb" if message.get("chunkIndex", 0) == 0 else "ab"

                with open(uploaded_files[file_index]["file_path"], file_mode) as f:
                    # Check if data is base64 encoded
                    if message.get("encoding") == "base64":
                        import base64

                        # Decode base64 data before writing to file
                        decoded_data = base64.b64decode(message["data"])
                        f.write(decoded_data)
                    else:
                        # Fallback to previous method for backward compatibility
                        f.write(message["data"].encode("latin1"))

            elif message["type"] == "file_complete":
                file_index = message["fileIndex"]
                files_to_process.append(uploaded_files[file_index])
                await websocket.send_json(
                    {"type": "file_processed", "fileIndex": file_index}
                )

            elif message["type"] == "process_files":
                total_to_process = len(files_to_process)
                for index, file_info in enumerate(files_to_process):
                    try:
                        # Offload the heavy synchronous work to a thread pool
                        process_result = await run_in_threadpool(
                            process_file_sync, 
                            file_uploader_object, 
                            file_info
                        )
                        
                        if process_result["success"]:
                            created_tables.append(file_info)
                            processed_files += 1
                            progress = (
                                int((processed_files / total_files) * 100)
                                if total_files
                                else 100
                            )
                            await websocket.send_json(
                                {
                                    "type": "table_progress",
                                    "progress": progress,
                                    "processed": processed_files,
                                    "total": total_files,
                                }
                            )
                        else:
                            raise Exception(
                                f"Failed to create table {file_info['table_id']}"
                            )
                    except Exception as e:
                        print(f"Error processing {file_info['table_name']}: {str(e)}")

                # Send message to /run endpoint with created table names
                if created_tables:
                    # Add tables in DB using explicit DB session (outside FastAPI DI)
                    db = SessionLocal()
                    try:
                        tables_payload = [
                            TableCreate(
                                id=t["table_id"],
                                name=t["table_name"],
                                created_at=datetime.now().isoformat(),
                                created_by=user_id,
                                parent_id=t["file_id"],
                                status="ACTIVE",
                                type="RAW",
                            )
                            for t in created_tables
                        ]

                        table_creation_response = create_table(tables_payload, db)
                    finally:
                        db.close()

                    if (
                        table_creation_response.message
                        == "Table(s) created successfully"
                    ):
                        print(f"Tables {created_tables} created successfully")
                    else:
                        print(f"Failed to create tables {created_tables}")

                    table_ids = ", ".join([t["table_id"] for t in created_tables])
                    print(created_tables)
                    run_message = f"I have created tables {table_ids} in the DB, they will be used in future transformations"
                    try:
                        app_name = "process-mining-app"

                        # Use existing session ID if provided, otherwise create a new one
                        session_id = session_id or create_session_id()
                        print(f"Using session ID: {session_id}")

                        # ---------------------------------------------------------------------
                        # Merge new tables/files into existing session if a sessionId is supplied
                        # ---------------------------------------------------------------------
                        if session_id:
                            try:
                                # Lazy import to avoid circular dependencies
                                from .sessions import get_session, edit_session
                                from schemas import SessionEdit

                                db_merge = SessionLocal()
                                try:
                                    # 1. Fetch existing session data from PostgreSQL
                                    current_resp = get_session(
                                        message["sessionId"], db=db_merge
                                    )
                                    existing_entities = {}
                                    if current_resp and getattr(
                                        current_resp, "data", None
                                    ):
                                        entities_raw = current_resp.data.get("entities")
                                        if entities_raw:
                                            try:
                                                # Parse JSONB field from PostgreSQL
                                                if isinstance(entities_raw, str):
                                                    existing_entities = json.loads(
                                                        entities_raw
                                                    )
                                                else:
                                                    existing_entities = entities_raw
                                            except (TypeError, json.JSONDecodeError):
                                                existing_entities = {}

                                    # 2. Merge tables & files into existing session entities
                                    existing_tables = existing_entities.get(
                                        "tables", {}
                                    )
                                    existing_files = existing_entities.get("files", {})
                                    # Add new tables to existing tables dict
                                    existing_tables.update(
                                        {
                                            t["table_id"]: t["table_name"]
                                            for t in created_tables
                                        }
                                    )
                                    # Add new files to existing files dict
                                    existing_files.update(files_dict)
                                    updated_entities = {
                                        "tables": existing_tables,
                                        "files": existing_files,
                                    }

                                    # 3. Persist update to PostgreSQL via sessions.edit_session
                                    session_edit_payload = SessionEdit(
                                        id=session_id,
                                        entities=updated_entities,
                                    )
                                    edit_session(
                                        payload=session_edit_payload, db=db_merge
                                    )
                                    print(
                                        f"Session {message['sessionId']} entities updated in PostgreSQL with new tables/files."
                                    )
                                finally:
                                    db_merge.close()
                            except Exception as merge_exc:
                                print(
                                    f"Failed to merge entities into existing session: {merge_exc}"
                                )

                        # Only send message to run endpoint if we have tables to process
                        if not created_tables:
                            print("No new tables created, skipping run endpoint")
                            continue
                        
                        # Send session ID to frontend after successful session creation and run endpoint call
                        await websocket.send_json(
                            {
                                "type": "session_created",
                                "sessionId": session_id,
                                "appName": app_name,
                                "userId": user_id,
                                "createdTables": {
                                    table["table_id"]: table["table_name"]
                                    for table in created_tables
                                },
                                "files": files_dict,
                                "message": "Session created successfully and ready for use",
                            }
                        )

                    except Exception as e:
                        print(f"Error in session/run workflow: {str(e)}")
                        # Continue with the rest of the websocket flow even if this fails

                await websocket.send_json(
                    {
                        "type": "all_tables_created",
                        "message": f"Successfully created {processed_files}/{total_files} tables",
                    }
                )
                
                # NOTE: Do NOT release the folder lock here. The user is still
                # on the Upload page, which owns the lock lifecycle via its
                # heartbeat + unmount cleanup.  Releasing here created a gap
                # that allowed a second user to acquire the lock (Bug A).
                
                # Reset tracking for the next batch of files
                uploaded_files.clear()
                files_to_process = []
                total_files = 0
                processed_files = 0
                created_tables = []

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {str(e)}")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        # NOTE: Do NOT release the folder lock on WebSocket disconnect.
        # The Upload page component owns the lock lifecycle.  If the user
        # navigates away, the page cleanup releases the lock.  If the
        # browser crashes, the Redis TTL handles expiry automatically.
        print("Closing connection")

