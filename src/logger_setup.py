import os
import logging
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("logs")
logger.setLevel(logging.INFO)
logger.propagate = False

# Set formatter for log messages
formatter = logging.Formatter(
    fmt='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create a StreamHandler for terminal output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

def setup_logger_file(log_directory: str, max_size_mb: int, max_files: int):
    """
    Set up the logger file handler with given log directory, max file size and number of files to keep.
    """

    # Create a FileHandler for file output
    file_handler = RotatingFileHandler(
        os.path.join(log_directory, 'logs.log'), 
        maxBytes=max_size_mb*1024*1024, 
        backupCount=max_files-1
        )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)