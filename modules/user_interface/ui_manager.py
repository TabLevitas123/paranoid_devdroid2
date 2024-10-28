# user_interface/ui_manager.py

import logging
import tkinter as tk
from tkinter import ttk
from modules.utilities.logging_manager import setup_logging
from user_interface.metrics_display import MetricsDisplay
from user_interface.notification_system import NotificationSystem


class UIManager:
    """
    Manages the user interface components and event handling.
    """

    def __init__(self):
        self.logger = setup_logging('UIManager')
        self.root = tk.Tk()
        self.root.title("Agent Interface")
        self.logger.info("Initializing UIManager.")
        self.metrics_display = MetricsDisplay(self.root)
        self.notification_system = NotificationSystem(self.root)
        self._setup_ui()
        self.logger.info("UIManager initialized successfully.")

    def _setup_ui(self):
        """
        Sets up the UI components.
        """
        try:
            self.logger.debug("Setting up UI components.")
            # Create main frames
            self.main_frame = ttk.Frame(self.root, padding="10")
            self.main_frame.pack(fill=tk.BOTH, expand=True)

            # Add components to the main frame
            self.metrics_display.create_widgets(self.main_frame)
            self.notification_system.create_widgets(self.main_frame)

            self.logger.info("UI components set up successfully.")
        except Exception as e:
            self.logger.error(f"Error setting up UI components: {e}", exc_info=True)
            raise

    def run(self):
        """
        Starts the main UI loop.
        """
        try:
            self.logger.info("Starting UI main loop.")
            self._schedule_updates()
            self.root.mainloop()
        except Exception as e:
            self.logger.error(f"Error running UI main loop: {e}", exc_info=True)
            raise

    def _schedule_updates(self):
        """
        Schedules periodic updates for UI components.
        """
        try:
            self.metrics_display.update_metrics()
            self.notification_system.update_notifications()
            self.root.after(1000, self._schedule_updates)  # Update every second
        except Exception as e:
            self.logger.error(f"Error scheduling UI updates: {e}", exc_info=True)
            raise
