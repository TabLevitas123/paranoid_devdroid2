# databases/graph_db.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
import os
import json

from neo4j import GraphDatabase, Neo4jError
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy.exc import SQLAlchemyError

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.sqlite_db import SQLiteDatabase
from databases.vector_db import VectorDatabase
from databases.time_series_db import TimeSeriesDatabase
from shared_memory.shared_data_structures import SharedMemoryManager

class GraphDatabaseError(Exception):
    """Custom exception for GraphDatabaseManager-related errors."""
    pass

class GraphDatabaseManager:
    """
    Manages Neo4j graph database connections and operations.
    Integrates seamlessly with SQLiteDatabase, VectorDatabase, TimeSeriesDatabase, and SharedMemoryManager to support RAG in near-real-time.
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
                    cls._instance = super(GraphDatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the GraphDatabaseManager with necessary configurations, authentication, and integrations.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        # Setup logging
        self.logger = setup_logging('GraphDatabaseManager')

        # Load configurations
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()

        # Initialize SQLite, Vector, and Time Series Databases
        try:
            self.sqlite_db = SQLiteDatabase()
            self.vector_db = VectorDatabase()
            self.time_series_db = TimeSeriesDatabase()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024*1024*200)  # 200 MB
            self.logger.info("Integrated with SQLiteDatabase, VectorDatabase, TimeSeriesDatabase, and SharedMemoryManager successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with other databases or shared memory: {e}", exc_info=True)
            raise GraphDatabaseError(f"Failed to integrate with other databases or shared memory: {e}")

        # Initialize Neo4j
        try:
            neo4j_uri_encrypted = self.config_loader.get('NEO4J_URI_ENCRYPTED')
            neo4j_user_encrypted = self.config_loader.get('NEO4J_USER_ENCRYPTED')
            neo4j_password_encrypted = self.config_loader.get('NEO4J_PASSWORD_ENCRYPTED')

            if not all([neo4j_uri_encrypted, neo4j_user_encrypted, neo4j_password_encrypted]):
                self.logger.error("Neo4j URI, user, or password is missing in configuration.")
                raise GraphDatabaseError("Neo4j URI, user, or password is missing in configuration.")

            neo4j_uri = self.encryption_manager.decrypt_data(neo4j_uri_encrypted).decode('utf-8')
            neo4j_user = self.encryption_manager.decrypt_data(neo4j_user_encrypted).decode('utf-8')
            neo4j_password = self.encryption_manager.decrypt_data(neo4j_password_encrypted).decode('utf-8')

            self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password), encrypted=True)
            self.logger.info(f"Connected to Neo4j at '{neo4j_uri}' as user '{neo4j_user}'.")
        except Neo4jError as e:
            self.logger.error(f"Neo4j connection error: {e}", exc_info=True)
            raise GraphDatabaseError(f"Neo4j connection error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during Neo4j initialization: {e}", exc_info=True)
            raise GraphDatabaseError(f"Unexpected error during Neo4j initialization: {e}")

        # Initialize indexes and constraints
        try:
            with self.driver.session() as session:
                # Create uniqueness constraints
                session.write_transaction(self._create_constraints)
                self.logger.info("Neo4j constraints created successfully.")
        except Neo4jError as e:
            self.logger.error(f"Neo4j constraint creation error: {e}", exc_info=True)
            raise GraphDatabaseError(f"Neo4j constraint creation error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during Neo4j constraint creation: {e}", exc_info=True)
            raise GraphDatabaseError(f"Unexpected error during Neo4j constraint creation: {e}")

        self._initialized = True

    @staticmethod
    def _create_constraints(tx):
        """
        Creates necessary constraints in Neo4j to ensure data integrity.
        """
        try:
            tx.run("CREATE CONSTRAINT IF NOT EXISTS ON (u:User) ASSERT u.id IS UNIQUE")
            tx.run("CREATE CONSTRAINT IF NOT EXISTS ON (b:BugReport) ASSERT b.id IS UNIQUE")
            tx.run("CREATE CONSTRAINT IF NOT EXISTS ON (f:FeedbackEntry) ASSERT f.id IS UNIQUE")
        except Neo4jError as e:
            raise e

    @staticmethod
    def _transform_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms metadata to ensure compatibility with Neo4j property types.
        """
        transformed = {}
        for key, value in metadata.items():
            if isinstance(value, datetime):
                transformed[key] = value.isoformat()
            else:
                transformed[key] = value
        return transformed

    # CRUD Operations

    # User Operations

    def add_user_node(self, user_id: int, username: str, email: str) -> bool:
        """
        Creates a User node in Neo4j.

        Args:
            user_id (int): The unique identifier of the user.
            username (str): The username of the user.
            email (str): The email address of the user.

        Returns:
            bool: True if the node is created successfully, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._create_user_node, user_id, username, email)
                if result:
                    self.logger.info(f"User node created successfully for user ID '{user_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='user_node_created', details={'user_id': user_id})
                    return True
                else:
                    self.logger.warning(f"User node already exists for user ID '{user_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while creating user node for user ID '{user_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while creating user node for user ID '{user_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _create_user_node(tx, user_id: int, username: str, email: str) -> bool:
        """
        Transactional method to create a User node in Neo4j.

        Args:
            tx: The transaction context.
            user_id (int): The unique identifier of the user.
            username (str): The username of the user.
            email (str): The email address of the user.

        Returns:
            bool: True if the node was created, False if it already exists.
        """
        query = (
            "MERGE (u:User {id: $user_id}) "
            "ON CREATE SET u.username = $username, u.email = $email, u.created_at = datetime(), u.updated_at = datetime() "
            "ON MATCH SET u.updated_at = datetime() "
            "RETURN u"
        )
        result = tx.run(query, user_id=user_id, username=username, email=email)
        record = result.single()
        return record is not None

    def get_user_node(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a User node's properties from Neo4j.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: The user's properties if found, else None.
        """
        try:
            with self.driver.session() as session:
                user_data = session.read_transaction(self._fetch_user_node, user_id)
                if user_data:
                    self.logger.debug(f"Retrieved User node data for user ID '{user_id}'.")
                    return user_data
                else:
                    self.logger.warning(f"No User node found for user ID '{user_id}'.")
                    return None
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while fetching user node for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching user node for user ID '{user_id}': {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_user_node(tx, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Transactional method to fetch a User node's properties from Neo4j.

        Args:
            tx: The transaction context.
            user_id (int): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: The user's properties if found, else None.
        """
        query = "MATCH (u:User {id: $user_id}) RETURN u.username AS username, u.email AS email, u.created_at AS created_at, u.updated_at AS updated_at"
        result = tx.run(query, user_id=user_id)
        record = result.single()
        if record:
            return {
                'username': record['username'],
                'email': record['email'],
                'created_at': record['created_at'],
                'updated_at': record['updated_at']
            }
        return None

    def update_user_node_email(self, user_id: int, new_email: str) -> bool:
        """
        Updates a User node's email in Neo4j.

        Args:
            user_id (int): The unique identifier of the user.
            new_email (str): The new email address.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._update_user_email, user_id, new_email)
                if result:
                    self.logger.info(f"Updated email for User node with user ID '{user_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='user_email_updated_graph', details={'user_id': user_id, 'new_email': new_email})
                    return True
                else:
                    self.logger.warning(f"Failed to update email for User node with user ID '{user_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while updating user email for user ID '{user_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating user email for user ID '{user_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _update_user_email(tx, user_id: int, new_email: str) -> bool:
        """
        Transactional method to update a User node's email in Neo4j.

        Args:
            tx: The transaction context.
            user_id (int): The unique identifier of the user.
            new_email (str): The new email address.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        query = (
            "MATCH (u:User {id: $user_id}) "
            "SET u.email = $new_email, u.updated_at = datetime() "
            "RETURN u"
        )
        result = tx.run(query, user_id=user_id, new_email=new_email)
        record = result.single()
        return record is not None

    def delete_user_node(self, user_id: int) -> bool:
        """
        Deletes a User node from Neo4j.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if the deletion is successful, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._delete_user_node, user_id)
                if result:
                    self.logger.info(f"Deleted User node with user ID '{user_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='user_node_deleted', details={'user_id': user_id})
                    return True
                else:
                    self.logger.warning(f"No User node found to delete for user ID '{user_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while deleting user node for user ID '{user_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while deleting user node for user ID '{user_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _delete_user_node(tx, user_id: int) -> bool:
        """
        Transactional method to delete a User node from Neo4j.

        Args:
            tx: The transaction context.
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if the node was deleted, False otherwise.
        """
        query = "MATCH (u:User {id: $user_id}) DETACH DELETE u RETURN COUNT(u) AS count"
        result = tx.run(query, user_id=user_id)
        record = result.single()
        return record['count'] > 0

    # BugReport Operations

    def add_bug_report_node(self, bug_report_id: int, user_id: int, severity: str) -> bool:
        """
        Creates a BugReport node in Neo4j and establishes a relationship with the User node.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            user_id (int): The unique identifier of the user who reported the bug.
            severity (str): The severity level of the bug.

        Returns:
            bool: True if the node and relationship are created successfully, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._create_bug_report_node, bug_report_id, user_id, severity)
                if result:
                    self.logger.info(f"BugReport node created successfully for bug report ID '{bug_report_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='bug_report_node_created', details={'bug_report_id': bug_report_id, 'user_id': user_id, 'severity': severity})
                    return True
                else:
                    self.logger.warning(f"BugReport node already exists for bug report ID '{bug_report_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while creating BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while creating BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _create_bug_report_node(tx, bug_report_id: int, user_id: int, severity: str) -> bool:
        """
        Transactional method to create a BugReport node and establish a relationship with the User node in Neo4j.

        Args:
            tx: The transaction context.
            bug_report_id (int): The unique identifier of the bug report.
            user_id (int): The unique identifier of the user.
            severity (str): The severity level of the bug.

        Returns:
            bool: True if the node and relationship were created, False otherwise.
        """
        query = (
            "MERGE (b:BugReport {id: $bug_report_id}) "
            "ON CREATE SET b.severity = $severity, b.status = 'Open', b.created_at = datetime(), b.updated_at = datetime() "
            "ON MATCH SET b.updated_at = datetime() "
            "WITH b "
            "MATCH (u:User {id: $user_id}) "
            "MERGE (u)-[:REPORTED]->(b) "
            "RETURN b"
        )
        result = tx.run(query, bug_report_id=bug_report_id, user_id=user_id, severity=severity)
        record = result.single()
        return record is not None

    def get_bug_report_node(self, bug_report_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a BugReport node's properties from Neo4j.

        Args:
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            Optional[Dict[str, Any]]: The bug report's properties if found, else None.
        """
        try:
            with self.driver.session() as session:
                bug_data = session.read_transaction(self._fetch_bug_report_node, bug_report_id)
                if bug_data:
                    self.logger.debug(f"Retrieved BugReport node data for bug report ID '{bug_report_id}'.")
                    return bug_data
                else:
                    self.logger.warning(f"No BugReport node found for bug report ID '{bug_report_id}'.")
                    return None
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while fetching BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_bug_report_node(tx, bug_report_id: int) -> Optional[Dict[str, Any]]:
        """
        Transactional method to fetch a BugReport node's properties from Neo4j.

        Args:
            tx: The transaction context.
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            Optional[Dict[str, Any]]: The bug report's properties if found, else None.
        """
        query = "MATCH (b:BugReport {id: $bug_report_id}) RETURN b.severity AS severity, b.status AS status, b.created_at AS created_at, b.updated_at AS updated_at"
        result = tx.run(query, bug_report_id=bug_report_id)
        record = result.single()
        if record:
            return {
                'severity': record['severity'],
                'status': record['status'],
                'created_at': record['created_at'],
                'updated_at': record['updated_at']
            }
        return None

    def update_bug_report_node_status(self, bug_report_id: int, new_status: str, comments: Optional[str] = None) -> bool:
        """
        Updates a BugReport node's status in Neo4j.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            new_status (str): The new status ('Open', 'In Progress', 'Resolved', 'Closed').
            comments (Optional[str], optional): Additional comments or resolution details. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        valid_statuses = ['Open', 'In Progress', 'Resolved', 'Closed']
        if new_status not in valid_statuses:
            self.logger.error(f"Invalid status '{new_status}' provided for bug report ID '{bug_report_id}'.")
            return False

        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._update_bug_report_status, bug_report_id, new_status, comments)
                if result:
                    self.logger.info(f"Updated status for BugReport node with bug report ID '{bug_report_id}' to '{new_status}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='bug_report_status_updated_graph', details={'bug_report_id': bug_report_id, 'new_status': new_status})
                    return True
                else:
                    self.logger.warning(f"Failed to update status for BugReport node with bug report ID '{bug_report_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while updating BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _update_bug_report_status(tx, bug_report_id: int, new_status: str, comments: Optional[str]) -> bool:
        """
        Transactional method to update a BugReport node's status in Neo4j.

        Args:
            tx: The transaction context.
            bug_report_id (int): The unique identifier of the bug report.
            new_status (str): The new status.
            comments (Optional[str]): Additional comments.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        query = (
            "MATCH (b:BugReport {id: $bug_report_id}) "
            "SET b.status = $new_status, b.updated_at = datetime() "
            "WITH b "
            "SET b.comments = coalesce(b.comments, '') + $comments "
            "RETURN b"
        )
        result = tx.run(query, bug_report_id=bug_report_id, new_status=new_status, comments=comments or '')
        record = result.single()
        return record is not None

    def delete_bug_report_node(self, bug_report_id: int) -> bool:
        """
        Deletes a BugReport node from Neo4j.

        Args:
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            bool: True if the deletion is successful, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._delete_bug_report_node, bug_report_id)
                if result:
                    self.logger.info(f"Deleted BugReport node with bug report ID '{bug_report_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='bug_report_node_deleted', details={'bug_report_id': bug_report_id})
                    return True
                else:
                    self.logger.warning(f"No BugReport node found to delete for bug report ID '{bug_report_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while deleting BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while deleting BugReport node for bug report ID '{bug_report_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _delete_bug_report_node(tx, bug_report_id: int) -> bool:
        """
        Transactional method to delete a BugReport node from Neo4j.

        Args:
            tx: The transaction context.
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            bool: True if the node was deleted, False otherwise.
        """
        query = "MATCH (b:BugReport {id: $bug_report_id}) DETACH DELETE b RETURN COUNT(b) AS count"
        result = tx.run(query, bug_report_id=bug_report_id)
        record = result.single()
        return record['count'] > 0

    # FeedbackEntry Operations

    def add_feedback_entry_node(self, feedback_id: int, user_id: int, service_name: str, rating: float) -> bool:
        """
        Creates a FeedbackEntry node in Neo4j and establishes a relationship with the User node.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.
            user_id (int): The unique identifier of the user who gave the feedback.
            service_name (str): The name of the service being reviewed.
            rating (float): The rating given by the user.

        Returns:
            bool: True if the node and relationship are created successfully, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._create_feedback_entry_node, feedback_id, user_id, service_name, rating)
                if result:
                    self.logger.info(f"FeedbackEntry node created successfully for feedback ID '{feedback_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='feedback_entry_node_created', details={'feedback_id': feedback_id, 'user_id': user_id, 'service_name': service_name, 'rating': rating})
                    return True
                else:
                    self.logger.warning(f"FeedbackEntry node already exists for feedback ID '{feedback_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while creating FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while creating FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _create_feedback_entry_node(tx, feedback_id: int, user_id: int, service_name: str, rating: float) -> bool:
        """
        Transactional method to create a FeedbackEntry node and establish a relationship with the User node in Neo4j.

        Args:
            tx: The transaction context.
            feedback_id (int): The unique identifier of the feedback entry.
            user_id (int): The unique identifier of the user.
            service_name (str): The name of the service being reviewed.
            rating (float): The rating given by the user.

        Returns:
            bool: True if the node and relationship were created, False otherwise.
        """
        query = (
            "MERGE (f:FeedbackEntry {id: $feedback_id}) "
            "ON CREATE SET f.service_name = $service_name, f.rating = $rating, f.processed = False, f.response = '', f.created_at = datetime(), f.updated_at = datetime() "
            "ON MATCH SET f.updated_at = datetime() "
            "WITH f "
            "MATCH (u:User {id: $user_id}) "
            "MERGE (u)-[:GAVE_FEEDBACK]->(f) "
            "RETURN f"
        )
        result = tx.run(query, feedback_id=feedback_id, user_id=user_id, service_name=service_name, rating=rating)
        record = result.single()
        return record is not None

    def get_feedback_entry_node(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a FeedbackEntry node's properties from Neo4j.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            Optional[Dict[str, Any]]: The feedback entry's properties if found, else None.
        """
        try:
            with self.driver.session() as session:
                feedback_data = session.read_transaction(self._fetch_feedback_entry_node, feedback_id)
                if feedback_data:
                    self.logger.debug(f"Retrieved FeedbackEntry node data for feedback ID '{feedback_id}'.")
                    return feedback_data
                else:
                    self.logger.warning(f"No FeedbackEntry node found for feedback ID '{feedback_id}'.")
                    return None
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while fetching FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_feedback_entry_node(tx, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        Transactional method to fetch a FeedbackEntry node's properties from Neo4j.

        Args:
            tx: The transaction context.
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            Optional[Dict[str, Any]]: The feedback entry's properties if found, else None.
        """
        query = "MATCH (f:FeedbackEntry {id: $feedback_id}) RETURN f.service_name AS service_name, f.rating AS rating, f.processed AS processed, f.response AS response, f.created_at AS created_at, f.updated_at AS updated_at"
        result = tx.run(query, feedback_id=feedback_id)
        record = result.single()
        if record:
            return {
                'service_name': record['service_name'],
                'rating': record['rating'],
                'processed': record['processed'],
                'response': record['response'],
                'created_at': record['created_at'],
                'updated_at': record['updated_at']
            }
        return None

    def update_feedback_entry_node(self, feedback_id: int, new_rating: Optional[float] = None, new_comment: Optional[str] = None) -> bool:
        """
        Updates a FeedbackEntry node's rating and/or comment in Neo4j.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.
            new_rating (Optional[float], optional): The new rating to update. Defaults to None.
            new_comment (Optional[str], optional): The new comment to update. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._update_feedback_entry_node, feedback_id, new_rating, new_comment)
                if result:
                    self.logger.info(f"Updated FeedbackEntry node with feedback ID '{feedback_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='feedback_entry_node_updated', details={'feedback_id': feedback_id, 'new_rating': new_rating, 'new_comment': new_comment})
                    return True
                else:
                    self.logger.warning(f"Failed to update FeedbackEntry node with feedback ID '{feedback_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while updating FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _update_feedback_entry_node(tx, feedback_id: int, new_rating: Optional[float], new_comment: Optional[str]) -> bool:
        """
        Transactional method to update a FeedbackEntry node's properties in Neo4j.

        Args:
            tx: The transaction context.
            feedback_id (int): The unique identifier of the feedback entry.
            new_rating (Optional[float]): The new rating.
            new_comment (Optional[str]): The new comment.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        set_clauses = []
        parameters = {'feedback_id': feedback_id}
        if new_rating is not None:
            set_clauses.append("f.rating = $new_rating")
            parameters['new_rating'] = new_rating
        if new_comment is not None:
            set_clauses.append("f.comment = $new_comment")
            parameters['new_comment'] = new_comment

        if not set_clauses:
            return False  # Nothing to update

        set_clause = ", ".join(set_clauses) + ", f.updated_at = datetime()"

        query = f"""
            MATCH (f:FeedbackEntry {{id: $feedback_id}})
            SET {set_clause}
            RETURN f
        """

        result = tx.run(query, **parameters)
        record = result.single()
        return record is not None

    def delete_feedback_entry_node(self, feedback_id: int) -> bool:
        """
        Deletes a FeedbackEntry node from Neo4j.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            bool: True if the deletion is successful, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._delete_feedback_entry_node, feedback_id)
                if result:
                    self.logger.info(f"Deleted FeedbackEntry node with feedback ID '{feedback_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='feedback_entry_node_deleted', details={'feedback_id': feedback_id})
                    return True
                else:
                    self.logger.warning(f"No FeedbackEntry node found to delete for feedback ID '{feedback_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while deleting FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while deleting FeedbackEntry node for feedback ID '{feedback_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _delete_feedback_entry_node(tx, feedback_id: int) -> bool:
        """
        Transactional method to delete a FeedbackEntry node from Neo4j.

        Args:
            tx: The transaction context.
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            bool: True if the node was deleted, False otherwise.
        """
        query = "MATCH (f:FeedbackEntry {id: $feedback_id}) DETACH DELETE f RETURN COUNT(f) AS count"
        result = tx.run(query, feedback_id=feedback_id)
        record = result.single()
        return record['count'] > 0

    # Relationship Management

    def add_relationship(self, source_id: str, target_id: str, relation_type: str) -> bool:
        """
        Adds a relationship between two nodes in Neo4j.

        Args:
            source_id (str): The unique identifier of the source node.
            target_id (str): The unique identifier of the target node.
            relation_type (str): The type of the relationship (e.g., 'RELATED_TO').

        Returns:
            bool: True if the relationship is added successfully, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._create_relationship, source_id, target_id, relation_type)
                if result:
                    self.logger.info(f"Relationship '{relation_type}' created between '{source_id}' and '{target_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='relationship_created', details={'source_id': source_id, 'target_id': target_id, 'relation_type': relation_type})
                    return True
                else:
                    self.logger.warning(f"Relationship '{relation_type}' already exists between '{source_id}' and '{target_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while creating relationship '{relation_type}' between '{source_id}' and '{target_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while creating relationship '{relation_type}' between '{source_id}' and '{target_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _create_relationship(tx, source_id: str, target_id: str, relation_type: str) -> bool:
        """
        Transactional method to create a relationship between two nodes in Neo4j.

        Args:
            tx: The transaction context.
            source_id (str): The unique identifier of the source node.
            target_id (str): The unique identifier of the target node.
            relation_type (str): The type of the relationship.

        Returns:
            bool: True if the relationship was created, False otherwise.
        """
        query = (
            f"MATCH (a),(b) WHERE a.id = $source_id AND b.id = $target_id "
            f"MERGE (a)-[r:{relation_type}]->(b) "
            f"RETURN r"
        )
        result = tx.run(query, source_id=source_id, target_id=target_id)
        record = result.single()
        return record is not None

    def remove_relationship(self, source_id: str, target_id: str, relation_type: str) -> bool:
        """
        Removes a relationship between two nodes in Neo4j.

        Args:
            source_id (str): The unique identifier of the source node.
            target_id (str): The unique identifier of the target node.
            relation_type (str): The type of the relationship to remove.

        Returns:
            bool: True if the relationship is removed successfully, False otherwise.
        """
        try:
            with self.driver.session() as session:
                result = session.write_transaction(self._delete_relationship, source_id, target_id, relation_type)
                if result:
                    self.logger.info(f"Relationship '{relation_type}' removed between '{source_id}' and '{target_id}'.")
                    # Log event to Time Series Database
                    self.time_series_db.log_event(event_type='relationship_removed', details={'source_id': source_id, 'target_id': target_id, 'relation_type': relation_type})
                    return True
                else:
                    self.logger.warning(f"No relationship '{relation_type}' found between '{source_id}' and '{target_id}'.")
                    return False
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while removing relationship '{relation_type}' between '{source_id}' and '{target_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while removing relationship '{relation_type}' between '{source_id}' and '{target_id}': {e}", exc_info=True)
            return False

    @staticmethod
    def _delete_relationship(tx, source_id: str, target_id: str, relation_type: str) -> bool:
        """
        Transactional method to delete a relationship between two nodes in Neo4j.

        Args:
            tx: The transaction context.
            source_id (str): The unique identifier of the source node.
            target_id (str): The unique identifier of the target node.
            relation_type (str): The type of the relationship to remove.

        Returns:
            bool: True if the relationship was deleted, False otherwise.
        """
        query = (
            f"MATCH (a)-[r:{relation_type}]->(b) WHERE a.id = $source_id AND b.id = $target_id "
            f"DELETE r RETURN COUNT(r) AS count"
        )
        result = tx.run(query, source_id=source_id, target_id=target_id)
        record = result.single()
        return record['count'] > 0

    # Advanced Queries

    def find_related_users(self, service_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Finds all users who have given feedback for a specific service.

        Args:
            service_name (str): The name of the service.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of users if successful, else None.
        """
        try:
            with self.driver.session() as session:
                users = session.read_transaction(self._fetch_users_by_service_feedback, service_name)
                if users:
                    self.logger.debug(f"Found {len(users)} users who gave feedback for service '{service_name}'.")
                    return users
                else:
                    self.logger.warning(f"No users found who gave feedback for service '{service_name}'.")
                    return None
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while finding users for service '{service_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while finding users for service '{service_name}': {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_users_by_service_feedback(tx, service_name: str) -> List[Dict[str, Any]]:
        """
        Transactional method to retrieve users who gave feedback for a specific service.

        Args:
            tx: The transaction context.
            service_name (str): The name of the service.

        Returns:
            List[Dict[str, Any]]: A list of users.
        """
        query = (
            "MATCH (u:User)-[:GAVE_FEEDBACK]->(f:FeedbackEntry {service_name: $service_name}) "
            "RETURN u.id AS id, u.username AS username, u.email AS email, u.created_at AS created_at, u.updated_at AS updated_at"
        )
        result = tx.run(query, service_name=service_name)
        return [record.data() for record in result]

    def find_related_bug_reports(self, severity: str) -> Optional[List[Dict[str, Any]]]:
        """
        Finds all bug reports with a specific severity level.

        Args:
            severity (str): The severity level of the bug reports.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of bug reports if successful, else None.
        """
        try:
            with self.driver.session() as session:
                bug_reports = session.read_transaction(self._fetch_bug_reports_by_severity, severity)
                if bug_reports:
                    self.logger.debug(f"Found {len(bug_reports)} bug reports with severity '{severity}'.")
                    return bug_reports
                else:
                    self.logger.warning(f"No bug reports found with severity '{severity}'.")
                    return None
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while finding bug reports with severity '{severity}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while finding bug reports with severity '{severity}': {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_bug_reports_by_severity(tx, severity: str) -> List[Dict[str, Any]]:
        """
        Transactional method to retrieve bug reports by severity level.

        Args:
            tx: The transaction context.
            severity (str): The severity level.

        Returns:
            List[Dict[str, Any]]: A list of bug reports.
        """
        query = (
            "MATCH (b:BugReport {severity: $severity}) "
            "RETURN b.id AS id, b.status AS status, b.created_at AS created_at, b.updated_at AS updated_at"
        )
        result = tx.run(query, severity=severity)
        return [record.data() for record in result]

    # RAG Operations

    def perform_rag(self, query_text: str, top_k: int = 5) -> Optional[Dict[str, Any]]:
        """
        Performs Retrieval-Augmented Generation by searching for similar vectors and retrieving their metadata from Neo4j.

        Args:
            query_text (str): The query text to perform RAG on.
            top_k (int, optional): Number of top similar results to retrieve. Defaults to 5.

        Returns:
            Optional[Dict[str, Any]]: The aggregated data from similar vectors if successful, else None.
        """
        try:
            # Utilize VectorDatabase to perform similarity search
            similar_vectors = self.vector_db.search_similar(query_text=query_text, top_k=top_k)
            if not similar_vectors:
                self.logger.warning(f"No similar vectors found for query: '{query_text}'.")
                return None

            rag_result = {
                'query': query_text,
                'similar_vectors': similar_vectors,
                'related_entities': []
            }

            # Enrich RAG result with data from Neo4j
            for vector in similar_vectors:
                metadata = vector.get('metadata', {})
                data_type = metadata.get('type')
                data_id = metadata.get(f"{data_type}_id")
                if data_type == 'user':
                    user_data = self.sqlite_db.get_user_by_id(data_id)
                    if user_data:
                        rag_result.setdefault('users', []).append(user_data)
                elif data_type == 'bug_report':
                    bug_data = self.sqlite_db.get_bug_report(data_id)
                    if bug_data:
                        rag_result.setdefault('bug_reports', []).append(bug_data)
                elif data_type == 'feedback':
                    feedback_data = self.sqlite_db.get_feedback_entry(data_id)
                    if feedback_data:
                        rag_result.setdefault('feedback_entries', []).append(feedback_data)
                else:
                    self.logger.warning(f"Unknown data type '{data_type}' in vector metadata.")

            # Fetch related entities from Neo4j
            for vector in similar_vectors:
                metadata = vector.get('metadata', {})
                data_type = metadata.get('type')
                data_id = metadata.get(f"{data_type}_id")
                if data_type == 'bug_report':
                    related_users = self.find_related_users(service_name=metadata.get('severity', ''))
                    if related_users:
                        rag_result['related_entities'].extend(related_users)
                elif data_type == 'feedback':
                    related_users = self.find_related_users(service_name=metadata.get('service_name', ''))
                    if related_users:
                        rag_result['related_entities'].extend(related_users)

            # Log RAG operation to Time Series Database
            self.time_series_db.log_event(event_type='rag_performed', details={'query_text': query_text, 'top_k': top_k, 'results_count': len(similar_vectors)})

            self.logger.debug(f"RAG operation completed for query: '{query_text}'.")
            return rag_result
        except Exception as e:
            self.logger.error(f"Failed to perform RAG operation for query '{query_text}': {e}", exc_info=True)
            return None

    # Additional Utility Methods

    def get_all_user_nodes(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all User nodes from Neo4j.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of users if successful, else None.
        """
        try:
            with self.driver.session() as session:
                users = session.read_transaction(self._fetch_all_users)
                self.logger.debug(f"Retrieved {len(users)} User nodes from Neo4j.")
                return users
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while retrieving all User nodes: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving all User nodes: {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_all_users(tx) -> List[Dict[str, Any]]:
        """
        Transactional method to retrieve all User nodes from Neo4j.

        Args:
            tx: The transaction context.

        Returns:
            List[Dict[str, Any]]: A list of users.
        """
        query = "MATCH (u:User) RETURN u.id AS id, u.username AS username, u.email AS email, u.created_at AS created_at, u.updated_at AS updated_at"
        result = tx.run(query)
        return [record.data() for record in result]

    def get_all_bug_reports(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all BugReport nodes from Neo4j.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of bug reports if successful, else None.
        """
        try:
            with self.driver.session() as session:
                bugs = session.read_transaction(self._fetch_all_bug_reports)
                self.logger.debug(f"Retrieved {len(bugs)} BugReport nodes from Neo4j.")
                return bugs
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while retrieving all BugReport nodes: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving all BugReport nodes: {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_all_bug_reports(tx) -> List[Dict[str, Any]]:
        """
        Transactional method to retrieve all BugReport nodes from Neo4j.

        Args:
            tx: The transaction context.

        Returns:
            List[Dict[str, Any]]: A list of bug reports.
        """
        query = "MATCH (b:BugReport) RETURN b.id AS id, b.severity AS severity, b.status AS status, b.created_at AS created_at, b.updated_at AS updated_at"
        result = tx.run(query)
        return [record.data() for record in result]

    def get_all_feedback_entry_nodes(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all FeedbackEntry nodes from Neo4j.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of feedback entries if successful, else None.
        """
        try:
            with self.driver.session() as session:
                feedbacks = session.read_transaction(self._fetch_all_feedback_entries)
                self.logger.debug(f"Retrieved {len(feedbacks)} FeedbackEntry nodes from Neo4j.")
                return feedbacks
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while retrieving all FeedbackEntry nodes: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving all FeedbackEntry nodes: {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_all_feedback_entries(tx) -> List[Dict[str, Any]]:
        """
        Transactional method to retrieve all FeedbackEntry nodes from Neo4j.

        Args:
            tx: The transaction context.

        Returns:
            List[Dict[str, Any]]: A list of feedback entries.
        """
        query = "MATCH (f:FeedbackEntry) RETURN f.id AS id, f.service_name AS service_name, f.rating AS rating, f.processed AS processed, f.response AS response, f.created_at AS created_at, f.updated_at AS updated_at"
        result = tx.run(query)
        return [record.data() for record in result]

    def find_users_by_feedback_service(self, service_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Finds all users who have given feedback for a specific service.

        Args:
            service_name (str): The name of the service.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of users if successful, else None.
        """
        try:
            with self.driver.session() as session:
                users = session.read_transaction(self._fetch_users_by_service_feedback, service_name)
                self.logger.debug(f"Found {len(users)} users who gave feedback for service '{service_name}'.")
                return users
        except Neo4jError as e:
            self.logger.error(f"Neo4j error while finding users for service '{service_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while finding users for service '{service_name}': {e}", exc_info=True)
            return None

    @staticmethod
    def _fetch_users_by_service_feedback(tx, service_name: str) -> List[Dict[str, Any]]:
        """
        Transactional method to retrieve users who gave feedback for a specific service.

        Args:
            tx: The transaction context.
            service_name (str): The name of the service.

        Returns:
            List[Dict[str, Any]]: A list of users.
        """
        query = (
            "MATCH (u:User)-[:GAVE_FEEDBACK]->(f:FeedbackEntry {service_name: $service_name}) "
            "RETURN u.id AS id, u.username AS username, u.email AS email, u.created_at AS created_at, u.updated_at AS updated_at"
        )
        result = tx.run(query, service_name=service_name)
        return [record.data() for record in result]

    # Integration with VectorDatabase and SQLiteDatabase

    def link_bug_report_with_feedback(self, bug_report_id: int, feedback_id: int) -> bool:
        """
        Establishes a relationship between a BugReport node and a FeedbackEntry node in Neo4j.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            bool: True if the relationship is created successfully, False otherwise.
        """
        source_id = f"bug_report_{bug_report_id}"
        target_id = f"feedback_{feedback_id}"
        relation_type = "HAS_FEEDBACK"
        return self.add_relationship(source_id, target_id, relation_type)

    def unlink_bug_report_with_feedback(self, bug_report_id: int, feedback_id: int) -> bool:
        """
        Removes the relationship between a BugReport node and a FeedbackEntry node in Neo4j.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            bool: True if the relationship is removed successfully, False otherwise.
        """
        source_id = f"bug_report_{bug_report_id}"
        target_id = f"feedback_{feedback_id}"
        relation_type = "HAS_FEEDBACK"
        return self.remove_relationship(source_id, target_id, relation_type)

    # Shared Memory Operations

    def retrieve_shared_memory_data(self, data_type: str, data_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves data from the shared memory system.

        Args:
            data_type (str): The type of data ('user', 'bug_report', 'feedback_entry').
            data_id (int): The unique identifier of the data entry.

        Returns:
            Optional[Dict[str, Any]]: The data if found, else None.
        """
        try:
            if data_type == 'user':
                return self.shared_memory.get_user(data_id=data_id)
            elif data_type == 'bug_report':
                return self.shared_memory.get_bug_report(data_id=data_id)
            elif data_type == 'feedback_entry':
                return self.shared_memory.get_feedback_entry(data_id=data_id)
            else:
                self.logger.error(f"Invalid data type '{data_type}' requested from shared memory.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to retrieve data from shared memory: {e}", exc_info=True)
            return None

    # Performance and Security Enhancements

    def ensure_relationship_integrity(self) -> bool:
        """
        Ensures that all relationships in Neo4j are consistent with the data in SQLiteDatabase and VectorDatabase.

        Returns:
            bool: True if integrity is maintained, False otherwise.
        """
        try:
            # Example: Verify that every BugReport node has a corresponding entry in SQLiteDatabase
            with self.driver.session() as session:
                bug_reports_in_graph = session.read_transaction(self._fetch_all_bug_report_ids)
                bug_reports_in_sqlite = {f"bug_report_{bug.id}" for bug in self.sqlite_db.get_all_bug_reports() or []}

                missing_in_sqlite = bug_reports_in_graph - bug_reports_in_sqlite
                if missing_in_sqlite:
                    self.logger.warning(f"Found {len(missing_in_sqlite)} BugReport nodes in Neo4j missing in SQLiteDatabase.")
                    # Optionally, remove these nodes or re-index them
                    for data_id in missing_in_sqlite:
                        bug_report_id = int(data_id.split('_')[2])
                        self.delete_bug_report_node(bug_report_id)
                else:
                    self.logger.info("All BugReport nodes in Neo4j are consistent with SQLiteDatabase.")

                # Similarly, verify FeedbackEntry nodes
                feedback_in_graph = session.read_transaction(self._fetch_all_feedback_entry_ids)
                feedback_in_sqlite = {f"feedback_{fb.id}" for fb in self.sqlite_db.get_all_feedback_entries() or []}

                missing_feedback = feedback_in_graph - feedback_in_sqlite
                if missing_feedback:
                    self.logger.warning(f"Found {len(missing_feedback)} FeedbackEntry nodes in Neo4j missing in SQLiteDatabase.")
                    for data_id in missing_feedback:
                        feedback_id = int(data_id.split('_')[1])
                        self.delete_feedback_entry_node(feedback_id)
                else:
                    self.logger.info("All FeedbackEntry nodes in Neo4j are consistent with SQLiteDatabase.")

                return True
        except Exception as e:
            self.logger.error(f"Failed to ensure relationship integrity: {e}", exc_info=True)
            return False

    @staticmethod
    def _fetch_all_bug_report_ids(tx) -> set:
        """
        Transactional method to fetch all BugReport node IDs from Neo4j.

        Args:
            tx: The transaction context.

        Returns:
            set: A set of BugReport node IDs.
        """
        query = "MATCH (b:BugReport) RETURN b.id AS id"
        result = tx.run(query)
        return {record['id'] for record in result}

    @staticmethod
    def _fetch_all_feedback_entry_ids(tx) -> set:
        """
        Transactional method to fetch all FeedbackEntry node IDs from Neo4j.

        Args:
            tx: The transaction context.

        Returns:
            set: A set of FeedbackEntry node IDs.
        """
        query = "MATCH (f:FeedbackEntry) RETURN f.id AS id"
        result = tx.run(query)
        return {record['id'] for record in result}

    # Additional Utility Methods

    def refresh_integrations(self) -> bool:
        """
        Refreshes all integrations by re-indexing data from SQLiteDatabase to VectorDatabase and ensuring GraphDatabase consistency.

        Returns:
            bool: True if refresh is successful, False otherwise.
        """
        try:
            # Re-index all users in VectorDatabase
            users = self.sqlite_db.get_all_users()
            if users:
                for user in users:
                    self.vector_db.index_user(user_id=user['id'], username=user['username'], email=user['email'])
                    self.add_user_node(user_id=user['id'], username=user['username'], email=user['email'])
                    self.shared_memory.update_user(user_id=user['id'], username=user['username'], email=user['email'])

            # Re-index all bug reports in VectorDatabase
            bug_reports = self.sqlite_db.get_all_bug_reports()
            if bug_reports:
                for bug in bug_reports:
                    self.vector_db.index_bug_report(bug_report_id=bug['id'], title=bug['title'], description=bug['description'], severity=bug['severity'])
                    self.add_bug_report_node(bug_report_id=bug['id'], user_id=bug['user_id'], severity=bug['severity'])
                    self.shared_memory.add_bug_report(bug_report_id=bug['id'], title=bug['title'], description=bug['description'], severity=bug['severity'], status=bug['status'])

            # Re-index all feedback entries in VectorDatabase
            feedback_entries = self.sqlite_db.get_all_feedback_entries()
            if feedback_entries:
                for feedback in feedback_entries:
                    self.vector_db.index_feedback(feedback_id=feedback['id'], service_name=feedback['service_name'], rating=feedback['rating'], comment=feedback['comment'])
                    self.add_feedback_entry_node(feedback_id=feedback['id'], user_id=feedback['user_id'], service_name=feedback['service_name'], rating=feedback['rating'])
                    self.shared_memory.add_feedback_entry(feedback_id=feedback['id'], service_name=feedback['service_name'], rating=feedback['rating'], comment=feedback['comment'], processed=feedback['processed'])

            # Ensure relationship integrity in GraphDatabase
            self.ensure_relationship_integrity()

            self.logger.info("All integrations refreshed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to refresh integrations: {e}", exc_info=True)
            return False

    # Cleanup and Resource Management

    def close(self):
        """
        Closes the Neo4j driver connection and all integrations.
        """
        try:
            self.driver.close()
            self.logger.info("Neo4j driver closed successfully.")
        except Neo4jError as e:
            self.logger.error(f"Failed to close Neo4j driver: {e}", exc_info=True)
            raise GraphDatabaseError(f"Failed to close Neo4j driver: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error while closing Neo4j driver: {e}", exc_info=True)
            raise GraphDatabaseError(f"Unexpected error while closing Neo4j driver: {e}")

        try:
            self.sqlite_db.dispose_engine()
            self.logger.info("SQLiteDatabase disposed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to dispose SQLiteDatabase: {e}", exc_info=True)
            raise GraphDatabaseError(f"Failed to dispose SQLiteDatabase: {e}")

        try:
            self.vector_db.close()
            self.logger.info("VectorDatabase closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close VectorDatabase: {e}", exc_info=True)
            raise GraphDatabaseError(f"Failed to close VectorDatabase: {e}")

        try:
            self.time_series_db.close()
            self.logger.info("TimeSeriesDatabase closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close TimeSeriesDatabase: {e}", exc_info=True)
            raise GraphDatabaseError(f"Failed to close TimeSeriesDatabase: {e}")

        try:
            self.shared_memory.close()
            self.logger.info("SharedMemoryManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close SharedMemoryManager: {e}", exc_info=True)
            raise GraphDatabaseError(f"Failed to close SharedMemoryManager: {e}")

    # Integration with Potential Additional Database (e.g., Knowledge Graph)

    def integrate_with_knowledge_graph(self, data_id: str, related_data_ids: List[str], relation_type: str) -> bool:
        """
        Integrates data with an additional Knowledge Graph by establishing relationships with related data entries.

        Args:
            data_id (str): The unique identifier of the data entry.
            related_data_ids (List[str]): A list of related data entry identifiers.
            relation_type (str): The type of the relationship to establish.

        Returns:
            bool: True if integration is successful, False otherwise.
        """
        try:
            for related_id in related_data_ids:
                success = self.add_relationship(source_id=data_id, target_id=related_id, relation_type=relation_type)
                if not success:
                    self.logger.warning(f"Failed to establish relationship '{relation_type}' between '{data_id}' and '{related_id}'.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to integrate with Knowledge Graph for data ID '{data_id}': {e}", exc_info=True)
            return False

    # Additional Methods for Enhanced Functionality can be added here as needed

