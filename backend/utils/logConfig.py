import logging
from pathlib import Path
import config
from datetime import datetime


logs_dir = config.logs_folder
today = datetime.today().strftime("%Y-%m-%d")

# Ensure logs directory exists
logs_dir.mkdir(parents=True, exist_ok=True)
ALL_LOGS_FILE = logs_dir / f"{today}.log"

# Logger 2: Logger
logger = logging.getLogger("General")
logger.setLevel(logging.INFO)

# Prevent duplicate handlers
if not logger.hasHandlers():
    logHandler = logging.FileHandler(ALL_LOGS_FILE)  # Logs to file
    logFormatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [User ID: %(user_id)s] - %(message)s"
    )
    logHandler.setFormatter(logFormatter)
    logger.addHandler(logHandler)
