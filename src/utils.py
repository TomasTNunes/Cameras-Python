import os
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