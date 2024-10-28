# modules/communication/advanced_communication.py

import threading
import logging
from modules.communication.communication_module import CommunicationModule
from modules.security.encryption_manager import EncryptionManager
from modules.utilities.logging_manager import setup_logging


class AdvancedCommunication(CommunicationModule):
    """
    Extends CommunicationModule with advanced communication features.
    """

    def __init__(self):
        super().__init__()
        self.logger = setup_logging('AdvancedCommunication')
        self.group_listeners = {}
        self.group_lock = threading.Lock()
        self.logger.info("AdvancedCommunication initialized.")

    def send_broadcast(self, sender_id, message_type, content):
        """
        Sends a broadcast message to all agents.

        Args:
            sender_id (str): ID of the sender agent.
            message_type (str): Type of the message.
            content (any): Content of the message.
        """
        try:
            self.logger.debug(f"{sender_id} broadcasting message to all agents.")
            encrypted_content = self.encryption_manager.encrypt_data(content)
            message = {
                'sender_id': sender_id,
                'receiver_id': 'broadcast',
                'message_type': message_type,
                'content': encrypted_content,
            }
            self.message_broker.publish_broadcast(message)
            self.logger.info(f"{sender_id} broadcasted message.")
        except Exception as e:
            self.logger.error(f"Error broadcasting message from {sender_id}: {e}", exc_info=True)

    def create_group(self, group_id, member_ids):
        """
        Creates a communication group.

        Args:
            group_id (str): ID of the group.
            member_ids (list): List of agent IDs to include in the group.
        """
        try:
            with self.group_lock:
                self.message_broker.create_group(group_id, member_ids)
                self.logger.info(f"Group {group_id} created with members {member_ids}.")
        except Exception as e:
            self.logger.error(f"Error creating group {group_id}: {e}", exc_info=True)

    def send_group_message(self, sender_id, group_id, message_type, content):
        """
        Sends a message to a group.

        Args:
            sender_id (str): ID of the sender agent.
            group_id (str): ID of the group.
            message_type (str): Type of the message.
            content (any): Content of the message.
        """
        try:
            self.logger.debug(f"{sender_id} sending message to group {group_id}.")
            encrypted_content = self.encryption_manager.encrypt_data(content)
            message = {
                'sender_id': sender_id,
                'receiver_id': group_id,
                'message_type': message_type,
                'content': encrypted_content,
            }
            self.message_broker.publish_group_message(group_id, message)
            self.logger.info(f"Message sent from {sender_id} to group {group_id}.")
        except Exception as e:
            self.logger.error(f"Error sending message from {sender_id} to group {group_id}: {e}", exc_info=True)

    def register_group_listener(self, group_id, receiver_id, callback):
        """
        Registers a listener for group messages.

        Args:
            group_id (str): ID of the group.
            receiver_id (str): ID of the receiver agent.
            callback (function): Callback function to handle received messages.
        """
        try:
            with self.group_lock:
                if group_id not in self.group_listeners:
                    self.group_listeners[group_id] = {}
                if receiver_id not in self.group_listeners[group_id]:
                    self.group_listeners[group_id][receiver_id] = callback
                    threading.Thread(target=self._group_listener_thread, args=(group_id, receiver_id), daemon=True).start()
                    self.logger.info(f"Group listener registered for {receiver_id} in group {group_id}.")
                else:
                    self.logger.warning(f"Group listener already registered for {receiver_id} in group {group_id}.")
        except Exception as e:
            self.logger.error(f"Error registering group listener for {receiver_id} in group {group_id}: {e}", exc_info=True)

    def _group_listener_thread(self, group_id, receiver_id):
        """
        Internal thread function for listening to group messages.

        Args:
            group_id (str): ID of the group.
            receiver_id (str): ID of the receiver agent.
        """
        self.logger.debug(f"Group listener thread started for {receiver_id} in group {group_id}.")
        while True:
            try:
                message = self.message_broker.consume_group_message(group_id, receiver_id)
                if message:
                    decrypted_content = self.encryption_manager.decrypt_data(message['content'])
                    message['content'] = decrypted_content
                    callback = self.group_listeners[group_id].get(receiver_id)
                    if callback:
                        callback(message)
            except Exception as e:
                self.logger.error(f"Error in group listener thread for {receiver_id} in group {group_id}: {e}", exc_info=True)
                break

    def unregister_group_listener(self, group_id, receiver_id):
        """
        Unregisters a listener for group messages.

        Args:
            group_id (str): ID of the group.
            receiver_id (str): ID of the receiver agent.
        """
        try:
            with self.group_lock:
                if group_id in self.group_listeners and receiver_id in self.group_listeners[group_id]:
                    del self.group_listeners[group_id][receiver_id]
                    self.logger.info(f"Group listener unregistered for {receiver_id} in group {group_id}.")
                else:
                    self.logger.warning(f"No group listener registered for {receiver_id} in group {group_id} to unregister.")
        except Exception as e:
            self.logger.error(f"Error unregistering group listener for {receiver_id} in group {group_id}: {e}", exc_info=True)
