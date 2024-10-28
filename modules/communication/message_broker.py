# modules/communication/message_broker.py

import threading
import queue
import logging
from typing import Dict, Any, Optional, List

from modules.utilities.logging_manager import setup_logging


class MessageBrokerError(Exception):
    """Custom exception class for MessageBroker-related errors."""
    pass


class MessageBroker:
    """
    Handles advanced message passing between agents, including individual, broadcast, and group messages.
    Ensures thread-safe operations with robust error handling and detailed logging.
    """

    def __init__(self):
        """
        Initializes the MessageBroker with dedicated queues for agents and groups.
        """
        self.logger = setup_logging('MessageBroker')
        self.agent_queues: Dict[str, queue.Queue] = {}
        self.group_queues: Dict[str, Dict[str, Any]] = {}
        self.broadcast_queue = queue.Queue()
        self.lock = threading.Lock()
        self.logger.info("MessageBroker initialized successfully.")

    def publish_message(self, receiver_id: str, message: Dict[str, Any]) -> None:
        """
        Publishes a message to an individual agent.

        Args:
            receiver_id (str): ID of the receiver agent.
            message (Dict[str, Any]): The message to send.

        Raises:
            MessageBrokerError: If publishing the message fails.
        """
        try:
            with self.lock:
                if receiver_id not in self.agent_queues:
                    self.agent_queues[receiver_id] = queue.Queue()
                    self.logger.debug(f"Queue created for agent {receiver_id}.")
                self.agent_queues[receiver_id].put(message)
                self.logger.debug(f"Message {message['message_id']} published to agent {receiver_id}.")
        except Exception as e:
            self.logger.error(f"Failed to publish message to agent {receiver_id}: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to publish message: {e}")

    def consume_message(self, receiver_id: str, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Consumes a message intended for an individual agent.

        Args:
            receiver_id (str): ID of the receiver agent.
            timeout (Optional[float]): Time to wait for a message in seconds.

        Returns:
            Optional[Dict[str, Any]]: The consumed message, or None if timeout.

        Raises:
            MessageBrokerError: If consuming the message fails.
        """
        try:
            with self.lock:
                if receiver_id not in self.agent_queues:
                    self.agent_queues[receiver_id] = queue.Queue()
                    self.logger.debug(f"Queue created for agent {receiver_id}.")
            message = self.agent_queues[receiver_id].get(timeout=timeout)
            self.logger.debug(f"Message {message['message_id']} consumed by agent {receiver_id}.")
            return message
        except queue.Empty:
            self.logger.debug(f"No message available for agent {receiver_id} within timeout.")
            return None
        except Exception as e:
            self.logger.error(f"Failed to consume message for agent {receiver_id}: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to consume message: {e}")

    def publish_broadcast(self, message: Dict[str, Any]) -> None:
        """
        Publishes a broadcast message to all agents.

        Args:
            message (Dict[str, Any]): The message to broadcast.

        Raises:
            MessageBrokerError: If publishing the broadcast message fails.
        """
        try:
            self.broadcast_queue.put(message)
            self.logger.debug(f"Broadcast message {message['message_id']} published.")
        except Exception as e:
            self.logger.error(f"Failed to publish broadcast message: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to publish broadcast message: {e}")

    def consume_broadcast(self, receiver_id: str) -> Optional[Dict[str, Any]]:
        """
        Consumes a broadcast message for a specific agent.

        Args:
            receiver_id (str): ID of the receiver agent.

        Returns:
            Optional[Dict[str, Any]]: The broadcast message, or None if none available.

        Raises:
            MessageBrokerError: If consuming the broadcast message fails.
        """
        try:
            message = self.broadcast_queue.get_nowait()
            self.logger.debug(f"Broadcast message {message['message_id']} consumed by agent {receiver_id}.")
            return message
        except queue.Empty:
            self.logger.debug(f"No broadcast message available for agent {receiver_id}.")
            return None
        except Exception as e:
            self.logger.error(f"Failed to consume broadcast message for agent {receiver_id}: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to consume broadcast message: {e}")

    def create_group(self, group_id: str, member_ids: List[str]) -> None:
        """
        Creates a group with the specified members.

        Args:
            group_id (str): ID of the group.
            member_ids (List[str]): List of agent IDs in the group.

        Raises:
            MessageBrokerError: If creating the group fails.
        """
        try:
            with self.lock:
                if group_id in self.group_queues:
                    self.logger.warning(f"Group {group_id} already exists.")
                    return
                self.group_queues[group_id] = {
                    'queue': queue.Queue(),
                    'members': set(member_ids)
                }
                self.logger.info(f"Group {group_id} created with members: {member_ids}.")
        except Exception as e:
            self.logger.error(f"Failed to create group {group_id}: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to create group: {e}")

    def publish_group_message(self, group_id: str, message: Dict[str, Any]) -> None:
        """
        Publishes a message to a specific group.

        Args:
            group_id (str): ID of the group.
            message (Dict[str, Any]): The message to send.

        Raises:
            MessageBrokerError: If publishing the group message fails.
        """
        try:
            with self.lock:
                if group_id not in self.group_queues:
                    self.logger.warning(f"Group {group_id} does not exist.")
                    return
                self.group_queues[group_id]['queue'].put(message)
                self.logger.debug(f"Message {message['message_id']} published to group {group_id}.")
        except Exception as e:
            self.logger.error(f"Failed to publish message to group {group_id}: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to publish group message: {e}")

    def consume_group_message(self, group_id: str, receiver_id: str) -> Optional[Dict[str, Any]]:
        """
        Consumes a group message for a specific agent.

        Args:
            group_id (str): ID of the group.
            receiver_id (str): ID of the receiver agent.

        Returns:
            Optional[Dict[str, Any]]: The group message, or None if none available.

        Raises:
            MessageBrokerError: If consuming the group message fails.
        """
        try:
            with self.lock:
                if group_id not in self.group_queues:
                    self.logger.warning(f"Group {group_id} does not exist.")
                    return None
                if receiver_id not in self.group_queues[group_id]['members']:
                    self.logger.warning(f"Agent {receiver_id} is not a member of group {group_id}.")
                    return None
            message = self.group_queues[group_id]['queue'].get_nowait()
            self.logger.debug(f"Group message {message['message_id']} consumed by agent {receiver_id} from group {group_id}.")
            return message
        except queue.Empty:
            self.logger.debug(f"No group message available for agent {receiver_id} in group {group_id}.")
            return None
        except Exception as e:
            self.logger.error(f"Failed to consume group message for agent {receiver_id} in group {group_id}: {e}", exc_info=True)
            raise MessageBrokerError(f"Failed to consume group message: {e}")
