# shared_memory/shared_data_structures.py

import logging
import threading
from multiprocessing import shared_memory
import struct
from typing import Any, Dict, Optional
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class SharedDataError(Exception):
    """Custom exception for shared data errors."""
    pass

class SharedMemoryManager:
    """
    Manages shared memory segments for inter-process communication.
    Provides thread-safe access to shared data structures.
    """

    def __init__(self, name: str, size: int):
        """
        Initializes a shared memory segment.

        Args:
            name (str): The name of the shared memory segment.
            size (int): The size of the shared memory segment in bytes.

        Raises:
            SharedDataError: If shared memory cannot be created or accessed.
        """
        self.logger = setup_logging('SharedMemoryManager')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.name = name
        self.size = size
        self.shared_mem = None
        self._initialize_shared_memory()

    def _initialize_shared_memory(self):
        """
        Initializes the shared memory segment, creating it if it does not exist.

        Raises:
            SharedDataError: If shared memory cannot be created or accessed.
        """
        try:
            self.logger.debug(f"Attempting to create shared memory '{self.name}' with size {self.size} bytes.")
            self.shared_mem = shared_memory.SharedMemory(name=self.name, create=True, size=self.size)
            self.logger.info(f"Shared memory '{self.name}' created successfully.")
        except FileExistsError:
            self.logger.debug(f"Shared memory '{self.name}' already exists. Attaching to existing segment.")
            try:
                self.shared_mem = shared_memory.SharedMemory(name=self.name)
                self.logger.info(f"Attached to existing shared memory '{self.name}'.")
            except Exception as e:
                self.logger.error(f"Failed to attach to existing shared memory '{self.name}': {e}")
                raise SharedDataError(f"Failed to attach to existing shared memory '{self.name}': {e}")
        except Exception as e:
            self.logger.error(f"Failed to create shared memory '{self.name}': {e}")
            raise SharedDataError(f"Failed to create shared memory '{self.name}': {e}")

    def write_data(self, offset: int, data: bytes) -> None:
        """
        Writes data to the shared memory segment at the specified offset.

        Args:
            offset (int): The byte offset at which to write data.
            data (bytes): The data to write.

        Raises:
            SharedDataError: If writing exceeds shared memory bounds.
        """
        with self.lock:
            try:
                end = offset + len(data)
                if end > self.size:
                    self.logger.error("Attempt to write beyond the shared memory bounds.")
                    raise SharedDataError("Attempt to write beyond the shared memory bounds.")
                self.shared_mem.buf[offset:end] = data
                self.logger.debug(f"Wrote {len(data)} bytes to shared memory '{self.name}' at offset {offset}.")
            except Exception as e:
                self.logger.error(f"Failed to write data to shared memory '{self.name}': {e}")
                raise SharedDataError(f"Failed to write data to shared memory '{self.name}': {e}")

    def read_data(self, offset: int, size: int) -> bytes:
        """
        Reads data from the shared memory segment starting at the specified offset.

        Args:
            offset (int): The byte offset at which to start reading.
            size (int): The number of bytes to read.

        Returns:
            bytes: The data read from shared memory.

        Raises:
            SharedDataError: If reading exceeds shared memory bounds.
        """
        with self.lock:
            try:
                end = offset + size
                if end > self.size:
                    self.logger.error("Attempt to read beyond the shared memory bounds.")
                    raise SharedDataError("Attempt to read beyond the shared memory bounds.")
                data = bytes(self.shared_mem.buf[offset:end])
                self.logger.debug(f"Read {size} bytes from shared memory '{self.name}' at offset {offset}.")
                return data
            except Exception as e:
                self.logger.error(f"Failed to read data from shared memory '{self.name}': {e}")
                raise SharedDataError(f"Failed to read data from shared memory '{self.name}': {e}")

    def close(self) -> None:
        """
        Closes the shared memory segment.

        Raises:
            SharedDataError: If closing fails.
        """
        try:
            self.shared_mem.close()
            self.logger.info(f"Shared memory '{self.name}' closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close shared memory '{self.name}': {e}")
            raise SharedDataError(f"Failed to close shared memory '{self.name}': {e}")

    def unlink(self) -> None:
        """
        Unlinks the shared memory segment, making it available for garbage collection.

        Raises:
            SharedDataError: If unlinking fails.
        """
        try:
            self.shared_mem.unlink()
            self.logger.info(f"Shared memory '{self.name}' unlinked successfully.")
        except FileNotFoundError:
            self.logger.warning(f"Shared memory '{self.name}' does not exist or has already been unlinked.")
        except Exception as e:
            self.logger.error(f"Failed to unlink shared memory '{self.name}': {e}")
            raise SharedDataError(f"Failed to unlink shared memory '{self.name}': {e}")

    def get_size(self) -> int:
        """
        Returns the size of the shared memory segment.

        Returns:
            int: The size in bytes.
        """
        return self.size

    def is_opened(self) -> bool:
        """
        Checks if the shared memory segment is currently opened.

        Returns:
            bool: True if opened, False otherwise.
        """
        try:
            _ = self.shared_mem.name
            return True
        except Exception:
            return False
