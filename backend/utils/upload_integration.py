#!/usr/bin/env python3
"""
Upload Integration System for Backup Monitoring
This allows upload code to communicate with the backup system
"""

import os
import json
import time
from datetime import datetime

class UploadManager:
    """Manages upload state communication with backup system"""
    
    def __init__(self, state_dir="./upload_states"):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
    
    def start_upload(self, table_name, upload_info=None):
        """Notify backup system that upload is starting"""
        state_file = os.path.join(self.state_dir, f"{table_name}_upload.json")
        state = {
            "status": "uploading",
            "start_time": time.time(),
            "start_timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "table_name": table_name,
            "upload_info": upload_info or {}
        }
        
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        
        print(f"[UPLOAD] Started upload for table '{table_name}' - backup system notified")
        return state_file
    
    def finish_upload(self, table_name, success=True):
        """Notify backup system that upload is complete"""
        state_file = os.path.join(self.state_dir, f"{table_name}_upload.json")
        
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state = json.load(f)
            
            state.update({
                "status": "completed" if success else "failed",
                "end_time": time.time(),
                "end_timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "duration": time.time() - state.get("start_time", 0)
            })
            
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            print(f"[UPLOAD] {'Completed' if success else 'Failed'} upload for table '{table_name}' - creating original backup")
            return True
        
        return False
    
    def is_uploading(self, table_name):
        """Check if table is currently being uploaded"""
        state_file = os.path.join(self.state_dir, f"{table_name}_upload.json")
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
            return state.get("status") == "uploading"
        except:
            return False
    
    def get_upload_state(self, table_name):
        """Get current upload state for table"""
        state_file = os.path.join(self.state_dir, f"{table_name}_upload.json")
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def cleanup_old_states(self, max_age_hours=24):
        """Clean up old upload state files"""
        current_time = time.time()
        for filename in os.listdir(self.state_dir):
            if filename.endswith('_upload.json'):
                filepath = os.path.join(self.state_dir, filename)
                try:
                    file_age = current_time - os.path.getmtime(filepath)
                    if file_age > max_age_hours * 3600:
                        os.remove(filepath)
                        print(f"[CLEANUP] Removed old upload state: {filename}")
                except Exception as e:
                    print(f"[ERROR] Failed to cleanup {filename}: {e}")

# Example usage for your upload code
def example_upload_integration():
    """Example of how to integrate this with your upload code"""
    upload_mgr = UploadManager()
    
    # 1. At start of your upload function
    table_name = "your_table_name"
    upload_mgr.start_upload(table_name, {"file_size": "50GB", "source": "data_import"})
    
    try:
        # 2. Your existing upload code here
        print("Uploading data...")
        time.sleep(2)  # Simulate upload
        
        # 3. At end of successful upload
        upload_mgr.finish_upload(table_name, success=True)
        
    except Exception as e:
        # 4. If upload fails
        upload_mgr.finish_upload(table_name, success=False)
        raise

if __name__ == "__main__":
    # Test the integration
    example_upload_integration() 