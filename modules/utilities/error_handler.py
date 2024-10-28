 # utilities/error_handler.py

import logging
import sys
import traceback
from modules.utilities.logging_manager import setup_logging

class ErrorHandler:
    """
    Handles exceptions and errors throughout the application.
    """
    def __init__(self):
        self.logger = setup_logging('ErrorHandler')
        self.logger.info("ErrorHandler initialized successfully.")

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """
        Handles uncaught exceptions by logging them.

        Args:
            exc_type (type): The exception type.
            exc_value (Exception): The exception instance.
            exc_traceback (traceback): The traceback object.
        """
        if issubclass(exc_type, KeyboardInterrupt):
            # Call the default excepthook for KeyboardInterrupt
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        self.logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Function to be set as the global exception handler.

    Args:
        exc_type (type): The exception type.
        exc_value (Exception): The exception instance.
        exc_traceback (traceback): The traceback object.
    """
    error_handler = ErrorHandler()
    error_handler.handle_exception(exc_type, exc_value, exc_traceback)
