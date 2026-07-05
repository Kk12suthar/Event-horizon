import psycopg2
import psycopg2.extras
import datetime
import decimal
import base64
import uuid


def serialize_value(v):
    """Serialize PostgreSQL values for JSON response."""
    if isinstance(v, uuid.UUID):
        return str(v)
    elif isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    elif isinstance(v, bytes):
        return base64.b64encode(v).decode("utf-8")  # or use v.hex() if preferred
    elif isinstance(v, decimal.Decimal):
        return float(v)  # or str(v) if you want exact precision
    else:
        return v


def get_data(
    table_name: str,
    db_config: dict,
    page: int = 1,
    limit: int = 10,
    schema: str = "uploads",
    folder_id: str = None,
) -> dict:
    """Fetch paginated data from PostgreSQL database.

    Args:
        table_name (str): The name of the table to query (will be properly escaped).
        db_config (dict): Database connection configuration.
        page (int): The page number to fetch.
        limit (int): The number of records per page.
        schema (str): The schema name (default: 'uploads').
        folder_id (str): The folder ID to set as the app.folder_id session variable.
                         REQUIRED when the table has been processed by the MCP agent,
                         which applies FORCE ROW LEVEL SECURITY with the policy:
                             USING (folder_id = current_setting('app.folder_id', true))
                         Without this, current_setting() returns NULL and every row is
                         filtered out for non-superuser DB roles - which is why root
                         credentials work but the app user sees an empty result.

    Returns:
        dict: A dictionary containing the fetched data, total count, current page, and limit.
    """
    offset = (page - 1) * limit

    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # CRITICAL: Set app.folder_id so RLS policies applied by the MCP agent evaluate
    # correctly before any SELECT on this connection.
    # The agent enforces: USING (folder_id = current_setting('app.folder_id', true))
    # If this is not set, current_setting() returns NULL → every row is denied for
    # non-superusers, while root bypasses RLS entirely - matching the reported symptom.
    if folder_id:
        # Normalize: strip dashes and lowercase to match the format the MCP agent uses.
        # The agent's _normalize_folder_id() strips all dashes before:
        #   1. Storing the value in the folder_id column (DEFAULT '<no-dash-id>')
        #   2. Setting SET app.folder_id = '<no-dash-id>'
        # The RLS policy is: USING (folder_id = current_setting('app.folder_id', true))
        # So both sides MUST use the same no-dash format or every row is denied.
        safe_folder_id = "".join(c for c in folder_id if c.isalnum()).lower()
        cursor.execute(f"SET app.folder_id = '{safe_folder_id}'")

    # Properly escape the schema and table name by quoting them
    safe_schema = f'"{schema.replace(chr(34), chr(34) + chr(34))}"'
    safe_table_name = f'"{table_name.replace(chr(34), chr(34) + chr(34))}"'
    full_table_name = f"{safe_schema}.{safe_table_name}"

    # Get total count
    cursor.execute(f"SELECT COUNT(*) AS total FROM {full_table_name}")
    total = cursor.fetchone()["total"]

    # Fetch paginated data
    cursor.execute(
        f"SELECT * FROM {full_table_name} LIMIT %s OFFSET %s",
        (limit, offset),
    )
    rows = cursor.fetchall()

    # Get column names
    column_names = [desc[0] for desc in cursor.description]

    cursor.close()
    conn.close()

    return {
        "columns": column_names,
        "data": [{k: serialize_value(v) for k, v in row.items()} for row in rows],
        "total": total,
        "page": page,
        "limit": limit,
    }
