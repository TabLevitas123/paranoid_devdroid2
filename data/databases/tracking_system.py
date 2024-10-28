# databases/tracking_system.py

import logging
import threading
from typing import Any, Dict, List, Optional
import json

from sqlalchemy import Column, String, Integer, Text, create_engine, exists
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.sqlite_db import SQLiteDatabase
from databases.vector_db import VectorDatabase
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase


Base = declarative_base()


class PineconeIDMapping(Base):
    """
    SQLAlchemy ORM model for Pinecone ID mappings.
    """
    __tablename__ = 'pinecone_id_mappings'

    external_id = Column(String, primary_key=True, nullable=False)
    pinecone_id = Column(String, unique=True, nullable=False)
    metadata = Column(Text, nullable=True)


class PineconeTrackingSystemError(Exception):
    """Custom exception for PineconeTrackingSystem-related errors."""
    pass


class PineconeTrackingSystem:
    """
    Manages the tracking of Pinecone vector IDs, ensuring synchronization between external IDs and Pinecone IDs.
    Integrates seamlessly with VectorDatabase and SharedMemoryManager to support RAG in near-real-time.
    Implements singleton pattern to ensure only one instance exists.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """
        Implements the singleton pattern.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PineconeTrackingSystem, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the PineconeTrackingSystem with necessary configurations, authentication, and integrations.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        # Setup logging
        self.logger = setup_logging('PineconeTrackingSystem')

        # Load configurations
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()

        # Initialize SQLite Database for tracking
        try:
            self.sqlite_db = SQLiteDatabase()
            self.logger.info("Connected to SQLiteDatabase successfully for Pinecone ID tracking.")
        except Exception as e:
            self.logger.error(f"Failed to connect to SQLiteDatabase: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to connect to SQLiteDatabase: {e}")

        # Initialize VectorDatabase and SharedMemoryManager
        try:
            self.vector_db = VectorDatabase()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024*1024*200)  # 200 MB
            self.time_series_db = TimeSeriesDatabase()
            self.logger.info("Integrated with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with VectorDatabase, SharedMemoryManager, or TimeSeriesDatabase: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to integrate with VectorDatabase, SharedMemoryManager, or TimeSeriesDatabase: {e}")

        # Initialize the tracking table in SQLite
        try:
            self.sqlite_db.create_pinecone_id_mappings_table()
            self.logger.info("Ensured Pinecone ID mappings table exists in SQLiteDatabase.")
        except Exception as e:
            self.logger.error(f"Failed to create Pinecone ID mappings table: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to create Pinecone ID mappings table: {e}")

        # Start background thread for periodic synchronization
        try:
            threading.Thread(target=self._periodic_synchronization, daemon=True).start()
            self.logger.info("Started background thread for periodic synchronization.")
        except Exception as e:
            self.logger.error(f"Failed to start background synchronization thread: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to start background synchronization thread: {e}")

        self._initialized = True

    # Tracking Methods

    def add_mapping(self, external_id: str, pinecone_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Adds a new mapping between an external ID and a Pinecone ID.
        
        Args:
            external_id (str): The external unique identifier (e.g., 'user_1').
            pinecone_id (str): The Pinecone-assigned unique identifier.
            metadata (Dict[str, Any]): Additional metadata associated with the vector.
        
        Returns:
            bool: True if the mapping is added successfully, False otherwise.
        """
        try:
            # Check if external_id already exists
            if self.sqlite_db.check_mapping_exists(external_id=external_id):
                self.logger.warning(f"Mapping for external ID '{external_id}' already exists.")
                return False

            # Check if pinecone_id is already mapped
            if self.sqlite_db.check_pinecone_id_exists(pinecone_id=pinecone_id):
                self.logger.warning(f"Pinecone ID '{pinecone_id}' is already mapped to another external ID.")
                return False

            # Insert the new mapping
            self.sqlite_db.insert_pinecone_id_mapping(external_id=external_id, pinecone_id=pinecone_id, metadata=json.dumps(metadata))
            self.logger.info(f"Added mapping: External ID '{external_id}' <-> Pinecone ID '{pinecone_id}'.")

            # Update shared memory
            self.shared_memory.cache_pinecone_mapping(external_id=external_id, pinecone_id=pinecone_id, metadata=metadata)
            self.logger.debug(f"Cached mapping in SharedMemoryManager for External ID '{external_id}'.")

            # Log the event
            self.time_series_db.log_event(event_type='pinecone_mapping_added', details={'external_id': external_id, 'pinecone_id': pinecone_id, 'metadata': metadata})

            return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding mapping for External ID '{external_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while adding mapping for External ID '{external_id}': {e}", exc_info=True)
            return False

    def remove_mapping(self, external_id: str) -> bool:
        """
        Removes an existing mapping based on the external ID.
        
        Args:
            external_id (str): The external unique identifier to remove.
        
        Returns:
            bool: True if the mapping is removed successfully, False otherwise.
        """
        try:
            # Retrieve the mapping
            mapping = self.sqlite_db.get_mapping_by_external_id(external_id=external_id)
            if not mapping:
                self.logger.warning(f"No mapping found for External ID '{external_id}'.")
                return False

            pinecone_id = mapping.pinecone_id

            # Delete the mapping
            self.sqlite_db.delete_pinecone_id_mapping(external_id=external_id)
            self.logger.info(f"Removed mapping for External ID '{external_id}' and Pinecone ID '{pinecone_id}'.")

            # Remove from shared memory
            self.shared_memory.remove_pinecone_mapping(external_id=external_id)
            self.logger.debug(f"Removed mapping from SharedMemoryManager for External ID '{external_id}'.")

            # Log the event
            self.time_series_db.log_event(event_type='pinecone_mapping_removed', details={'external_id': external_id, 'pinecone_id': pinecone_id})

            return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while removing mapping for External ID '{external_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while removing mapping for External ID '{external_id}': {e}", exc_info=True)
            return False

    def get_pinecone_id(self, external_id: str) -> Optional[str]:
        """
        Retrieves the Pinecone ID associated with a given external ID.
        
        Args:
            external_id (str): The external unique identifier.
        
        Returns:
            Optional[str]: The Pinecone ID if found, else None.
        """
        try:
            # Attempt to retrieve from shared memory first
            cached_mapping = self.shared_memory.get_pinecone_mapping(external_id=external_id)
            if cached_mapping:
                self.logger.debug(f"Retrieved Pinecone ID from SharedMemoryManager for External ID '{external_id}'.")
                return cached_mapping['pinecone_id']

            # If not in cache, retrieve from database
            mapping = self.sqlite_db.get_mapping_by_external_id(external_id=external_id)
            if mapping:
                # Cache the mapping for future requests
                self.shared_memory.cache_pinecone_mapping(external_id=external_id, pinecone_id=mapping.pinecone_id, metadata=json.loads(mapping.metadata))
                self.logger.debug(f"Retrieved and cached Pinecone ID for External ID '{external_id}'.")
                return mapping.pinecone_id
            else:
                self.logger.warning(f"No Pinecone ID found for External ID '{external_id}'.")
                return None
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving Pinecone ID for External ID '{external_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving Pinecone ID for External ID '{external_id}': {e}", exc_info=True)
            return None

    def get_external_id(self, pinecone_id: str) -> Optional[str]:
        """
        Retrieves the external ID associated with a given Pinecone ID.
        
        Args:
            pinecone_id (str): The Pinecone-assigned unique identifier.
        
        Returns:
            Optional[str]: The external ID if found, else None.
        """
        try:
            # Attempt to retrieve from shared memory first
            cached_mapping = self.shared_memory.get_external_mapping(pinecone_id=pinecone_id)
            if cached_mapping:
                self.logger.debug(f"Retrieved External ID from SharedMemoryManager for Pinecone ID '{pinecone_id}'.")
                return cached_mapping['external_id']

            # If not in cache, retrieve from database
            mapping = self.sqlite_db.get_mapping_by_pinecone_id(pinecone_id=pinecone_id)
            if mapping:
                # Cache the mapping for future requests
                self.shared_memory.cache_external_mapping(pinecone_id=pinecone_id, external_id=mapping.external_id, metadata=json.loads(mapping.metadata))
                self.logger.debug(f"Retrieved and cached External ID for Pinecone ID '{pinecone_id}'.")
                return mapping.external_id
            else:
                self.logger.warning(f"No External ID found for Pinecone ID '{pinecone_id}'.")
                return None
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving External ID for Pinecone ID '{pinecone_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving External ID for Pinecone ID '{pinecone_id}': {e}", exc_info=True)
            return None

    # Synchronization Methods

    def _periodic_synchronization(self):
        """
        Periodically synchronizes the tracking system with the VectorDatabase to ensure data consistency.
        """
        try:
            while True:
                self.logger.debug("Starting periodic synchronization of Pinecone IDs.")
                self.synchronize_with_vector_db()
                self.logger.debug("Completed periodic synchronization of Pinecone IDs.")
                # Sleep for a defined interval before next synchronization
                threading.Event().wait(300)  # Synchronize every 5 minutes
        except Exception as e:
            self.logger.error(f"Unexpected error during periodic synchronization: {e}", exc_info=True)

    def synchronize_with_vector_db(self):
        """
        Synchronizes the tracking system with the VectorDatabase to ensure all Pinecone IDs are accurately tracked.
        """
        try:
            # Fetch all external IDs from the VectorDatabase
            external_ids = self.vector_db.get_all_external_ids()
            self.logger.debug(f"Fetched {len(external_ids)} external IDs from VectorDatabase.")

            # Fetch all mappings from the tracking system
            tracked_external_ids = self.sqlite_db.get_all_tracked_external_ids()
            self.logger.debug(f"Fetched {len(tracked_external_ids)} tracked external IDs from tracking system.")

            # Identify new mappings to add
            new_external_ids = set(external_ids) - set(tracked_external_ids)
            self.logger.debug(f"Identified {len(new_external_ids)} new external IDs to track.")

            for external_id in new_external_ids:
                pinecone_id = self.vector_db.get_pinecone_id(external_id=external_id)
                if pinecone_id:
                    # Fetch metadata from VectorDatabase
                    metadata = self.vector_db.get_vector_metadata(pinecone_id=pinecone_id)
                    if metadata:
                        self.add_mapping(external_id=external_id, pinecone_id=pinecone_id, metadata=metadata)

            # Identify mappings to remove
            obsolete_external_ids = set(tracked_external_ids) - set(external_ids)
            self.logger.debug(f"Identified {len(obsolete_external_ids)} obsolete external IDs to remove.")

            for external_id in obsolete_external_ids:
                self.remove_mapping(external_id=external_id)

            self.logger.info("Synchronization with VectorDatabase completed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to synchronize with VectorDatabase: {e}", exc_info=True)

    # Final Clean-up and Resource Management

    def dispose(self):
        """
        Disposes all resources and closes connections.
        """
        try:
            self.close()
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Error during disposal: {e}", exc_info=True)
            raise

    def close(self):
        """
        Closes all integrations and releases resources.
        """
        try:
            # Close VectorDatabase
            self.vector_db.close()
            self.logger.info("VectorDatabase closed successfully.")
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Failed to close VectorDatabase: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to close VectorDatabase: {e}")

        try:
            # Close SQLiteDatabase
            self.sqlite_db.dispose_engine()
            self.logger.info("SQLiteDatabase disposed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to dispose SQLiteDatabase: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to dispose SQLiteDatabase: {e}")

        try:
            # Close SharedMemoryManager
            self.shared_memory.close()
            self.logger.info("SharedMemoryManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close SharedMemoryManager: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to close SharedMemoryManager: {e}")

        try:
            # Close TimeSeriesDatabase
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise PineconeTrackingSystemError(f"Failed to close TimeSeriesDatabase: {e}")

        self.logger.info("PineconeTrackingSystem closed all resources successfully.")

    # Additional Utility Methods

    def get_all_mappings(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all current mappings between external IDs and Pinecone IDs.
        
        Returns:
            Optional[List[Dict[str, Any]]]: A list of mappings if successful, else None.
        """
        try:
            mappings = self.sqlite_db.get_all_pinecone_id_mappings()
            result = []
            for mapping in mappings:
                result.append({
                    'external_id': mapping.external_id,
                    'pinecone_id': mapping.pinecone_id,
                    'metadata': json.loads(mapping.metadata) if mapping.metadata else {}
                })
            self.logger.debug(f"Retrieved {len(result)} mappings from tracking system.")
            return result
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving all mappings: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving all mappings: {e}", exc_info=True)
            return None

    def update_mapping_metadata(self, external_id: str, new_metadata: Dict[str, Any]) -> bool:
        """
        Updates the metadata for an existing mapping.
        
        Args:
            external_id (str): The external unique identifier.
            new_metadata (Dict[str, Any]): The new metadata to update.
        
        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            mapping = self.sqlite_db.get_mapping_by_external_id(external_id=external_id)
            if not mapping:
                self.logger.warning(f"No mapping found for External ID '{external_id}'.")
                return False

            # Update the metadata
            self.sqlite_db.update_pinecone_id_metadata(external_id=external_id, new_metadata=json.dumps(new_metadata))
            self.logger.info(f"Updated metadata for External ID '{external_id}'.")

            # Update shared memory
            self.shared_memory.update_pinecone_mapping(external_id=external_id, pinecone_id=mapping.pinecone_id, metadata=new_metadata)
            self.logger.debug(f"Updated cached metadata in SharedMemoryManager for External ID '{external_id}'.")

            # Log the event
            self.time_series_db.log_event(event_type='pinecone_mapping_updated', details={'external_id': external_id, 'pinecone_id': mapping.pinecone_id, 'new_metadata': new_metadata})

            return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating metadata for External ID '{external_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating metadata for External ID '{external_id}': {e}", exc_info=True)
            return False
