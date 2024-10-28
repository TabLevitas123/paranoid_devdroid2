# modules/utilities/logging_manager.py

import logging
import os

def setup_logging(name: str, log_file: str = None, level: str = 'DEBUG') -> logging.Logger:
    """
    Sets up and returns a logger with specified configurations.

    Args:
        name (str): Name of the logger.
        log_file (str, optional): File path for logging. If None, logs to console.
        level (str): Logging level.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if not logger.handlers:
        if log_file:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        else:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    return logger
