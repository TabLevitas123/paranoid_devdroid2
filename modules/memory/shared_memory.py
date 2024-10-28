# memory/shared_memory.py

import threading
import logging
from modules.security.encryption_manager import EncryptionManager
from modules.memory.access_control import AccessControl
from modules.memory.synchronization import Synchronization
from modules.utilities.logging_manager import setup_logging


class SharedMemory:
    """
    Manages shared memory storage for inter-agent communication and data sharing.
    """

    def __init__(self):
        self.logger = setup_logging('SharedMemory')
        self.data_store = {}
        self.lock = threading.RLock()
        self.access_control = AccessControl()
        self.synchronization = Synchronization()
        self.encryption_manager = EncryptionManager()
        self.logger.info("SharedMemory initialized successfully.")

    def read_data(self, key, agent_id):
        """
        Reads data from shared memory if access is permitted.

        Args:
            key (str): The key for the data.
            agent_id (str): The ID of the requesting agent.

        Returns:
            any: The decrypted data if access is granted, else None.
        """
        try:
            self.logger.debug(f"Agent {agent_id} requests to read key: {key}")
            if self.access_control.check_read_permission(agent_id, key):
                with self.lock:
                    encrypted_data = self.data_store.get(key)
                if encrypted_data is not None:
                    data = self.encryption_manager.decrypt_data(encrypted_data)
                    self.logger.info(f"Data read successfully by agent {agent_id} for key: {key}")
                    return data
                else:
                    self.logger.warning(f"No data found for key: {key}")
                    return None
            else:
                self.logger.warning(f"Access denied for agent {agent_id} to read key: {key}")
                return None
        except Exception as e:
            self.logger.error(f"Error reading data for key {key}: {e}", exc_info=True)
            return None

    def write_data(self, key, data, agent_id):
        """
        Writes data to shared memory if access is permitted.

        Args:
            key (str): The key for the data.
            data (any): The data to store.
            agent_id (str): The ID of the requesting agent.

        Returns:
            bool: True if write is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Agent {agent_id} requests to write key: {key}")
            if self.access_control.check_write_permission(agent_id, key):
                with self.lock:
                    encrypted_data = self.encryption_manager.encrypt_data(data)
                    self.data_store[key] = encrypted_data
                self.logger.info(f"Data written successfully by agent {agent_id} for key: {key}")
                return True
            else:
                self.logger.warning(f"Access denied for agent {agent_id} to write key: {key}")
                return False
        except Exception as e:
            self.logger.error(f"Error writing data for key {key}: {e}", exc_info=True)
            return False

    def delete_data(self, key, agent_id):
        """
        Deletes data from shared memory if access is permitted.

        Args:
            key (str): The key for the data.
            agent_id (str): The ID of the requesting agent.

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Agent {agent_id} requests to delete key: {key}")
            if self.access_control.check_delete_permission(agent_id, key):
                with self.lock:
                    if key in self.data_store:
                        del self.data_store[key]
                        self.logger.info(f"Data deleted successfully by agent {agent_id} for key: {key}")
                        return True
                    else:
                        self.logger.warning(f"No data found for key: {key}")
                        return False
            else:
                self.logger.warning(f"Access denied for agent {agent_id} to delete key: {key}")
                return False
        except Exception as e:
            self.logger.error(f"Error deleting data for key {key}: {e}", exc_info=True)
            return False

    def list_keys(self, agent_id):
        """
        Lists all keys accessible to the agent.

        Args:
            agent_id (str): The ID of the requesting agent.

        Returns:
            list: A list of keys accessible to the agent.
        """
        try:
            self.logger.debug(f"Agent {agent_id} requests to list keys.")
            accessible_keys = self.access_control.get_accessible_keys(agent_id)
            self.logger.info(f"Agent {agent_id} has access to keys: {accessible_keys}")
            return accessible_keys
        except Exception as e:
            self.logger.error(f"Error listing keys for agent {agent_id}: {e}", exc_info=True)
            return []

    def lock_resource(self, key, agent_id):
        """
        Locks a resource for exclusive access.

        Args:
            key (str): The key for the resource.
            agent_id (str): The ID of the requesting agent.

        Returns:
            bool: True if lock is acquired, False otherwise.
        """
        try:
            self.logger.debug(f"Agent {agent_id} requests to lock key: {key}")
            if self.access_control.check_lock_permission(agent_id, key):
                result = self.synchronization.acquire_lock(key, agent_id)
                if result:
                    self.logger.info(f"Lock acquired by agent {agent_id} for key: {key}")
                else:
                    self.logger.warning(f"Lock acquisition failed for agent {agent_id} on key: {key}")
                return result
            else:
                self.logger.warning(f"Access denied for agent {agent_id} to lock key: {key}")
                return False
        except Exception as e:
            self.logger.error(f"Error locking resource {key}: {e}", exc_info=True)
            return False

    def unlock_resource(self, key, agent_id):
        """
        Releases a previously acquired lock on a resource.

        Args:
            key (str): The key for the resource.
            agent_id (str): The ID of the requesting agent.

        Returns:
            bool: True if lock is released, False otherwise.
        """
        try:
            self.logger.debug(f"Agent {agent_id} requests to unlock key: {key}")
            result = self.synchronization.release_lock(key, agent_id)
            if result:
                self.logger.info(f"Lock released by agent {agent_id} for key: {key}")
            else:
                self.logger.warning(f"Lock release failed for agent {agent_id} on key: {key}")
            return result
        except Exception as e:
            self.logger.error(f"Error unlocking resource {key}: {e}", exc_info=True)
            return False
