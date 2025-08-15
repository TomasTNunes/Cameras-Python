import os
import time
from logger_setup import logger

def check_create_directory(directory: str):
    """
    Check if the directory exists, if not, create it.
    """
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
            logger.info(f'Directory {os.path.abspath(directory)} created.')
        except OSError as e:
            logger.error(f"Error creating directory {os.path.abspath(directory)}: {e}")
            raise(f"Error creating directory {os.path.abspath(directory)}: {e}")

def convert_time_to_datetime(time_float: float):
    """
    Converts `time.time()` to:
    - date string: `DD-MM-YYYY`
    - time string: `HH:MM:SS.MS`
    """
    local_time = time.localtime(time_float)
    millis = int((time_float - int(time_float)) * 1000)
    date_str = time.strftime("%d-%m-%Y", local_time)
    time_str = time.strftime(f"%H:%M:%S.{millis:03d}", local_time)
    return date_str, time_str