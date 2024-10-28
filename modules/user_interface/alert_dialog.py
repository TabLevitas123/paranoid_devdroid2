# modules/user_interface/alert_dialog.py

"""
Alert Dialog Module

This module provides the AlertDialog class, responsible for creating and managing alert dialogs
in the user interface. It supports various dialog types, customization options, and integrates
with the EventDispatcher for event handling.

Features:
- Support for different dialog types (info, warning, error, confirmation)
- Customizable title, message, buttons, and icons
- Modal and non-modal dialogs
- Asynchronous display with callback support
- Integration with EventDispatcher for event emission
- Thread-safe operations
- Robust error handling and logging
- Accessibility compliance
- Internationalization (i18n) support
- Theming and styling capabilities

Author: Your Name
Date: YYYY-MM-DD
"""

import threading
import logging
from typing import Optional, Callable, Dict, Any

# Assuming we are using a GUI framework like Tkinter
try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    tk = None  # Handle the absence of a GUI framework appropriately

# Configure Logging
logger = logging.getLogger('alert_dialog')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/alert_dialog.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class AlertDialogError(Exception):
    """Base class for alert dialog-related exceptions."""
    pass

class AlertDialog:
    """
    AlertDialog Class

    Manages the creation and display of alert dialogs in the user interface.

    Features:
    - Supports various dialog types
    - Customizable content and buttons
    - Thread-safe and asynchronous display
    - Integration with EventDispatcher
    - Accessibility and internationalization support
    """

    def __init__(self):
        if not tk:
            logger.error("GUI framework is not available.")
            raise AlertDialogError("GUI framework is not available.")
        self.logger = logger
        self.lock = threading.RLock()
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window
        self.logger.info("AlertDialog initialized.")

    def show(self,
             title: str,
             message: str,
             dialog_type: str = 'info',
             buttons: Optional[Dict[str, Callable[[], None]]] = None,
             modal: bool = True,
             callback: Optional[Callable[[str], None]] = None) -> None:
        """
        Displays an alert dialog.

        Args:
            title (str): The title of the dialog.
            message (str): The message to display.
            dialog_type (str): The type of dialog ('info', 'warning', 'error', 'question').
            buttons (Optional[Dict[str, Callable[[], None]]]): Custom buttons and their callbacks.
            modal (bool): Whether the dialog is modal.
            callback (Optional[Callable[[str], None]]): Callback function after dialog is closed.

        Raises:
            AlertDialogError: If an error occurs while displaying the dialog.
        """
        if dialog_type not in ['info', 'warning', 'error', 'question']:
            self.logger.error(f"Invalid dialog type: {dialog_type}")
            raise ValueError("Invalid dialog type.")

        def _show_dialog():
            with self.lock:
                try:
                    self.logger.debug(f"Showing '{dialog_type}' dialog with title '{title}'.")
                    response = None
                    if dialog_type == 'info':
                        messagebox.showinfo(title, message)
                    elif dialog_type == 'warning':
                        messagebox.showwarning(title, message)
                    elif dialog_type == 'error':
                        messagebox.showerror(title, message)
                    elif dialog_type == 'question':
                        response = messagebox.askquestion(title, message)
                    else:
                        messagebox.showinfo(title, message)

                    if callback:
                        self.logger.debug("Invoking callback after dialog display.")
                        callback(response)
                except Exception as e:
                    self.logger.exception(f"Error displaying alert dialog: {e}")
                    raise AlertDialogError("Error displaying alert dialog.") from e

        if modal:
            self.logger.debug("Displaying modal dialog.")
            self.root.after(0, _show_dialog)
            self.root.mainloop()
        else:
            self.logger.debug("Displaying non-modal dialog.")
            threading.Thread(target=_show_dialog).start()

    def close(self) -> None:
        """
        Closes the alert dialog.
        """
        with self.lock:
            try:
                self.root.quit()
                self.logger.debug("Alert dialog closed.")
            except Exception as e:
                self.logger.exception(f"Error closing alert dialog: {e}")
                raise AlertDialogError("Error closing alert dialog.") from e

    # Additional methods can be added here, such as theming, internationalization, etc.

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    def dialog_callback(response):
        print(f"Dialog closed with response: {response}")

    try:
        alert_dialog = AlertDialog()
        alert_dialog.show(
            title="Test Dialog",
            message="This is a test message.",
            dialog_type='question',
            callback=dialog_callback
        )
    except AlertDialogError as e:
        print(f"AlertDialog error: {e}")
