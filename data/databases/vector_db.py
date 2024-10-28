# databases/vector_db.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import os
import json

import pinecone
from sentence_transformers import SentenceTransformer
from pinecone import PineconeException
from sqlalchemy.exc import SQLAlchemyError

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.sqlite_db import SQLiteDatabase
from databases.graph_db import GraphDatabaseManager
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase

class VectorDatabaseError(Exception):
    """Custom exception for VectorDatabase-related errors."""
    pass

class VectorDatabase:
    """
    Manages vector embeddings and similarity searches using Pinecone.
    Integrates seamlessly with SQLiteDatabase, GraphDatabaseManager, TimeSeriesDatabase, and SharedMemoryManager to support RAG in near-real-time.
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

        # Initialize SQLite and Graph Databases
        try:
            self.sqlite_db = SQLiteDatabase()
            self.graph_db = GraphDatabaseManager()
            self.time_series_db = TimeSeriesDatabase()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024*1024*200)  # 200 MB
            self.logger.info("Integrated with SQLiteDatabase, GraphDatabaseManager, TimeSeriesDatabase, and SharedMemoryManager successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with other databases or shared memory: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to integrate with other databases or shared memory: {e}")

        # Initialize Pinecone
        try:
            pinecone_api_key_encrypted = self.config_loader.get('PINECONE_API_KEY')
            pinecone_env = self.config_loader.get('PINECONE_ENVIRONMENT', 'us-west1-gcp')
            if not pinecone_api_key_encrypted:
                self.logger.error("Pinecone API key is missing in configuration.")
                raise VectorDatabaseError("Pinecone API key is missing in configuration.")
            pinecone_api_key = self.encryption_manager.decrypt_data(pinecone_api_key_encrypted).decode('utf-8')

            pinecone.init(api_key=pinecone_api_key, environment=pinecone_env)
            self.logger.info(f"Pinecone initialized successfully in environment '{pinecone_env}'.")

            # Define index parameters
            self.index_name = self.config_loader.get('PINECONE_INDEX_NAME', 'llm-rag-index')
            self.dimension = int(self.config_loader.get('PINECONE_DIMENSION', 768))
            self.metric = self.config_loader.get('PINECONE_METRIC', 'cosine')
            self.pod_type = self.config_loader.get('PINECONE_POD_TYPE', 'p1')
            self.replicas = int(self.config_loader.get('PINECONE_REPLICAS', 1))

            # Check if index exists; if not, create it
            if self.index_name not in pinecone.list_indexes():
                pinecone.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric=self.metric,
                    pod_type=self.pod_type,
                    replicas=self.replicas
                )
                self.logger.info(f"Pinecone index '{self.index_name}' created successfully.")
            else:
                self.logger.info(f"Pinecone index '{self.index_name}' already exists.")

            # Connect to the index
            self.index = pinecone.Index(self.index_name)
            self.logger.info(f"Connected to Pinecone index '{self.index_name}' successfully.")
        except PineconeException as e:
            self.logger.error(f"Pinecone initialization error: {e}", exc_info=True)
            raise VectorDatabaseError(f"Pinecone initialization error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during Pinecone initialization: {e}", exc_info=True)
            raise VectorDatabaseError(f"Unexpected error during Pinecone initialization: {e}")

        # Initialize SentenceTransformer model
        try:
            model_name = self.config_loader.get('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            self.model = SentenceTransformer(model_name)
            self.logger.info(f"SentenceTransformer model '{model_name}' loaded successfully.")
        except Exception as e:
            self.logger.error(f"Failed to load SentenceTransformer model: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to load SentenceTransformer model: {e}")

        self._initialized = True

    # Utility Methods

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding vector for the given text using the SentenceTransformer model.

        Args:
            text (str): The input text to generate embedding for.

        Returns:
            List[float]: The embedding vector.
        """
        try:
            embedding = self.model.encode(text, show_progress_bar=False, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            self.logger.error(f"Failed to generate embedding for text: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to generate embedding for text: {e}")

    def index_data(self, data_id: str, text: str, metadata: Dict[str, Any]) -> bool:
        """
        Indexes a single data entry into Pinecone.

        Args:
            data_id (str): The unique identifier for the data.
            text (str): The textual content to generate embedding from.
            metadata (Dict[str, Any]): Additional metadata to store with the vector.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            embedding = self._generate_embedding(text)
            self.index.upsert(vectors=[(data_id, embedding, metadata)])
            self.logger.info(f"Data indexed successfully with ID '{data_id}'.")
            return True
        except PineconeException as e:
            self.logger.error(f"Pinecone indexing error for ID '{data_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while indexing data ID '{data_id}': {e}", exc_info=True)
            return False

    def batch_index_data(self, vectors: List[Tuple[str, str, Dict[str, Any]]]) -> bool:
        """
        Indexes multiple data entries into Pinecone in batch.

        Args:
            vectors (List[Tuple[str, str, Dict[str, Any]]]): A list of tuples containing (data_id, text, metadata).

        Returns:
            bool: True if batch indexing is successful, False otherwise.
        """
        try:
            upsert_vectors = []
            for data_id, text, metadata in vectors:
                embedding = self._generate_embedding(text)
                upsert_vectors.append((data_id, embedding, metadata))
            self.index.upsert(vectors=upsert_vectors)
            self.logger.info(f"Batch indexed {len(vectors)} vectors successfully.")
            return True
        except PineconeException as e:
            self.logger.error(f"Pinecone batch indexing error: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during batch indexing: {e}", exc_info=True)
            return False

    def search_similar(self, query_text: str, top_k: int = 5) -> Optional[List[Dict[str, Any]]]:
        """
        Searches for similar vectors in Pinecone based on the query text.

        Args:
            query_text (str): The text to query.
            top_k (int, optional): Number of top similar vectors to retrieve. Defaults to 5.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of similar vectors with metadata if successful, else None.
        """
        try:
            embedding = self._generate_embedding(query_text)
            response = self.index.query(queries=[embedding], top_k=top_k, include_metadata=True)
            if not response or not response.results:
                self.logger.warning(f"No results found for query: '{query_text}'.")
                return None
            similar_vectors = []
            for match in response.results[0].matches:
                similar_vectors.append({
                    'id': match.id,
                    'score': match.score,
                    'metadata': match.metadata
                })
            self.logger.debug(f"Found {len(similar_vectors)} similar vectors for query: '{query_text}'.")
            return similar_vectors
        except PineconeException as e:
            self.logger.error(f"Pinecone search error for query '{query_text}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during search for query '{query_text}': {e}", exc_info=True)
            return None

    def delete_data(self, data_id: str) -> bool:
        """
        Deletes a vector from Pinecone based on its unique identifier.

        Args:
            data_id (str): The unique identifier of the data to delete.

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            self.index.delete(ids=[data_id])
            self.logger.info(f"Data with ID '{data_id}' deleted successfully from Pinecone.")
            return True
        except PineconeException as e:
            self.logger.error(f"Pinecone deletion error for ID '{data_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during deletion of data ID '{data_id}': {e}", exc_info=True)
            return False

    def update_vector(self, data_id: str, new_text: str, new_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Updates the vector and metadata for a given data ID in Pinecone.

        Args:
            data_id (str): The unique identifier of the data entry.
            new_text (str): The new textual content to generate embedding from.
            new_metadata (Optional[Dict[str, Any]], optional): New metadata to update. Defaults to None.

        Returns:
            bool: True if update is successful, False otherwise.
        """
        try:
            embedding = self._generate_embedding(new_text)
            # Fetch existing metadata
            response = self.index.fetch(ids=[data_id])
            if data_id not in response.vectors:
                self.logger.error(f"No existing vector found for data ID '{data_id}' to update.")
                return False
            existing_metadata = response.vectors[data_id].metadata
            if new_metadata:
                existing_metadata.update(new_metadata)
            self.index.upsert(vectors=[(data_id, embedding, existing_metadata)])
            self.logger.info(f"Vector for data ID '{data_id}' updated successfully.")
            return True
        except PineconeException as e:
            self.logger.error(f"Pinecone update error for ID '{data_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during update of data ID '{data_id}': {e}", exc_info=True)
            return False

    def count_vectors(self) -> Optional[int]:
        """
        Retrieves the total number of vectors indexed in Pinecone.

        Returns:
            Optional[int]: The total count of vectors if successful, else None.
        """
        try:
            stats = self.index.describe_index_stats()
            total_vectors = stats.get('total_vector_count', 0)
            self.logger.debug(f"Total vectors in Pinecone index: {total_vectors}")
            return total_vectors
        except PineconeException as e:
            self.logger.error(f"Pinecone stats retrieval error: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving vector count: {e}", exc_info=True)
            return None

    def purge_index(self) -> bool:
        """
        Purges all vectors from the Pinecone index.

        Returns:
            bool: True if purge is successful, False otherwise.
        """
        try:
            self.index.delete(delete_all=True)
            self.logger.info("All vectors purged from Pinecone index successfully.")
            return True
        except PineconeException as e:
            self.logger.error(f"Pinecone purge error: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during purge: {e}", exc_info=True)
            return False

    # Integration Methods with SQLiteDatabase, GraphDatabaseManager, TimeSeriesDatabase

    def index_user(self, user_id: int, username: str, email: str) -> bool:
        """
        Indexes a user into Pinecone.

        Args:
            user_id (int): The unique identifier of the user.
            username (str): The username of the user.
            email (str): The email address of the user.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            combined_text = f"Username: {username}\nEmail: {email}"
            data_id = f"user_{user_id}"
            metadata = {
                'type': 'user',
                'user_id': user_id,
                'username': username,
                'email': email,
                'timestamp': datetime.utcnow().isoformat()
            }
            success = self.index_data(data_id=data_id, text=combined_text, metadata=metadata)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='user_indexed', details={'user_id': user_id})
                # Update shared memory
                self.shared_memory.cache_user(user_id=user_id, data=json.dumps(metadata))
            return success
        except Exception as e:
            self.logger.error(f"Failed to index user ID '{user_id}': {e}", exc_info=True)
            return False

    def update_user_email(self, user_id: int, new_email: str) -> bool:
        """
        Updates a user's email in Pinecone.

        Args:
            user_id (int): The unique identifier of the user.
            new_email (str): The new email address.

        Returns:
            bool: True if update is successful, False otherwise.
        """
        try:
            data_id = f"user_{user_id}"
            new_text = f"Username: {self.sqlite_db.get_user_by_id(user_id)['username']}\nEmail: {new_email}"
            new_metadata = {'email': new_email, 'timestamp': datetime.utcnow().isoformat()}
            success = self.update_vector(data_id=data_id, new_text=new_text, new_metadata=new_metadata)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='user_email_updated', details={'user_id': user_id, 'new_email': new_email})
                # Update shared memory
                self.shared_memory.cache_user(user_id=user_id, data=json.dumps(new_metadata))
            return success
        except Exception as e:
            self.logger.error(f"Failed to update email for user ID '{user_id}': {e}", exc_info=True)
            return False

    def delete_user(self, user_id: int) -> bool:
        """
        Deletes a user from Pinecone.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            data_id = f"user_{user_id}"
            success = self.delete_data(data_id=data_id)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='user_deleted', details={'user_id': user_id})
                # Update shared memory
                self.shared_memory.delete_user(user_id=user_id)
            return success
        except Exception as e:
            self.logger.error(f"Failed to delete user ID '{user_id}': {e}", exc_info=True)
            return False

    def index_bug_report(self, bug_report_id: int, title: str, description: str, severity: str) -> bool:
        """
        Indexes a bug report into Pinecone.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            title (str): The title of the bug report.
            description (str): The detailed description of the bug.
            severity (str): The severity level of the bug.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            combined_text = f"Title: {title}\nDescription: {description}\nSeverity: {severity}"
            data_id = f"bug_report_{bug_report_id}"
            metadata = {
                'type': 'bug_report',
                'bug_report_id': bug_report_id,
                'severity': severity,
                'status': 'Open',
                'timestamp': datetime.utcnow().isoformat()
            }
            success = self.index_data(data_id=data_id, text=combined_text, metadata=metadata)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='bug_report_indexed', details={'bug_report_id': bug_report_id, 'severity': severity})
                # Update shared memory
                self.shared_memory.cache_bug_report(bug_report_id=bug_report_id, data=json.dumps(metadata))
            return success
        except Exception as e:
            self.logger.error(f"Failed to index bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    def update_bug_report_status(self, bug_report_id: int, new_status: str, comments: Optional[str] = None) -> bool:
        """
        Updates the status of a bug report in Pinecone.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            new_status (str): The new status ('Open', 'In Progress', 'Resolved', 'Closed').
            comments (Optional[str], optional): Additional comments or resolution details. Defaults to None.

        Returns:
            bool: True if update is successful, False otherwise.
        """
        try:
            bug = self.sqlite_db.get_bug_report(bug_report_id)
            if not bug:
                self.logger.error(f"Bug report with ID '{bug_report_id}' does not exist in SQLiteDatabase.")
                return False
            combined_text = f"Title: {bug['title']}\nDescription: {bug['description']}\nSeverity: {bug['severity']}\nStatus: {new_status}\nComments: {comments or ''}"
            metadata = {
                'type': 'bug_report',
                'bug_report_id': bug_report_id,
                'severity': bug['severity'],
                'status': new_status,
                'timestamp': datetime.utcnow().isoformat()
            }
            success = self.update_vector(data_id=f"bug_report_{bug_report_id}", new_text=combined_text, new_metadata=metadata)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='bug_report_status_updated', details={'bug_report_id': bug_report_id, 'new_status': new_status})
                # Update shared memory
                self.shared_memory.cache_bug_report(bug_report_id=bug_report_id, data=json.dumps(metadata))
            return success
        except Exception as e:
            self.logger.error(f"Failed to update bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    def delete_bug_report(self, bug_report_id: int) -> bool:
        """
        Deletes a bug report from Pinecone.

        Args:
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            data_id = f"bug_report_{bug_report_id}"
            success = self.delete_data(data_id=data_id)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='bug_report_deleted', details={'bug_report_id': bug_report_id})
                # Update shared memory
                self.shared_memory.delete_bug_report(bug_report_id=bug_report_id)
            return success
        except Exception as e:
            self.logger.error(f"Failed to delete bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    def index_feedback(self, feedback_id: int, service_name: str, rating: float, comment: Optional[str] = None) -> bool:
        """
        Indexes a feedback entry into Pinecone.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.
            service_name (str): The name of the service being reviewed.
            rating (float): The rating given by the user.
            comment (Optional[str], optional): Additional comments. Defaults to None.

        Returns:
            bool: True if indexing is successful, False otherwise.
        """
        try:
            combined_text = f"Service: {service_name}\nRating: {rating}\nComment: {comment or ''}"
            data_id = f"feedback_{feedback_id}"
            metadata = {
                'type': 'feedback',
                'feedback_id': feedback_id,
                'service_name': service_name,
                'rating': rating,
                'processed': False,
                'timestamp': datetime.utcnow().isoformat()
            }
            success = self.index_data(data_id=data_id, text=combined_text, metadata=metadata)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='feedback_indexed', details={'feedback_id': feedback_id, 'service_name': service_name, 'rating': rating})
                # Update shared memory
                self.shared_memory.cache_feedback_entry(feedback_id=feedback_id, data=json.dumps(metadata))
            return success
        except Exception as e:
            self.logger.error(f"Failed to index feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    def update_feedback_entry(self, feedback_id: int, new_rating: Optional[float] = None, new_comment: Optional[str] = None) -> bool:
        """
        Updates a feedback entry's rating and/or comment in Pinecone.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.
            new_rating (Optional[float], optional): The new rating to update. Defaults to None.
            new_comment (Optional[str], optional): The new comment to update. Defaults to None.

        Returns:
            bool: True if update is successful, False otherwise.
        """
        try:
            feedback = self.sqlite_db.get_feedback_entry(feedback_id)
            if not feedback:
                self.logger.error(f"Feedback entry with ID '{feedback_id}' does not exist in SQLiteDatabase.")
                return False
            combined_text = f"Service: {feedback['service_name']}\nRating: {new_rating if new_rating is not None else feedback['rating']}\nComment: {new_comment or feedback['comment']}"
            metadata = {
                'type': 'feedback',
                'feedback_id': feedback_id,
                'service_name': feedback['service_name'],
                'rating': new_rating if new_rating is not None else feedback['rating'],
                'processed': feedback['processed'],
                'timestamp': datetime.utcnow().isoformat()
            }
            success = self.update_vector(data_id=f"feedback_{feedback_id}", new_text=combined_text, new_metadata=metadata)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='feedback_updated', details={'feedback_id': feedback_id, 'new_rating': new_rating, 'new_comment': new_comment})
                # Update shared memory
                self.shared_memory.cache_feedback_entry(feedback_id=feedback_id, data=json.dumps(metadata))
            return success
        except Exception as e:
            self.logger.error(f"Failed to update feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    def delete_feedback_entry(self, feedback_id: int) -> bool:
        """
        Deletes a feedback entry from Pinecone.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            data_id = f"feedback_{feedback_id}"
            success = self.delete_data(data_id=data_id)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='feedback_deleted', details={'feedback_id': feedback_id})
                # Update shared memory
                self.shared_memory.delete_feedback_entry(feedback_id=feedback_id)
            return success
        except Exception as e:
            self.logger.error(f"Failed to delete feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    # RAG Operation

    def perform_rag(self, query_text: str, top_k: int = 5) -> Optional[Dict[str, Any]]:
        """
        Performs Retrieval-Augmented Generation by searching for similar vectors and retrieving their metadata.

        Args:
            query_text (str): The query text to perform RAG on.
            top_k (int, optional): Number of top similar results to retrieve. Defaults to 5.

        Returns:
            Optional[Dict[str, Any]]: The aggregated data from similar vectors if successful, else None.
        """
        try:
            similar_vectors = self.search_similar(query_text=query_text, top_k=top_k)
            if not similar_vectors:
                self.logger.warning(f"No similar vectors found for query: '{query_text}'.")
                return None

            rag_result = {
                'query': query_text,
                'similar_vectors': similar_vectors
            }

            # Enrich RAG result with data from SQLiteDatabase and GraphDatabaseManager
            for vector in similar_vectors:
                metadata = vector['metadata']
                data_type = metadata.get('type')
                data_id = metadata.get(f"{data_type}_id")
                if data_type == 'user':
                    user_data = self.sqlite_db.get_user_by_id(data_id)
                    rag_result.setdefault('users', []).append(user_data)
                elif data_type == 'bug_report':
                    bug_data = self.sqlite_db.get_bug_report(data_id)
                    rag_result.setdefault('bug_reports', []).append(bug_data)
                elif data_type == 'feedback':
                    feedback_data = self.sqlite_db.get_feedback_entry(data_id)
                    rag_result.setdefault('feedback_entries', []).append(feedback_data)
                else:
                    self.logger.warning(f"Unknown data type '{data_type}' in vector metadata.")

            # Optionally, integrate with GraphDatabaseManager for related entities
            # Example: Fetch related users or services
            related_entities = []
            for bug in rag_result.get('bug_reports', []):
                related_users = self.graph_db.find_related_users(service_name=bug.get('severity', ''))
                related_entities.extend(related_users or [])
            for feedback in rag_result.get('feedback_entries', []):
                related_users = self.graph_db.find_related_users(service_name=feedback.get('service_name', ''))
                related_entities.extend(related_users or [])
            rag_result['related_entities'] = related_entities

            # Log RAG operation to Time Series Database
            self.time_series_db.log_event(event_type='rag_performed', details={'query_text': query_text, 'top_k': top_k, 'results_count': len(similar_vectors)})

            self.logger.debug(f"RAG operation completed for query: '{query_text}'.")
            return rag_result
        except Exception as e:
            self.logger.error(f"Failed to perform RAG operation for query '{query_text}': {e}", exc_info=True)
            return None

    # Cleanup and Resource Management

    def close(self):
        """
        Closes the Pinecone connection and all integrations.
        """
        try:
            pinecone.deinit()
            self.logger.info("Pinecone connection closed successfully.")
        except PineconeException as e:
            self.logger.error(f"Failed to close Pinecone connection: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close Pinecone connection: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing Pinecone connection: {e}", exc_info=True)
            raise VectorDatabaseError(f"Unexpected error while closing Pinecone connection: {e}")

        try:
            self.sqlite_db.dispose_engine()
            self.logger.info("SQLiteDatabase disposed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to dispose SQLiteDatabase: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to dispose SQLiteDatabase: {e}")

        try:
            self.graph_db.close()
            self.logger.info("GraphDatabaseManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close GraphDatabaseManager: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close GraphDatabaseManager: {e}")

        try:
            self.shared_memory.close()
            self.logger.info("SharedMemoryManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close SharedMemoryManager: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close SharedMemoryManager: {e}")

        try:
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise VectorDatabaseError(f"Failed to close TimeSeriesDatabase: {e}")

    # Additional Utility Methods

    def refresh_index(self) -> bool:
        """
        Refreshes the Pinecone index by re-indexing all data from SQLiteDatabase.

        Returns:
            bool: True if refresh is successful, False otherwise.
        """
        try:
            # Re-index all users
            with self.sqlite_db.get_session() as session:
                users = session.query(self.sqlite_db.User).all()
                user_vectors = []
                for user in users:
                    combined_text = f"Username: {user.username}\nEmail: {user.email}"
                    data_id = f"user_{user.id}"
                    metadata = {
                        'type': 'user',
                        'user_id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'timestamp': user.updated_at.isoformat()
                    }
                    user_vectors.append((data_id, combined_text, metadata))
                self.batch_index_data(user_vectors)
                self.logger.info(f"Re-indexed {len(user_vectors)} user vectors.")

            # Re-index all bug reports
            with self.sqlite_db.get_session() as session:
                bug_reports = session.query(self.sqlite_db.BugReport).all()
                bug_vectors = []
                for bug in bug_reports:
                    combined_text = f"Title: {bug.title}\nDescription: {bug.description}\nSeverity: {bug.severity}\nStatus: {bug.status}"
                    data_id = f"bug_report_{bug.id}"
                    metadata = {
                        'type': 'bug_report',
                        'bug_report_id': bug.id,
                        'severity': bug.severity,
                        'status': bug.status,
                        'timestamp': bug.updated_at.isoformat()
                    }
                    bug_vectors.append((data_id, combined_text, metadata))
                self.batch_index_data(bug_vectors)
                self.logger.info(f"Re-indexed {len(bug_vectors)} bug report vectors.")

            # Re-index all feedback entries
            with self.sqlite_db.get_session() as session:
                feedback_entries = session.query(self.sqlite_db.FeedbackEntry).all()
                feedback_vectors = []
                for feedback in feedback_entries:
                    combined_text = f"Service: {feedback.service_name}\nRating: {feedback.rating}\nComment: {feedback.comment or ''}"
                    data_id = f"feedback_{feedback.id}"
                    metadata = {
                        'type': 'feedback',
                        'feedback_id': feedback.id,
                        'service_name': feedback.service_name,
                        'rating': feedback.rating,
                        'processed': feedback.processed,
                        'timestamp': feedback.updated_at.isoformat()
                    }
                    feedback_vectors.append((data_id, combined_text, metadata))
                self.batch_index_data(feedback_vectors)
                self.logger.info(f"Re-indexed {len(feedback_vectors)} feedback entry vectors.")

            self.logger.info("Pinecone index refreshed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to refresh Pinecone index: {e}", exc_info=True)
            return False

    def cleanup_deleted_entries(self) -> bool:
        """
        Cleans up vectors in Pinecone that no longer exist in SQLiteDatabase.

        Returns:
            bool: True if cleanup is successful, False otherwise.
        """
        try:
            # Fetch all existing IDs from SQLiteDatabase
            with self.sqlite_db.get_session() as session:
                user_ids = {f"user_{user.id}" for user in session.query(self.sqlite_db.User.id).all()}
                bug_ids = {f"bug_report_{bug.id}" for bug in session.query(self.sqlite_db.BugReport.id).all()}
                feedback_ids = {f"feedback_{fb.id}" for fb in session.query(self.sqlite_db.FeedbackEntry.id).all()}
                existing_ids = user_ids.union(bug_ids).union(feedback_ids)

            # Since Pinecone does not provide a straightforward method to list all IDs, we assume maintaining a separate log or tracking system.
            # For demonstration, this method will be a placeholder and will delete all vectors not in existing_ids.
            # In practice, maintain a separate tracking system for Pinecone IDs.
            # Example: Fetch all IDs from an external tracking database or cache.

            # Placeholder: Assuming an external tracking system provides all pinecone_ids
            pinecone_ids = self.shared_memory.get_all_pinecone_ids()
            if pinecone_ids is None:
                self.logger.error("Failed to retrieve Pinecone IDs from shared memory.")
                return False

            ids_to_delete = set(pinecone_ids) - existing_ids
            if ids_to_delete:
                self.index.delete(ids=list(ids_to_delete))
                self.logger.info(f"Deleted {len(ids_to_delete)} vectors from Pinecone that no longer exist in SQLiteDatabase.")
            else:
                self.logger.info("No vectors to delete from Pinecone.")

            # Log cleanup event
            self.time_series_db.log_event(event_type='cleanup_deleted_entries', details={'deleted_ids_count': len(ids_to_delete)})

            return True
        except Exception as e:
            self.logger.error(f"Failed to cleanup deleted entries in Pinecone: {e}", exc_info=True)
            return False

    # Integration with GraphDatabaseManager

    def establish_relationship_with_graph_db(self, data_id: str, related_data_id: str, relation_type: str) -> bool:
        """
        Establishes a relationship between two data entries in the GraphDatabase.

        Args:
            data_id (str): The unique identifier of the first data entry.
            related_data_id (str): The unique identifier of the related data entry.
            relation_type (str): The type of the relationship (e.g., 'RELATED_TO').

        Returns:
            bool: True if the relationship is established successfully, False otherwise.
        """
        try:
            success = self.graph_db.add_relation(source_id=data_id, target_id=related_data_id, relation_type=relation_type)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='relationship_established', details={'source_id': data_id, 'target_id': related_data_id, 'relation_type': relation_type})
            return success
        except Exception as e:
            self.logger.error(f"Failed to establish relationship '{relation_type}' between '{data_id}' and '{related_data_id}': {e}", exc_info=True)
            return False

    def remove_relationship_with_graph_db(self, data_id: str, related_data_id: str, relation_type: str) -> bool:
        """
        Removes a relationship between two data entries in the GraphDatabase.

        Args:
            data_id (str): The unique identifier of the first data entry.
            related_data_id (str): The unique identifier of the related data entry.
            relation_type (str): The type of the relationship to remove.

        Returns:
            bool: True if the relationship is removed successfully, False otherwise.
        """
        try:
            success = self.graph_db.remove_relation(source_id=data_id, target_id=related_data_id, relation_type=relation_type)
            if success:
                # Log event to Time Series Database
                self.time_series_db.log_event(event_type='relationship_removed', details={'source_id': data_id, 'target_id': related_data_id, 'relation_type': relation_type})
            return success
        except Exception as e:
            self.logger.error(f"Failed to remove relationship '{relation_type}' between '{data_id}' and '{related_data_id}': {e}", exc_info=True)
            return False

    # Caching with Redis (via SharedMemoryManager)

    def cache_vector_metadata(self, data_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Caches vector metadata in Redis for faster access.

        Args:
            data_id (str): The unique identifier of the data entry.
            metadata (Dict[str, Any]): The metadata to cache.

        Returns:
            bool: True if caching is successful, False otherwise.
        """
        try:
            metadata_str = json.dumps(metadata)
            self.shared_memory.cache_vector_metadata(data_id=data_id, metadata=metadata_str)
            self.logger.debug(f"Cached metadata for vector ID '{data_id}' in Redis.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cache metadata for vector ID '{data_id}': {e}", exc_info=True)
            return False

    def get_cached_vector_metadata(self, data_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached vector metadata from Redis.

        Args:
            data_id (str): The unique identifier of the data entry.

        Returns:
            Optional[Dict[str, Any]]: The cached metadata if found, else None.
        """
        try:
            metadata_str = self.shared_memory.get_cached_vector_metadata(data_id=data_id)
            if metadata_str:
                metadata = json.loads(metadata_str)
                self.logger.debug(f"Retrieved cached metadata for vector ID '{data_id}' from Redis.")
                return metadata
            else:
                self.logger.debug(f"No cached metadata found for vector ID '{data_id}' in Redis.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to retrieve cached metadata for vector ID '{data_id}': {e}", exc_info=True)
            return None

    # Additional Methods for Enhanced Functionality

    def get_embedding(self, data_id: str) -> Optional[List[float]]:
        """
        Retrieves the embedding vector for a given data ID from Pinecone.

        Args:
            data_id (str): The unique identifier of the data entry.

        Returns:
            Optional[List[float]]: The embedding vector if found, else None.
        """
        try:
            response = self.index.fetch(ids=[data_id])
            if data_id in response.vectors:
                embedding = response.vectors[data_id].values
                self.logger.debug(f"Retrieved embedding for data ID '{data_id}'.")
                return embedding
            else:
                self.logger.warning(f"No embedding found for data ID '{data_id}'.")
                return None
        except PineconeException as e:
            self.logger.error(f"Pinecone fetch error for ID '{data_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving embedding for data ID '{data_id}': {e}", exc_info=True)
            return None

    def list_all_vectors(self) -> Optional[List[str]]:
        """
        Lists all vector IDs in Pinecone.

        Returns:
            Optional[List[str]]: A list of all vector IDs if successful, else None.
        """
        try:
            # Pinecone does not provide a direct method to list all vector IDs.
            # This requires maintaining an external log or tracking system.
            pinecone_ids = self.shared_memory.get_all_pinecone_ids()
            if pinecone_ids:
                self.logger.debug(f"Retrieved {len(pinecone_ids)} vector IDs from shared memory.")
                return pinecone_ids
            else:
                self.logger.warning("No vector IDs found in shared memory.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to list all vectors: {e}", exc_info=True)
            return None

    # Shared Memory Integration

    def update_shared_memory_with_vector(self, data_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Updates the shared memory system with the vector's metadata.

        Args:
            data_id (str): The unique identifier of the data entry.
            metadata (Dict[str, Any]): The metadata to store.

        Returns:
            bool: True if update is successful, False otherwise.
        """
        try:
            metadata_str = json.dumps(metadata)
            self.shared_memory.cache_vector_metadata(data_id=data_id, metadata=metadata_str)
            self.logger.debug(f"Updated shared memory with metadata for vector ID '{data_id}'.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to update shared memory for vector ID '{data_id}': {e}", exc_info=True)
            return False

    def retrieve_shared_memory_vector(self, data_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves vector metadata from shared memory.

        Args:
            data_id (str): The unique identifier of the data entry.

        Returns:
            Optional[Dict[str, Any]]: The metadata if found, else None.
        """
        try:
            metadata = self.get_cached_vector_metadata(data_id=data_id)
            return metadata
        except Exception as e:
            self.logger.error(f"Failed to retrieve vector metadata from shared memory for ID '{data_id}': {e}", exc_info=True)
            return None

    # Suggested Additional Database Integration: Knowledge Graph (e.g., Neo4j)

    def integrate_with_knowledge_graph(self, data_id: str, related_data_ids: List[str], relation_type: str) -> bool:
        """
        Integrates vector data with a Knowledge Graph by establishing relationships with related data entries.

        Args:
            data_id (str): The unique identifier of the vector data entry.
            related_data_ids (List[str]): A list of related data entry identifiers.
            relation_type (str): The type of the relationship to establish.

        Returns:
            bool: True if integration is successful, False otherwise.
        """
        try:
            for related_id in related_data_ids:
                success = self.establish_relationship_with_graph_db(data_id=data_id, related_data_id=related_id, relation_type=relation_type)
                if not success:
                    self.logger.warning(f"Failed to establish relationship '{relation_type}' between '{data_id}' and '{related_id}'.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to integrate with Knowledge Graph for data ID '{data_id}': {e}", exc_info=True)
            return False

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

    # Additional Methods for Enhanced Functionality can be added here

