# memory/synchronization.py

import threading
import logging
from modules.utilities.logging_manager import setup_logging


class Synchronization:
    """
    Provides synchronization mechanisms for shared resources.
    """

    def __init__(self):
        self.logger = setup_logging('Synchronization')
        self.locks = {}
        self.locks_lock = threading.RLock()
        self.logger.info("Synchronization initialized successfully.")

    def acquire_lock(self, key, agent_id, timeout=None):
        """
        Acquires a lock on a resource for exclusive access.

        Args:
            key (str): The key for the resource.
            agent_id (str): The ID of the agent requesting the lock.
            timeout (float, optional): Time to wait for the lock.

        Returns:
            bool: True if the lock is acquired, False otherwise.
        """
        try:
            self.logger.debug(f"Agent {agent_id} attempting to acquire lock on key: {key}")
            with self.locks_lock:
                lock = self.locks.setdefault(key, threading.Lock())
            result = lock.acquire(timeout=timeout)
            if result:
                self.logger.info(f"Lock acquired by agent {agent_id} on key: {key}")
            else:
                self.logger.warning(f"Agent {agent_id} failed to acquire lock on key: {key}")
            return result
        except Exception as e:
            self.logger.error(f"Error acquiring lock on key {key} by agent {agent_id}: {e}", exc_info=True)
            return False

    def release_lock(self, key, agent_id):
        """
        Releases a lock on a resource.

        Args:
            key (str): The key for the resource.
            agent_id (str): The ID of the agent releasing the lock.

        Returns:
            bool: True if the lock is released, False otherwise.
        """
        try:
            self.logger.debug(f"Agent {agent_id} attempting to release lock on key: {key}")
            with self.locks_lock:
                lock = self.locks.get(key)
            if lock and lock.locked():
                lock.release()
                self.logger.info(f"Lock released by agent {agent_id} on key: {key}")
                return True
            else:
                self.logger.warning(f"No lock to release for agent {agent_id} on key: {key}")
                return False
        except Exception as e:
            self.logger.error(f"Error releasing lock on key {key} by agent {agent_id}: {e}", exc_info=True)
            return False

    def is_locked(self, key):
        """
        Checks if a resource is currently locked.

        Args:
            key (str): The key for the resource.

        Returns:
            bool: True if the resource is locked, False otherwise.
        """
        try:
            with self.locks_lock:
                lock = self.locks.get(key)
            locked = lock.locked() if lock else False
            self.logger.debug(f"Resource {key} locked status: {locked}")
            return locked
        except Exception as e:
            self.logger.error(f"Error checking lock status for key {key}: {e}", exc_info=True)
            return False
