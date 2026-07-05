#!/usr/bin/env python3
"""
File Uploader for PostgreSQL Database with Backup System Integration

This script uploads CSV or XLSX files to a PostgreSQL database.
Integrates with backup monitoring system to prevent conflicts during uploads.
"""

import os
import sys
import pandas as pd
import psycopg2
from psycopg2 import Error, sql, extras
from pathlib import Path
import logging
from typing import Optional, Dict, Any
import argparse
from datetime import datetime
from tqdm import tqdm
import time

# Add dotenv support for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[WARNING] python-dotenv not installed, relying on system environment variables.")

# Import upload integration
try:
    from utils.upload_integration import UploadManager
    BACKUP_INTEGRATION = True
except ImportError:
    print("[WARNING] Backup system integration not available")
    BACKUP_INTEGRATION = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('upload.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration class for maintainability and security."""
    
    def __init__(self):
        """Load database configuration from environment variables."""
        self.host = os.environ.get("POSTGRES_HOST")
        self.port = int(os.environ.get("POSTGRES_PORT", 5432))
        self.user = os.environ.get("POSTGRES_USER")
        self.password = os.environ.get("POSTGRES_PASSWORD")
        self.database = os.environ.get("POSTGRES_UPLOAD_DBNAME")

        if not all([self.host, self.user, self.password, self.database]):
            print("[ERROR] Critical database configuration is missing.")
            print("Please ensure DB_HOST, DB_USER, DB_PASSWORD, and DB_NAME are set in your .env file or system environment.")
            sys.exit(1)
    
    def get_connection_params(self) -> Dict[str, Any]:
        """Return connection parameters as dictionary."""
        return {
            'host': self.host,
            'port': self.port,
            'user': self.user,
            'password': self.password,
            'dbname': self.database,
            'connect_timeout': 10
        }

class FileUploader:
    """Main class for handling file uploads to PostgreSQL database."""

    def __init__(self, db_config: DatabaseConfig, schema: str = "public"):
        self.db_config = db_config
        self.connection: Optional[psycopg2.extensions.connection] = None
        self.schema = schema  # PostgreSQL schema for all uploaded file tables

        # Initialize backup integration
        if BACKUP_INTEGRATION:
            self.upload_mgr = UploadManager()
        else:
            self.upload_mgr = None
    
    def connect_to_database(self) -> bool:
        """Establish connection to PostgreSQL database."""
        try:
            self.connection = psycopg2.connect(**self.db_config.get_connection_params())
            self.connection.autocommit = True
            logger.info(f"Successfully connected to PostgreSQL database: {self.db_config.database}")
            return True
        except Error as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            return False
    
    def disconnect_from_database(self):
        """Close database connection safely."""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.info("PostgreSQL connection closed")
    
    def validate_file(self, file_path: str) -> bool:
        """Validate if file exists and has supported extension."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in ['.csv', '.xlsx', '.xls']:
            logger.error(f"Unsupported file format: {file_extension}. Supported formats: .csv, .xlsx, .xls")
            return False
        
        return True
    
    def read_file(self, file_path: str) -> Optional[pd.DataFrame]:
        """Read CSV or XLSX file into pandas DataFrame."""
        try:
            file_extension = Path(file_path).suffix.lower()
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            print(f"\n📁 Reading file: {Path(file_path).name}")
            print(f"📏 File size: {file_size_mb:.2f} MB")
            
            df = None
            
            if file_extension == '.csv':
                print("🔍 Detecting CSV encoding...")
                encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
                for encoding in encodings:
                    try:
                        print(f"   Trying {encoding} encoding...")
                        df = pd.read_csv(file_path, encoding=encoding)
                        print(f"✅ Successfully read CSV file with {encoding} encoding")
                        logger.info(f"Successfully read CSV file with {encoding} encoding")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    print("❌ Failed to read CSV file with any supported encoding")
                    logger.error("Failed to read CSV file with any supported encoding")
                    return None
            
            elif file_extension in ['.xlsx', '.xls']:
                print("📖 Reading Excel file...")
                df = pd.read_excel(file_path)
                print("✅ Successfully read Excel file")
                logger.info("Successfully read Excel file")
            
            if df is not None:
                rows, cols = df.shape
                print(f"📊 File loaded: {rows:,} rows × {cols} columns")
                print(f"📋 Columns: {', '.join(df.columns[:5])}{'...' if len(df.columns) > 5 else ''}")
                logger.info(f"File contains {rows} rows and {cols} columns")
            
            return df
            
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            logger.error(f"Error reading file {file_path}: {e}")
            return None
    
    def sanitize_column_name(self, column_name: str) -> str:
        """Sanitize column name for MySQL compatibility."""
        # Handle NaN values from pandas
        if pd.isna(column_name) or str(column_name).lower() in ['nan', 'none', 'null', '']:
            return "unnamed_column"
        
        sanitized = str(column_name).replace(' ', '_').replace('-', '_')
        sanitized = ''.join(c if c.isalnum() or c == '_' else '_' for c in sanitized)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"{sanitized}"
        if not sanitized or sanitized.lower() == 'nan':
            sanitized = "unnamed_column"
        return sanitized.lower()
    
    def infer_postgres_type(self, series: pd.Series) -> str:
        """Infer PostgreSQL column type from pandas Series."""
        series_clean = series.dropna()
        
        if len(series_clean) == 0:
            return "TEXT"
        
        if pd.api.types.is_integer_dtype(series):
            max_val = series_clean.max()
            min_val = series_clean.min()
            
            if min_val >= -32768 and max_val <= 32767:
                return "SMALLINT"
            elif min_val >= -2147483648 and max_val <= 2147483647:
                return "INTEGER"
            else:
                return "BIGINT"
        
        elif pd.api.types.is_float_dtype(series):
            return "NUMERIC(15,4)"
        elif pd.api.types.is_datetime64_any_dtype(series):
            return "TIMESTAMP"
        elif pd.api.types.is_bool_dtype(series):
            return "BOOLEAN"
        else:
            max_length = series_clean.astype(str).str.len().max()
            if max_length <= 255:
                return f"VARCHAR({max(max_length, 50)})"
            else:
                return "TEXT"
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table already exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            bool: True if table exists, False otherwise
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = %s
                    AND table_name = %s
                )
            """, (self.schema, table_name))
            exists = cursor.fetchone()[0]
            cursor.close()
            return exists
        except Error as e:
            logger.error(f"Error checking if table exists: {e}")
            return False
    
    def create_table(self, table_name: str, df: pd.DataFrame) -> bool:
        """Create PostgreSQL table based on DataFrame structure, replicating the source file exactly."""
        try:
            cursor = self.connection.cursor()
            table_name = self.sanitize_column_name(table_name)

            print(f"\n🏗️  Creating table structure in PostgreSQL ({self.schema} schema)...")
            print(f"   📝 Table name: '{self.schema}.{table_name}'")
            
            # Step 1: Sanitize and de-duplicate column names from the source file.
            sanitized_columns = []
            column_counts = {}
            
            print(f"   🔍 Analyzing {len(df.columns)} columns...")
            for col in df.columns:
                sanitized = self.sanitize_column_name(col)
                
                # Handle duplicate source columns by appending a suffix
                if sanitized in column_counts:
                    column_counts[sanitized] += 1
                    unique_sanitized = f"{sanitized}_{column_counts[sanitized]}"
                else:
                    column_counts[sanitized] = 1 # Start with 1 for clarity if duplicates are found
                    unique_sanitized = sanitized
                
                sanitized_columns.append(unique_sanitized)
            
            df.columns = sanitized_columns

            # Step 2: Build column definitions for the user-provided data.
            column_definitions = []
            for i, sanitized_col_name in enumerate(sanitized_columns):
                postgres_type = self.infer_postgres_type(df.iloc[:, i])
                column_definitions.append(f"\"{sanitized_col_name}\" {postgres_type}")
            
            # Step 3: Construct the final CREATE TABLE statement for PostgreSQL.
            # This creates a table in the configured schema.
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.schema}."{table_name}" (
                {', '.join(column_definitions)}
            )
            """

            print(f"   ⚡ Executing CREATE TABLE command...")
            cursor.execute(create_table_sql)
            print(f"✅ Table '{self.schema}.{table_name}' created successfully!")
            logger.info(f"Table '{self.schema}.{table_name}' created successfully")
            
            cursor.close()
            return True
            
        except Error as e:
            print(f"❌ Error creating table: {e}")
            logger.error(f"Error creating table '{self.schema}.{table_name}': {e}")
            return False
    
    def _trigger_monitor(self, table_name: str):
        """
        Creates a final database write to a trigger table.
        This notifies the unified_snapshot_monitor that an upload has finished
        and that it should perform post-upload cleanup and backup tasks.
        """
        if not self.connection or self.connection.closed:
            logger.warning("No database connection available to trigger the monitor.")
            return
        
        try:
            cursor = self.connection.cursor()
            trigger_table = "_upload_completed_trigger"

            # Ensure the trigger table exists in the same schema as uploaded tables
            create_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.schema}."{trigger_table}" (
                "id" SERIAL PRIMARY KEY,
                "table_name" VARCHAR(255) NOT NULL,
                "triggered_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_sql)

            # Insert a record to create a WAL event
            insert_sql = f"INSERT INTO {self.schema}.\"{trigger_table}\" (table_name) VALUES (%s)"
            cursor.execute(insert_sql, (table_name,))

            # IMPORTANT: Commit the transaction to persist the trigger record
            self.connection.commit()

            logger.info(f"Successfully triggered monitor for completed upload of table '{table_name}'")
            cursor.close()
        except Error as e:
            logger.error(f"Failed to trigger monitor for table '{table_name}': {e}")

    def insert_data(self, table_name: str, df: pd.DataFrame) -> bool:
        """Insert DataFrame data into PostgreSQL table with progress tracking."""
        try:
            cursor = self.connection.cursor()
            table_name = self.sanitize_column_name(table_name)
            
            # Column names should already be sanitized from create_table
            sanitized_columns = list(df.columns)
            print(f"🔍 Using pre-sanitized column names: {len(sanitized_columns)} columns")
            
            print(f"\n📊 Preparing data for upload...")
            
            df_clean = df.copy()
            df_clean = df_clean.where(pd.notnull(df_clean), None)
            
            placeholders = ', '.join(['%s'] * len(sanitized_columns))
            column_list = ', '.join([f"\"{col}\"" for col in sanitized_columns])
            insert_sql = f"INSERT INTO {self.schema}.\"{table_name}\" ({column_list}) VALUES ({placeholders})"

            # Debug: Show the SQL structure
            print(f"🔍 SQL Structure Debug:")
            print(f"   Schema.Table: {self.schema}.{table_name}")
            print(f"   Columns ({len(sanitized_columns)}): {sanitized_columns[:5]}{'...' if len(sanitized_columns) > 5 else ''}")
            print(f"   SQL: {insert_sql[:100]}{'...' if len(insert_sql) > 100 else ''}")
            print(f"   Total rows to insert: {len(df_clean)}")
            
            print("🔄 Converting data format...")
            
            # Comprehensive NaN cleanup - handle both string 'nan' and float NaN values
            print("🧹 Cleaning NaN values...")
            
            # Step 1: Replace string 'nan' variants with None
            df_clean = df_clean.replace(['nan', 'NaN', 'NAN', 'null', 'NULL', 'Null'], None)
            
            # Step 2: Convert to numpy array and handle float NaN values
            import numpy as np
            values_array = df_clean.values
            
            # Replace any remaining NaN values (including float NaN) with None
            clean_values = []
            for row in values_array:
                clean_row = []
                for val in row:
                    if pd.isna(val) or (isinstance(val, float) and np.isnan(val)) or str(val).lower() == 'nan':
                        clean_row.append(None)
                    else:
                        clean_row.append(val)
                clean_values.append(tuple(clean_row))
            
            data_tuples = clean_values
            
            # Debug: Check first few rows for any remaining 'nan' issues
            print(f"🔍 Data Sample Debug (first row after cleanup):")
            if len(data_tuples) > 0:
                first_row = data_tuples[0]
                nan_positions = [i for i, val in enumerate(first_row) if val is not None and str(val).lower() == 'nan']
                none_positions = [i for i, val in enumerate(first_row) if val is None]
                
                if nan_positions:
                    print(f"   ⚠️  Still found 'nan' strings at positions: {nan_positions}")
                    for pos in nan_positions:
                        print(f"      Column '{sanitized_columns[pos]}' contains: {repr(first_row[pos])}")
                else:
                    print(f"   ✅ No 'nan' strings found in first row")
                
                if none_positions[:5]:  # Show first 5 None positions
                    print(f"   📝 None values at positions: {none_positions[:5]}{'...' if len(none_positions) > 5 else ''}")
                    print(f"   📊 Total None values in first row: {len(none_positions)}")
            
            total_rows = len(data_tuples)
            batch_size = min(1000, max(100, total_rows // 10))

            print(f"\n📤 Uploading {total_rows:,} rows to PostgreSQL table '{self.schema}.{table_name}'...")

            uploaded_rows = 0
            with tqdm(total=total_rows, desc="Uploading", unit="rows", ncols=100) as pbar:
                for i in range(0, total_rows, batch_size):
                    batch = data_tuples[i:i + batch_size]
                    # Use execute_batch for better PostgreSQL performance
                    extras.execute_batch(cursor, insert_sql, batch)

                    uploaded_rows += len(batch)
                    pbar.update(len(batch))

                    percentage = (uploaded_rows / total_rows) * 100
                    pbar.set_postfix({
                        'Progress': f'{percentage:.1f}%',
                        'Uploaded': f'{uploaded_rows:,}/{total_rows:,}'
                    })

            print(f"✅ Successfully uploaded {total_rows:,} rows to table '{self.schema}.{table_name}'!")
            logger.info(f"Successfully inserted {total_rows} rows into table '{self.schema}.{table_name}'")
            
            cursor.close()
            return True
            
        except Error as e:
            print(f"❌ Error uploading data: {e}")
            logger.error(f"Error inserting data into table '{self.schema}.{table_name}': {e}")
            return False

    def is_initial_backup_running(self) -> bool:
        """
        Checks if the initial backup is running by looking for a lock file.
        """
        lock_file_path = os.path.join("./upload_states", "initial_backup.lock")
        if os.path.exists(lock_file_path):
            logger.warning("Initial backup lock file found. Uploads are blocked.")
            return True
        logger.info("Initial backup lock file not found. Uploads are allowed.")
        return False
    
    def upload_file(self, file_path: str, table_name: Optional[str] = None) -> bool:
        """Main method to upload file to PostgreSQL database with backup system integration."""
        if self.is_initial_backup_running():
            print("\n❌ Upload Blocked: The initial database backup is currently in progress.")
            print("   To ensure data integrity, file uploads are disabled until the first full backup is created.")
            print("   Please wait for the initial backup to complete and then try again.")
            logger.warning("Upload blocked because initial backup lock file was found.")
            return False
            
        start_time = time.time()
        
        # Generate table name if not provided
        if table_name is None:
            table_name = Path(file_path).stem
        
        table_name = self.sanitize_column_name(table_name)
        
        # **BACKUP INTEGRATION: Start upload**
        if self.upload_mgr:
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            self.upload_mgr.start_upload(table_name, {
                "source_file": file_path,
                "file_size_mb": round(file_size, 2)
            })
        
        upload_success = False
        
        try:
            # Validate file
            print(f"🔍 Validating file...")
            if not self.validate_file(file_path):
                return False
            
            # Connect to database
            print(f"🔌 Connecting to PostgreSQL database...")
            if not self.connect_to_database():
                return False
            
            # Read file
            df = self.read_file(file_path)
            if df is None:
                return False
            
            # Check if table already exists
            print(f"\n🔍 Checking if table '{table_name}' already exists...")
            if self.table_exists(table_name):
                print(f"\n⚠️  WARNING: Table '{table_name}' already exists in the database!")
                print(f"   📊 This table may contain existing data that would be overwritten.")
                print(f"   🛡️  To protect your existing data, this upload has been terminated.")
                print(f"\n💡 Options:")
                print(f"   1. Use a different table name when uploading this file")
                print(f"   2. Manually drop the existing table if you want to replace it:")
                print(f"      DROP TABLE \"{table_name}\";")
                print(f"   3. Use the restore feature to revert to a previous backup")
                logger.warning(f"Upload terminated: Table '{table_name}' already exists")
                return False
            
            print(f"✅ Table name is available")
            
            # Create table
            if not self.create_table(table_name, df):
                return False
            
            # Insert data
            if not self.insert_data(table_name, df):
                return False
            
            # Calculate upload time
            end_time = time.time()
            upload_time = end_time - start_time
            rows_per_second = len(df) / upload_time if upload_time > 0 else 0
            
            print(f"\n🎯 Upload Summary:")
            print(f"   📊 Rows uploaded: {len(df):,}")
            print(f"   📋 Columns: {len(df.columns)}")
            print(f"   ⏱️  Upload time: {upload_time:.2f} seconds")
            print(f"   🚀 Speed: {rows_per_second:.0f} rows/second")
            print(f"   🏷️  Table: '{self.schema}.{table_name}'")

            logger.info(f"File '{file_path}' successfully uploaded to table '{self.schema}.{table_name}' in {upload_time:.2f}s")
            upload_success = True
        except Exception as e:
            print(f"❌ Unexpected error during upload: {e}")
            logger.error(f"Unexpected error during upload: {e}")
            upload_success = False
        finally:
            # **BACKUP INTEGRATION: Finish upload**
            if self.upload_mgr:
                # First mark upload as complete
                self.upload_mgr.finish_upload(table_name, success=upload_success)

            # Always notify the monitor about upload completion (regardless of backup integration)
            if upload_success:
                self._trigger_monitor(table_name)

            # Now it is safe to close the connection
            self.disconnect_from_database()
        
        return upload_success
            

def get_file_path_interactive() -> Optional[str]:
    """
    Interactive file path input with validation.
    
    Returns:
        Optional[str]: Valid file path or None if cancelled
    """
    print("\n" + "="*60)
    print("🚀 CSV/XLSX to PostgreSQL File Uploader")
    print("="*60)
    
    while True:
        print(f"\n📁 Enter file path (or 'q' to quit):")
        print("   Supported formats: .csv, .xlsx, .xls")
        print("   Examples:")
        print("     - data.csv")
        print("     - C:\\Users\\user\\Documents\\data.xlsx")
        print("     - ./folder/file.csv")
        
        file_path = input("\n📂 File path: ").strip()
        
        if file_path.lower() in ['q', 'quit', 'exit']:
            return None
        
        if not file_path:
            print("❌ Please enter a file path")
            continue
        
        # Remove quotes if present
        file_path = file_path.strip('"').strip("'")
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            print("   Please check the path and try again")
            continue
        
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in ['.csv', '.xlsx', '.xls']:
            print(f"❌ Unsupported file format: {file_extension}")
            print("   Supported formats: .csv, .xlsx, .xls")
            continue
        
        return file_path

def get_table_name_interactive(default_name: str) -> str:
    """
    Interactive table name input.
    
    Args:
        default_name (str): Default table name based on filename
        
    Returns:
        str: Table name to use
    """
    print(f"\n🏷️  Table name (press Enter for default: '{default_name}'):")
    table_name = input("   Table name: ").strip()
    
    if not table_name:
        return default_name
    
    # Sanitize the input table name
    sanitized = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
    if sanitized != table_name:
        print(f"   📝 Sanitized table name: '{sanitized}'")
    
    return sanitized or default_name

def main():
    """Main function with command-line and interactive interfaces."""
    parser = argparse.ArgumentParser(
        description="Upload CSV or XLSX files to PostgreSQL database",
        epilog="Example: python file_uploader.py data.csv --table my_table"
    )
    parser.add_argument("file_path", nargs='?', help="Path to the CSV or XLSX file to upload")
    parser.add_argument("--table", "-t", help="Custom table name (defaults to filename)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--interactive", "-i", action="store_true", help="Use interactive mode")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize db_config early to show in configuration summary
    db_config = DatabaseConfig()
    
    # Determine file path
    file_path = args.file_path
    table_name = args.table
    
    # Use interactive mode if no file path provided or explicitly requested
    if not file_path or args.interactive:
        file_path = get_file_path_interactive()
        if not file_path:
            print("\n👋 Upload cancelled by user")
            sys.exit(0)
        
        # Get table name interactively if not provided
        if not table_name:
            default_table = Path(file_path).stem
            table_name = get_table_name_interactive(default_table)
    
    print(f"\n🔧 Configuration:")
    print(f"   📁 File: {file_path}")
    print(f"   🏷️  Table: {table_name or Path(file_path).stem}")
    print(f"   🗄️  Database: {db_config.user}@{db_config.host}:{db_config.port}/{db_config.database}")
    
    # Show backup integration status
    if BACKUP_INTEGRATION:
        print(f"   🔄 Backup integration: ACTIVE (communicates with monitoring system)")
    else:
        print(f"   🔄 Backup integration: Not available")
    
    # Confirm before proceeding
    if not args.file_path:  # Only ask for confirmation in interactive mode
        confirm = input(f"\n❓ Proceed with upload? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("\n👋 Upload cancelled by user")
            sys.exit(0)
    
    # Initialize uploader
    uploader = FileUploader(db_config)
    
    # Upload file
    print(f"\n🚀 Starting upload process...")
    success = uploader.upload_file(file_path, table_name)
    
    if success:
        print(f"\n🎉 SUCCESS: File '{Path(file_path).name}' uploaded successfully!")
        print(f"   📊 Data is now available in table '{table_name or Path(file_path).stem}'")
        print(f"🔗 Connect to pgAdmin or psql to view your data")
        sys.exit(0)
    else:
        print(f"\n💥 FAILED: Could not upload file '{Path(file_path).name}'")
        print(f"   📋 Check the log file 'upload.log' for detailed error information")
        sys.exit(1)

if __name__ == "__main__":
    main() 
