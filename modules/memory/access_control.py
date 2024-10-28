# memory/access_control.py

import threading
import logging
from modules.utilities.logging_manager import setup_logging


class AccessControl:
    """
    Manages access permissions to shared memory resources.
    """

    def __init__(self):
        self.logger = setup_logging('AccessControl')
        self.permissions = {}
        self.lock = threading.RLock()
        self.logger.info("AccessControl initialized successfully.")

    def set_permissions(self, agent_id, key, permissions):
        """
        Sets permissions for a specific agent on a resource.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.
            permissions (dict): Permissions dictionary (read, write, delete, lock).

        Returns:
            bool: True if permissions are set successfully, False otherwise.
        """
        try:
            with self.lock:
                self.permissions.setdefault(key, {})[agent_id] = permissions
            self.logger.info(f"Permissions set for agent {agent_id} on key {key}: {permissions}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting permissions for agent {agent_id} on key {key}: {e}", exc_info=True)
            return False

    def check_read_permission(self, agent_id, key):
        """
        Checks if an agent has read permission on a resource.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.

        Returns:
            bool: True if permission is granted, False otherwise.
        """
        return self._check_permission(agent_id, key, 'read')

    def check_write_permission(self, agent_id, key):
        """
        Checks if an agent has write permission on a resource.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.

        Returns:
            bool: True if permission is granted, False otherwise.
        """
        return self._check_permission(agent_id, key, 'write')

    def check_delete_permission(self, agent_id, key):
        """
        Checks if an agent has delete permission on a resource.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.

        Returns:
            bool: True if permission is granted, False otherwise.
        """
        return self._check_permission(agent_id, key, 'delete')

    def check_lock_permission(self, agent_id, key):
        """
        Checks if an agent has lock permission on a resource.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.

        Returns:
            bool: True if permission is granted, False otherwise.
        """
        return self._check_permission(agent_id, key, 'lock')

    def get_accessible_keys(self, agent_id):
        """
        Retrieves a list of resource keys accessible by the agent.

        Args:
            agent_id (str): The ID of the agent.

        Returns:
            list: List of keys accessible by the agent.
        """
        try:
            accessible_keys = []
            with self.lock:
                for key, agents in self.permissions.items():
                    if agent_id in agents:
                        accessible_keys.append(key)
            self.logger.debug(f"Accessible keys for agent {agent_id}: {accessible_keys}")
            return accessible_keys
        except Exception as e:
            self.logger.error(f"Error retrieving accessible keys for agent {agent_id}: {e}", exc_info=True)
            return []

    def _check_permission(self, agent_id, key, permission_type):
        """
        Internal method to check a specific permission.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.
            permission_type (str): The type of permission to check.

        Returns:
            bool: True if permission is granted, False otherwise.
        """
        try:
            with self.lock:
                agent_permissions = self.permissions.get(key, {}).get(agent_id)
            if agent_permissions and agent_permissions.get(permission_type, False):
                self.logger.debug(f"Permission '{permission_type}' granted for agent {agent_id} on key {key}")
                return True
            else:
                self.logger.debug(f"Permission '{permission_type}' denied for agent {agent_id} on key {key}")
                return False
        except Exception as e:
            self.logger.error(f"Error checking permission '{permission_type}' for agent {agent_id} on key {key}: {e}", exc_info=True)
            return False
