# memory/resource_manager.py

import threading
import logging
from modules.memory.shared_memory import SharedMemory
from modules.utilities.logging_manager import setup_logging


class ResourceManager:
    """
    Manages memory resources, including allocation and deallocation.
    """

    def __init__(self):
        self.logger = setup_logging('ResourceManager')
        self.shared_memory = SharedMemory()
        self.lock = threading.RLock()
        self.resource_limits = {}
        self.resource_usage = {}
        self.logger.info("ResourceManager initialized successfully.")

    def allocate_resource(self, agent_id, key, size):
        """
        Allocates memory resources to an agent.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.
            size (int): The size of the resource to allocate.

        Returns:
            bool: True if allocation is successful, False otherwise.
        """
        try:
            with self.lock:
                limit = self.resource_limits.get(agent_id, float('inf'))
                usage = self.resource_usage.get(agent_id, 0)
                if usage + size <= limit:
                    self.resource_usage[agent_id] = usage + size
                    self.logger.info(f"Allocated {size} units to agent {agent_id}. Total usage: {self.resource_usage[agent_id]}")
                    return True
                else:
                    self.logger.warning(f"Resource limit exceeded for agent {agent_id}. Allocation denied.")
                    return False
        except Exception as e:
            self.logger.error(f"Error allocating resource for agent {agent_id}: {e}", exc_info=True)
            return False

    def deallocate_resource(self, agent_id, key, size):
        """
        Deallocates memory resources from an agent.

        Args:
            agent_id (str): The ID of the agent.
            key (str): The key for the resource.
            size (int): The size of the resource to deallocate.

        Returns:
            bool: True if deallocation is successful, False otherwise.
        """
        try:
            with self.lock:
                usage = self.resource_usage.get(agent_id, 0)
                self.resource_usage[agent_id] = max(0, usage - size)
                self.logger.info(f"Deallocated {size} units from agent {agent_id}. Total usage: {self.resource_usage[agent_id]}")
                return True
        except Exception as e:
            self.logger.error(f"Error deallocating resource for agent {agent_id}: {e}", exc_info=True)
            return False

    def set_resource_limit(self, agent_id, limit):
        """
        Sets a resource limit for an agent.

        Args:
            agent_id (str): The ID of the agent.
            limit (int): The maximum resource limit.

        Returns:
            bool: True if limit is set successfully, False otherwise.
        """
        try:
            with self.lock:
                self.resource_limits[agent_id] = limit
            self.logger.info(f"Resource limit set to {limit} units for agent {agent_id}.")
            return True
        except Exception as e:
            self.logger.error(f"Error setting resource limit for agent {agent_id}: {e}", exc_info=True)
            return False

    def get_resource_usage(self, agent_id):
        """
        Retrieves current resource usage for an agent.

        Args:
            agent_id (str): The ID of the agent.

        Returns:
            int: Current resource usage.
        """
        try:
            with self.lock:
                usage = self.resource_usage.get(agent_id, 0)
            self.logger.debug(f"Resource usage for agent {agent_id}: {usage}")
            return usage
        except Exception as e:
            self.logger.error(f"Error getting resource usage for agent {agent_id}: {e}", exc_info=True)
            return 0
