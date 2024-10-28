# notification_system.py

import logging
import threading
import tkinter as tk
from tkinter import ttk
from modules.utilities.logging_manager import setup_logging
from modules.communication.communication_module import CommunicationModule
from modules.security.encryption_manager import EncryptionManager
from modules.utilities.event_dispatcher import EventDispatcher
from modules.user_interface.alert_dialog import AlertDialog


class NotificationSystem:
    """
    Manages notifications and displays them in the user interface.
    """

    def __init__(self, parent):
        self.logger = setup_logging('NotificationSystem')
        self.parent = parent
        self.communication_module = CommunicationModule()
        self.encryption_manager = EncryptionManager()
        self.event_dispatcher = EventDispatcher()
        self.notifications_frame = None
        self.notifications_listbox = None
        self.notifications = []
        self.lock = threading.Lock()
        self.logger.info("NotificationSystem initialized successfully.")
        self._register_event_handlers()

    def _register_event_handlers(self):
        """
        Registers event handlers for notifications.
        """
        try:
            self.logger.debug("Registering event handlers for notifications.")
            self.event_dispatcher.register_handler('new_notification', self._handle_new_notification)
            self.logger.info("Event handlers registered successfully.")
        except Exception as e:
            self.logger.error(f"Error registering event handlers: {e}", exc_info=True)
            raise

    def create_widgets(self, parent_frame):
        """
        Creates the widgets for displaying notifications.
        """
        try:
            self.logger.debug("Creating notification system widgets.")
            self.notifications_frame = ttk.LabelFrame(parent_frame, text="Notifications", padding="10")
            self.notifications_frame.pack(fill=tk.BOTH, expand=True, side=tk.RIGHT)

            self.notifications_listbox = tk.Listbox(self.notifications_frame, height=15)
            self.notifications_listbox.pack(fill=tk.BOTH, expand=True)

            scrollbar = ttk.Scrollbar(self.notifications_frame, orient=tk.VERTICAL, command=self.notifications_listbox.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.notifications_listbox.config(yscrollcommand=scrollbar.set)

            # Bind double-click event to open notification details
            self.notifications_listbox.bind('<Double-1>', self._on_notification_double_click)

            self.logger.info("Notification system widgets created successfully.")
        except Exception as e:
            self.logger.error(f"Error creating notification system widgets: {e}", exc_info=True)
            raise

    def _on_notification_double_click(self, event):
        """
        Handles double-click events on the notification list.
        """
        try:
            index = self.notifications_listbox.curselection()
            if index:
                notification = self.notifications[index[0]]
                self.logger.debug(f"Notification double-clicked: {notification}")
                self._show_notification_details(notification)
        except Exception as e:
            self.logger.error(f"Error handling notification double-click: {e}", exc_info=True)
            raise

    def _show_notification_details(self, notification):
        """
        Displays the details of a notification in a dialog.
        """
        try:
            alert_dialog = AlertDialog(self.parent, notification)
            alert_dialog.show()
        except Exception as e:
            self.logger.error(f"Error showing notification details: {e}", exc_info=True)
            raise

    def update_notifications(self):
        """
        Updates the notifications display.
        """
        try:
            self.logger.debug("Updating notifications.")
            # Fetch new notifications from communication_module
            new_notifications = self.communication_module.get_new_notifications()

            with self.lock:
                for notification in new_notifications:
                    decrypted_notification = self._decrypt_notification(notification)
                    if decrypted_notification:
                        self.notifications.append(decrypted_notification)
                        self.notifications_listbox.insert(tk.END, decrypted_notification['title'])

                        # Auto-scroll to the end
                        self.notifications_listbox.yview_moveto(1.0)

            self.logger.info("Notifications updated successfully.")
        except Exception as e:
            self.logger.error(f"Error updating notifications: {e}", exc_info=True)
            raise

    def _decrypt_notification(self, notification):
        """
        Decrypts an encrypted notification.
        """
        try:
            encrypted_content = notification.get('content')
            decrypted_content = self.encryption_manager.decrypt_data(encrypted_content)
            notification_data = self._deserialize_notification(decrypted_content)
            self.logger.debug(f"Notification decrypted: {notification_data}")
            return notification_data
        except Exception as e:
            self.logger.error(f"Error decrypting notification: {e}", exc_info=True)
            return None

    def _deserialize_notification(self, data_bytes):
        """
        Deserializes notification data from bytes.
        """
        try:
            import pickle
            notification_data = pickle.loads(data_bytes)
            return notification_data
        except Exception as e:
            self.logger.error(f"Error deserializing notification: {e}", exc_info=True)
            return None

    def _handle_new_notification(self, notification):
        """
        Handles a new notification event.
        """
        try:
            decrypted_notification = self._decrypt_notification(notification)
            if decrypted_notification:
                with self.lock:
                    self.notifications.append(decrypted_notification)
                    self.notifications_listbox.insert(tk.END, decrypted_notification['title'])
                    self.notifications_listbox.yview_moveto(1.0)
                self.logger.info(f"New notification received: {decrypted_notification['title']}")
        except Exception as e:
            self.logger.error(f"Error handling new notification: {e}", exc_info=True)
            raise

    def send_notification(self, recipient_id, title, message):
        """
        Sends a notification to another agent.

        Args:
            recipient_id (str): The ID of the recipient agent.
            title (str): The title of the notification.
            message (str): The message content.
        """
        try:
            self.logger.debug(f"Sending notification to {recipient_id}.")
            notification = {
                'title': title,
                'message': message,
                'sender_id': self.communication_module.agent_id,
                'timestamp': self._get_current_timestamp()
            }
            serialized_notification = self._serialize_notification(notification)
            encrypted_notification = self.encryption_manager.encrypt_data(serialized_notification)
            self.communication_module.send_message(
                sender_id=self.communication_module.agent_id,
                receiver_id=recipient_id,
                message_type='notification',
                content=encrypted_notification
            )
            self.logger.info(f"Notification sent to {recipient_id}: {title}")
        except Exception as e:
            self.logger.error(f"Error sending notification to {recipient_id}: {e}", exc_info=True)
            raise

    def _serialize_notification(self, notification_data):
        """
        Serializes notification data into bytes.

        Args:
            notification_data (dict): The notification data to serialize.

        Returns:
            bytes: The serialized notification data.
        """
        try:
            import pickle
            serialized_data = pickle.dumps(notification_data)
            self.logger.debug("Notification data serialized successfully.")
            return serialized_data
        except Exception as e:
            self.logger.error(f"Error serializing notification data: {e}", exc_info=True)
            raise

    def _get_current_timestamp(self):
        """
        Returns the current timestamp.

        Returns:
            str: The current timestamp in ISO format.
        """
        try:
            from datetime import datetime
            timestamp = datetime.utcnow().isoformat()
            return timestamp
        except Exception as e:
            self.logger.error(f"Error getting current timestamp: {e}", exc_info=True)
            return ''

    def mark_notification_as_read(self, notification_index):
        """
        Marks a notification as read.

        Args:
            notification_index (int): The index of the notification in the list.
        """
        try:
            with self.lock:
                if 0 <= notification_index < len(self.notifications):
                    notification = self.notifications[notification_index]
                    notification['read'] = True
                    self.logger.info(f"Notification marked as read: {notification['title']}")
                else:
                    self.logger.warning(f"Invalid notification index: {notification_index}")
        except Exception as e:
            self.logger.error(f"Error marking notification as read: {e}", exc_info=True)
            raise

    def delete_notification(self, notification_index):
        """
        Deletes a notification from the list.

        Args:
            notification_index (int): The index of the notification to delete.
        """
        try:
            with self.lock:
                if 0 <= notification_index < len(self.notifications):
                    notification = self.notifications.pop(notification_index)
                    self.notifications_listbox.delete(notification_index)
                    self.logger.info(f"Notification deleted: {notification['title']}")
                else:
                    self.logger.warning(f"Invalid notification index: {notification_index}")
        except Exception as e:
            self.logger.error(f"Error deleting notification: {e}", exc_info=True)
            raise

    def clear_all_notifications(self):
        """
        Clears all notifications from the list.
        """
        try:
            with self.lock:
                self.notifications.clear()
                self.notifications_listbox.delete(0, tk.END)
            self.logger.info("All notifications cleared.")
        except Exception as e:
            self.logger.error(f"Error clearing notifications: {e}", exc_info=True)
            raise
