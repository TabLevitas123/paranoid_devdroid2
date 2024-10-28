# databases/vector_db.py

import logging
import threading
from typing import Any, Dict, List, Optional
import json

import pinecone
from sentence_transformers import SentenceTransformer
from pinecone import VectorAlreadyExistsException, VectorNotFoundException, PineconeException

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.sqlite_db import SQLiteDatabase
from databases.graph_db import GraphDatabaseManager
from databases.tracking_system import PineconeTrackingSystem, PineconeTrackingSystemError
from databases.time_series_db import TimeSeriesDatabase
from shared_memory.shared_data_structures import SharedMemoryManager


class VectorDatabaseError(Exception):
    """Custom exception for VectorDatabase-related errors."""
    pass


class VectorDatabase:
    """
    Manages Pinecone vector embeddings and operations.
    Integrates seamlessly with SQLiteDatabase, GraphDatabaseManager, PineconeTrackingSystem,
    SharedMemoryManager, and TimeSeriesDatabase to support RAG in near-real-time.
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
                    cls._instance = super(VectorDatabase, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the VectorDatabase with necessary configurations, authentication, and integrations.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        # Setup logging
        self.logger = setup_logging('VectorDatabase')

        # Load configurations
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()

        # Initialize SQLite, Graph, Tracking System, Time Series Database, and Shared Memory
        try:
            self.sqlite_db = SQLiteDatabase()
            self.graph_db = GraphDatabaseManager()
            self.tracking_system = PineconeTrackingSystem()
            self.time_series_db = TimeSeriesDatabase()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024*1024*200)  # 200 MB
            self.logger.info("Integrated with SQLiteDatabase, GraphDatabaseManager, PineconeTrackingSystem, TimeSeriesDatabase, and SharedMemoryManager successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with other databases or shared memory: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to integrate with other databases or shared memory: {e}")

        # Initialize Pinecone
        try:
            pinecone_api_key_encrypted = self.config_loader.get('PINECONE_API_KEY_ENCRYPTED')
            pinecone_env_encrypted = self.config_loader.get('PINECONE_ENV_ENCRYPTED')
            pinecone_index_encrypted = self.config_loader.get('PINECONE_INDEX_ENCRYPTED')

            if not all([pinecone_api_key_encrypted, pinecone_env_encrypted, pinecone_index_encrypted]):
                self.logger.error("Pinecone configuration parameters are missing.")
                raise VectorDatabaseError("Pinecone configuration parameters are missing.")

            pinecone_api_key = self.encryption_manager.decrypt_data(pinecone_api_key_encrypted).decode('utf-8')
            pinecone_env = self.encryption_manager.decrypt_data(pinecone_env_encrypted).decode('utf-8')
            pinecone_index = self.encryption_manager.decrypt_data(pinecone_index_encrypted).decode('utf-8')

            pinecone.init(api_key=pinecone_api_key, environment=pinecone_env)
            self.index_name = pinecone_index

            if self.index_name not in pinecone.list_indexes():
                # Create index with appropriate dimension and metric
                # Assuming using SentenceTransformer with 768 dimensions
                pinecone.create_index(name=self.index_name, dimension=768, metric='cosine')
                self.logger.info(f"Created new Pinecone index '{self.index_name}'.")
            else:
                self.logger.info(f"Pinecone index '{self.index_name}' already exists.")

            self.index = pinecone.Index(self.index_name)
            self.logger.info(f"Connected to Pinecone index '{self.index_name}'.")

            # Initialize SentenceTransformer model
            model_name = self.config_loader.get('SENTENCE_TRANSFORMER_MODEL', 'all-MiniLM-L6-v2')
            self.model = SentenceTransformer(model_name)
            self.logger.info(f"Initialized SentenceTransformer model '{model_name}'.")

        except PineconeException as e:
            self.logger.error(f"Pinecone error during initialization: {e}", exc_info=True)
            raise VectorDatabaseError(f"Pinecone error during initialization: {e}")
        except Exception as e:
            self.logger.error(f"Failed to initialize Pinecone: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to initialize Pinecone: {e}")

        # Start background thread for cleaning up orphan vectors via Tracking System
        try:
            threading.Thread(target=self._cleanup_orphan_vectors, daemon=True).start()
            self.logger.info("Started background thread for cleaning up orphan vectors.")
        except Exception as e:
            self.logger.error(f"Failed to start background thread for cleaning up vectors: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to start background thread for cleaning up vectors: {e}")

        self._initialized = True

    # Vector Management Methods

    def index_user(self, user_id: int, username: str, email: str) -> bool:
        """
        Indexes a user into Pinecone and tracks the Pinecone ID.

        Args:
            user_id (int): The unique identifier of the user.
            username (str): The username of the user.
            email (str): The email of the user.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            metadata = {
                'type': 'user',
                'user_id': user_id,
                'username': username,
                'email': email
            }
            vector = self.model.encode([username + " " + email])[0].tolist()
            external_id = f"user_{user_id}"

            # Generate a unique Pinecone ID or use external_id
            pinecone_id = external_id

            # Upsert vector into Pinecone
            self.index.upsert(vectors=[(pinecone_id, vector, metadata)])
            self.logger.info(f"Indexed user '{username}' with Pinecone ID '{pinecone_id}'.")

            # Track Pinecone ID using Tracking System
            self.tracking_system.add_mapping(external_id=external_id, pinecone_id=pinecone_id, metadata=metadata)

            # Log event to TimeSeriesDatabase
            self.time_series_db.log_event(event_type='user_indexed', details={'user_id': user_id, 'pinecone_id': pinecone_id})

            return True
        except VectorAlreadyExistsException:
            self.logger.warning(f"Vector for user ID '{user_id}' already exists in Pinecone.")
            return False
        except PineconeException as e:
            self.logger.error(f"Pinecone error while indexing user ID '{user_id}': {e}", exc_info=True)
            return False
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error while indexing user ID '{user_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Failed to index user ID '{user_id}': {e}", exc_info=True)
            return False

    def index_bug_report(self, bug_report_id: int, title: str, description: str, severity: str) -> bool:
        """
        Indexes a bug report into Pinecone and tracks the Pinecone ID.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            title (str): The title of the bug report.
            description (str): The description of the bug report.
            severity (str): The severity level of the bug report.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            metadata = {
                'type': 'bug_report',
                'bug_report_id': bug_report_id,
                'severity': severity
            }
            vector = self.model.encode([title + " " + description])[0].tolist()
            external_id = f"bug_report_{bug_report_id}"

            # Generate a unique Pinecone ID or use external_id
            pinecone_id = external_id

            # Upsert vector into Pinecone
            self.index.upsert(vectors=[(pinecone_id, vector, metadata)])
            self.logger.info(f"Indexed bug report '{title}' with Pinecone ID '{pinecone_id}'.")

            # Track Pinecone ID using Tracking System
            self.tracking_system.add_mapping(external_id=external_id, pinecone_id=pinecone_id, metadata=metadata)

            # Log event to TimeSeriesDatabase
            self.time_series_db.log_event(event_type='bug_report_indexed', details={'bug_report_id': bug_report_id, 'pinecone_id': pinecone_id})

            return True
        except VectorAlreadyExistsException:
            self.logger.warning(f"Vector for bug report ID '{bug_report_id}' already exists in Pinecone.")
            return False
        except PineconeException as e:
            self.logger.error(f"Pinecone error while indexing bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error while indexing bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Failed to index bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    def index_feedback(self, feedback_id: int, service_name: str, rating: float, comment: Optional[str] = None) -> bool:
        """
        Indexes a feedback entry into Pinecone and tracks the Pinecone ID.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.
            service_name (str): The name of the service being reviewed.
            rating (float): The rating given.
            comment (Optional[str], optional): The comment provided. Defaults to None.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            metadata = {
                'type': 'feedback',
                'feedback_id': feedback_id,
                'service_name': service_name,
                'rating': rating
            }
            if comment:
                metadata['comment'] = comment

            vector_input = service_name + " " + (comment if comment else "")
            vector = self.model.encode([vector_input])[0].tolist()
            external_id = f"feedback_{feedback_id}"

            # Generate a unique Pinecone ID or use external_id
            pinecone_id = external_id

            # Upsert vector into Pinecone
            self.index.upsert(vectors=[(pinecone_id, vector, metadata)])
            self.logger.info(f"Indexed feedback ID '{feedback_id}' with Pinecone ID '{pinecone_id}'.")

            # Track Pinecone ID using Tracking System
            self.tracking_system.add_mapping(external_id=external_id, pinecone_id=pinecone_id, metadata=metadata)

            # Log event to TimeSeriesDatabase
            self.time_series_db.log_event(event_type='feedback_indexed', details={'feedback_id': feedback_id, 'pinecone_id': pinecone_id})

            return True
        except VectorAlreadyExistsException:
            self.logger.warning(f"Vector for feedback ID '{feedback_id}' already exists in Pinecone.")
            return False
        except PineconeException as e:
            self.logger.error(f"Pinecone error while indexing feedback ID '{feedback_id}': {e}", exc_info=True)
            return False
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error while indexing feedback ID '{feedback_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Failed to index feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    def delete_vector(self, external_id: str) -> bool:
        """
        Deletes a vector from Pinecone and removes its tracking from the Tracking System.

        Args:
            external_id (str): The external unique identifier (e.g., 'user_1', 'bug_report_5').

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            pinecone_id = self.tracking_system.get_pinecone_id(external_id=external_id)
            if not pinecone_id:
                self.logger.warning(f"No Pinecone ID found for external ID '{external_id}'.")
                return False

            # Delete the vector from Pinecone
            self.index.delete(ids=[pinecone_id])
            self.logger.info(f"Deleted vector with Pinecone ID '{pinecone_id}' from Pinecone.")

            # Remove the mapping from Tracking System
            self.tracking_system.remove_mapping(external_id=external_id)

            # Log event to TimeSeriesDatabase
            self.time_series_db.log_event(event_type='vector_deleted', details={'external_id': external_id, 'pinecone_id': pinecone_id})

            return True
        except VectorNotFoundException:
            self.logger.warning(f"Vector with Pinecone ID '{pinecone_id}' not found in Pinecone.")
            return False
        except PineconeException as e:
            self.logger.error(f"Pinecone error while deleting vector ID '{pinecone_id}': {e}", exc_info=True)
            return False
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error while deleting vector ID '{pinecone_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Failed to delete vector with external ID '{external_id}': {e}", exc_info=True)
            return False

    def search_similar(self, query_text: str, top_k: int = 5) -> Optional[List[Dict[str, Any]]]:
        """
        Searches for similar vectors in Pinecone based on the query text.

        Args:
            query_text (str): The query text to perform similarity search.
            top_k (int, optional): Number of top similar results to retrieve. Defaults to 5.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of similar vectors with their metadata if successful, else None.
        """
        try:
            vector = self.model.encode([query_text])[0].tolist()
            response = self.index.query(vector=vector, top_k=top_k, include_metadata=True)

            results = []
            for match in response['matches']:
                pinecone_id = match['id']
                metadata = match['metadata']
                score = match['score']

                # Retrieve external ID from Tracking System
                external_id = self.tracking_system.get_external_id(pinecone_id=pinecone_id)
                if not external_id:
                    self.logger.warning(f"No external ID found for Pinecone ID '{pinecone_id}'. Skipping.")
                    continue

                # Fetch detailed metadata from other databases
                if metadata['type'] == 'user':
                    user_data = self.sqlite_db.get_user_by_id(metadata['user_id'])
                    if user_data:
                        results.append({
                            'external_id': external_id,
                            'type': 'user',
                            'data': user_data,
                            'score': score
                        })
                elif metadata['type'] == 'bug_report':
                    bug_data = self.sqlite_db.get_bug_report(metadata['bug_report_id'])
                    if bug_data:
                        results.append({
                            'external_id': external_id,
                            'type': 'bug_report',
                            'data': bug_data,
                            'score': score
                        })
                elif metadata['type'] == 'feedback':
                    feedback_data = self.sqlite_db.get_feedback_entry(metadata['feedback_id'])
                    if feedback_data:
                        results.append({
                            'external_id': external_id,
                            'type': 'feedback',
                            'data': feedback_data,
                            'score': score
                        })
                else:
                    self.logger.warning(f"Unknown metadata type '{metadata['type']}' for Pinecone ID '{pinecone_id}'.")

            self.logger.debug(f"Search for query '{query_text}' returned {len(results)} results.")

            # Log event to TimeSeriesDatabase
            self.time_series_db.log_event(event_type='vector_search', details={'query_text': query_text, 'top_k': top_k, 'results_count': len(results)})

            return results
        except PineconeException as e:
            self.logger.error(f"Pinecone error during similarity search: {e}", exc_info=True)
            return None
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error during similarity search: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Failed to perform similarity search for query '{query_text}': {e}", exc_info=True)
            return None

    def get_all_external_ids(self) -> Optional[List[str]]:
        """
        Retrieves all external IDs from the VectorDatabase.

        Returns:
            Optional[List[str]]: A list of external IDs if successful, else None.
        """
        try:
            # Assuming VectorDatabase can fetch all external IDs via Tracking System
            mappings = self.tracking_system.get_all_mappings()
            if mappings:
                external_ids = [mapping['external_id'] for mapping in mappings]
                self.logger.debug(f"Retrieved {len(external_ids)} external IDs from Tracking System.")
                return external_ids
            else:
                self.logger.debug("No mappings found in Tracking System.")
                return []
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error while retrieving all external IDs: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving all external IDs: {e}", exc_info=True)
            return None

    # Cleanup Methods

    def _cleanup_orphan_vectors(self):
        """
        Cleans up vectors in Pinecone that are no longer tracked in the Tracking System.
        Runs periodically in a background thread.
        """
        try:
            while True:
                self.logger.debug("Starting cleanup of orphan vectors.")
                self._cleanup_orphan_vectors_once()
                self.logger.debug("Completed cleanup of orphan vectors.")
                # Sleep for a defined interval before next cleanup
                threading.Event().wait(600)  # Cleanup every 10 minutes
        except Exception as e:
            self.logger.error(f"Unexpected error during orphan vector cleanup: {e}", exc_info=True)

    def _cleanup_orphan_vectors_once(self):
        """
        Performs a single cleanup operation to remove orphan vectors from Pinecone.
        """
        try:
            # Fetch all Pinecone IDs from Tracking System
            tracked_pinecone_ids = [mapping['pinecone_id'] for mapping in self.tracking_system.get_all_mappings() or []]
            self.logger.debug(f"Tracked Pinecone IDs count: {len(tracked_pinecone_ids)}")

            # Since Pinecone does not provide a method to list all IDs, we cannot fetch them directly.
            # Instead, maintain a separate log or tracking system to know which IDs exist.
            # Therefore, no action is taken unless Pinecone introduces ID listing capabilities.

            # Placeholder: No cleanup performed as per current Pinecone capabilities
            self.logger.info("Orphan vector cleanup is not performed as Pinecone does not support listing all IDs.")
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Tracking system error during orphan vector cleanup: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Failed to clean up orphan vectors: {e}", exc_info=True)

    # Final Clean-up and Resource Management

    def dispose(self):
        """
        Disposes all resources and closes connections.
        """
        try:
            self.close()
        except VectorDatabaseError as e:
            self.logger.error(f"Error during disposal: {e}", exc_info=True)
            raise

    def close(self):
        """
        Closes all integrations and releases resources.
        """
        try:
            # Close Pinecone connection
            pinecone.deinit()
            self.logger.info("Pinecone client deinitialized successfully.")
        except PineconeException as e:
            self.logger.error(f"Pinecone error while deinitializing: {e}", exc_info=True)
            raise VectorDatabaseError(f"Pinecone error while deinitializing: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while deinitializing Pinecone: {e}", exc_info=True)
            raise VectorDatabaseError(f"Unexpected error while deinitializing Pinecone: {e}")

        try:
            # Close Tracking System
            self.tracking_system.dispose()
            self.logger.info("PineconeTrackingSystem disposed successfully.")
        except PineconeTrackingSystemError as e:
            self.logger.error(f"Failed to dispose PineconeTrackingSystem: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to dispose PineconeTrackingSystem: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while disposing PineconeTrackingSystem: {e}", exc_info=True)
            raise VectorDatabaseError(f"Unexpected error while disposing PineconeTrackingSystem: {e}")

        try:
            # Close SharedMemoryManager
            self.shared_memory.close()
            self.logger.info("SharedMemoryManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close SharedMemoryManager: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close SharedMemoryManager: {e}")

        try:
            # Close SQLiteDatabase
            self.sqlite_db.dispose_engine()
            self.logger.info("SQLiteDatabase disposed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to dispose SQLiteDatabase: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to dispose SQLiteDatabase: {e}")

        try:
            # Close GraphDatabaseManager
            self.graph_db.close()
            self.logger.info("GraphDatabaseManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close GraphDatabaseManager: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close GraphDatabaseManager: {e}")

        try:
            # Close TimeSeriesDatabase
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except VectorDatabaseError as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close TimeSeriesDatabase: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing TimeSeriesDatabase: {e}", exc_info=True)
            raise VectorDatabaseError(f"Unexpected error while closing TimeSeriesDatabase: {e}")

        self.logger.info("VectorDatabase closed all resources successfully.")

    # Additional Utility Methods

    def get_vector_metadata(self, pinecone_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the metadata associated with a given Pinecone ID.

        Args:
            pinecone_id (str): The Pinecone-assigned unique identifier.

        Returns:
            Optional[Dict[str, Any]]: The metadata if found, else None.
        """
        try:
            mapping = self.tracking_system.sqlite_db.get_mapping_by_pinecone_id(pinecone_id=pinecone_id)
            if mapping:
                metadata = json.loads(mapping.metadata) if mapping.metadata else {}
                self.logger.debug(f"Retrieved metadata for Pinecone ID '{pinecone_id}': {metadata}")
                return metadata
            else:
                self.logger.warning(f"No metadata found for Pinecone ID '{pinecone_id}'.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to retrieve metadata for Pinecone ID '{pinecone_id}': {e}", exc_info=True)
            return None
