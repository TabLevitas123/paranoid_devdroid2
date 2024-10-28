# modules/communication/communication_module.py

import threading
import json
import os
import uuid
import time
from typing import Optional, Dict, Any, Callable

from modules.security.encryption_manager import EncryptionManager
from modules.utilities.logging_manager import setup_logging
from modules.communication.message_broker import MessageBroker


class CommunicationModuleError(Exception):
    """Custom exception class for CommunicationModule-related errors."""
    pass


class CommunicationModule:
    """
    Handles advanced communication functionalities between agents, including sending,
    receiving, and asynchronously handling messages with robust error handling and security.
    """

    def __init__(self):
        """
        Initializes the CommunicationModule with encryption, message broker, and logging.
        """
        self.logger = setup_logging('CommunicationModule')
        self.encryption_manager = EncryptionManager()
        self.message_broker = MessageBroker()
        self.listeners: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self.lock = threading.Lock()
        self.running = True
        self.listener_threads: Dict[str, threading.Thread] = {}
        self.logger.info("CommunicationModule initialized successfully.")

    def send_message(self, sender_id: str, receiver_id: str, message_type: str, content: Any) -> None:
        """
        Sends an encrypted message to a receiver via the message broker.

        Args:
            sender_id (str): ID of the sender agent.
            receiver_id (str): ID of the receiver agent.
            message_type (str): Type of the message.
            content (Any): Content of the message.

        Raises:
            CommunicationModuleError: If sending the message fails.
        """
        try:
            self.logger.debug(f"Preparing to send message from {sender_id} to {receiver_id}.")
            encrypted_content = self.encryption_manager.encrypt_data(content)
            message = {
                'message_id': str(uuid.uuid4()),
                'timestamp': time.time(),
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'message_type': message_type,
                'content': encrypted_content,
            }
            self.message_broker.publish_message(receiver_id, message)
            self.logger.info(f"Message {message['message_id']} sent from {sender_id} to {receiver_id}.")
        except Exception as e:
            self.logger.error(f"Failed to send message from {sender_id} to {receiver_id}: {e}", exc_info=True)
            raise CommunicationModuleError(f"Failed to send message: {e}")

    def receive_message(self, receiver_id: str, message_type_filter: Optional[str] = None, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Receives a message intended for the receiver.

        Args:
            receiver_id (str): ID of the receiver agent.
            message_type_filter (Optional[str]): Filter messages by type.
            timeout (Optional[float]): Time to wait for a message in seconds.

        Returns:
            Optional[Dict[str, Any]]: The received message, or None if timeout or no message.

        Raises:
            CommunicationModuleError: If receiving the message fails.
        """
        try:
            self.logger.debug(f"{receiver_id} is waiting to receive a message.")
            message = self.message_broker.consume_message(receiver_id, timeout)
            if message:
                decrypted_content = self.encryption_manager.decrypt_data(message['content'])
                message['content'] = decrypted_content
                if message_type_filter and message['message_type'] != message_type_filter:
                    self.logger.debug(f"Message type {message['message_type']} does not match filter {message_type_filter}. Ignoring message.")
                    return None
                self.logger.info(f"{receiver_id} received message {message['message_id']} from {message['sender_id']}.")
                return message
            else:
                self.logger.debug(f"No message received for {receiver_id} within timeout.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to receive message for {receiver_id}: {e}", exc_info=True)
            raise CommunicationModuleError(f"Failed to receive message: {e}")

    def register_listener(self, receiver_id: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Registers a listener callback for asynchronous message handling.

        Args:
            receiver_id (str): ID of the receiver agent.
            callback (Callable[[Dict[str, Any]], None]): Callback function to handle received messages.

        Raises:
            CommunicationModuleError: If registering the listener fails.
        """
        with self.lock:
            if receiver_id in self.listeners:
                self.logger.warning(f"Listener already registered for {receiver_id}.")
                return
            self.listeners[receiver_id] = callback
            listener_thread = threading.Thread(target=self._listener_thread, args=(receiver_id,), daemon=True)
            self.listener_threads[receiver_id] = listener_thread
            listener_thread.start()
            self.logger.info(f"Listener registered and thread started for {receiver_id}.")

    def unregister_listener(self, receiver_id: str) -> None:
        """
        Unregisters a listener callback.

        Args:
            receiver_id (str): ID of the receiver agent.

        Raises:
            CommunicationModuleError: If unregistering the listener fails.
        """
        with self.lock:
            if receiver_id not in self.listeners:
                self.logger.warning(f"No listener registered for {receiver_id} to unregister.")
                return
            del self.listeners[receiver_id]
            self.logger.info(f"Listener unregistered for {receiver_id}.")

    def _listener_thread(self, receiver_id: str) -> None:
        """
        Internal thread function for listening to messages asynchronously.

        Args:
            receiver_id (str): ID of the receiver agent.
        """
        self.logger.debug(f"Listener thread started for {receiver_id}.")
        while self.running and receiver_id in self.listeners:
            try:
                message = self.receive_message(receiver_id, timeout=1.0)
                if message and self.listeners.get(receiver_id):
                    self.logger.debug(f"Dispatching message {message['message_id']} to listener for {receiver_id}.")
                    self.listeners[receiver_id](message)
            except CommunicationModuleError as e:
                self.logger.error(f"Error in listener thread for {receiver_id}: {e}", exc_info=True)
                break
            except Exception as e:
                self.logger.critical(f"Unexpected error in listener thread for {receiver_id}: {e}", exc_info=True)
                break
        self.logger.debug(f"Listener thread terminating for {receiver_id}.")

    def broadcast_message(self, sender_id: str, message_type: str, content: Any) -> None:
        """
        Sends an encrypted broadcast message to all agents via the message broker.

        Args:
            sender_id (str): ID of the sender agent.
            message_type (str): Type of the message.
            content (Any): Content of the message.

        Raises:
            CommunicationModuleError: If sending the broadcast message fails.
        """
        try:
            self.logger.debug(f"Preparing to send broadcast message from {sender_id}.")
            encrypted_content = self.encryption_manager.encrypt_data(content)
            message = {
                'message_id': str(uuid.uuid4()),
                'timestamp': time.time(),
                'sender_id': sender_id,
                'receiver_id': 'ALL',
                'message_type': message_type,
                'content': encrypted_content,
            }
            self.message_broker.publish_broadcast(message)
            self.logger.info(f"Broadcast message {message['message_id']} sent from {sender_id}.")
        except Exception as e:
            self.logger.error(f"Failed to send broadcast message from {sender_id}: {e}", exc_info=True)
            raise CommunicationModuleError(f"Failed to send broadcast message: {e}")

    def shutdown(self) -> None:
        """
        Shuts down the CommunicationModule gracefully by stopping listener threads.

        Raises:
            CommunicationModuleError: If shutdown fails.
        """
        self.logger.info("Shutting down CommunicationModule.")
        self.running = False
        with self.lock:
            for receiver_id in list(self.listeners.keys()):
                self.unregister_listener(receiver_id)
        self.logger.info("CommunicationModule shutdown completed successfully.")
