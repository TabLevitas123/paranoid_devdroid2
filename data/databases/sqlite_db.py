# databases/sqlite_db.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base, relationship
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.engine.url import URL
from datetime import datetime
import os
import json

from contextlib import contextmanager

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.vector_db import VectorDatabase
from databases.graph_db import GraphDatabaseManager
from shared_memory.shared_data_structures import SharedMemoryManager

# Define the declarative base
Base = declarative_base()

class SQLiteDatabaseError(Exception):
    """Custom exception for SQLiteDatabase-related errors."""
    pass

class SQLiteDatabase:
    """
    Manages SQLite database connections and operations.
    Integrates seamlessly with VectorDatabase and GraphDatabaseManager to support RAG in near-real-time.
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
                    cls._instance = super(SQLiteDatabase, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the SQLiteDatabase with necessary configurations and authentication.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        # Setup logging
        self.logger = setup_logging('SQLiteDatabase')

        # Load configurations
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()

        # Database configuration
        self.db_path = self.config_loader.get('SQLITE_DB_PATH', 'data/database.sqlite')
        self.db_url = self._build_db_url(self.db_path)

        # Ensure the database directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # Initialize SQLAlchemy engine and session
        try:
            self.engine = create_engine(
                self.db_url,
                connect_args={'check_same_thread': False},
                pool_pre_ping=True,
                echo=False  # Disable SQLAlchemy logging; use our logger instead
            )
            self.SessionFactory = scoped_session(sessionmaker(bind=self.engine))
            self.logger.info(f"SQLite engine created successfully at '{self.db_path}'.")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to create SQLite engine: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Failed to create SQLite engine: {e}")

        # Initialize database tables
        try:
            Base.metadata.create_all(self.engine)
            self.logger.info("All SQLite database tables created successfully.")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to create SQLite tables: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Failed to create SQLite tables: {e}")

        # Initialize integrations with Vector and Graph Databases
        try:
            self.vector_db = VectorDatabase()
            self.graph_db = GraphDatabaseManager()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024*1024*200)  # 200 MB
            self.logger.info("Integrated with VectorDatabase, GraphDatabaseManager, and SharedMemoryManager successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with other databases or shared memory: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Failed to integrate with other databases or shared memory: {e}")

        self._initialized = True

    def _build_db_url(self, db_path: str) -> str:
        """
        Builds the SQLAlchemy database URL for SQLite.

        Args:
            db_path (str): The file path to the SQLite database.

        Returns:
            str: The SQLite database URL.
        """
        return f"sqlite:///{db_path}"

    @contextmanager
    def get_session(self):
        """
        Provides a transactional scope around a series of operations.

        Usage:
            with sqlite_db.get_session() as session:
                # Perform database operations
        """
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.error(f"Session rollback due to error: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Session rollback due to error: {e}")
        except Exception as e:
            session.rollback()
            self.logger.error(f"Unexpected error during session: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Unexpected error during session: {e}")
        finally:
            session.close()

    # ORM Models

    class User(Base):
        __tablename__ = 'users'

        id = Column(Integer, primary_key=True, autoincrement=True)
        username = Column(String(50), unique=True, nullable=False, index=True)
        email = Column(String(120), unique=True, nullable=False, index=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        # Relationships
        bug_reports = relationship("BugReport", back_populates="user", cascade="all, delete-orphan")
        feedback_entries = relationship("FeedbackEntry", back_populates="user", cascade="all, delete-orphan")

    class BugReport(Base):
        __tablename__ = 'bug_reports'

        id = Column(Integer, primary_key=True, autoincrement=True)
        user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
        title = Column(String(255), nullable=False)
        description = Column(Text, nullable=False)
        severity = Column(String(50), nullable=False)
        status = Column(String(50), default='Open', nullable=False, index=True)
        reported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
        resolved_at = Column(DateTime, nullable=True)
        comments = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        # Relationships
        user = relationship("User", back_populates="bug_reports")

        # Indexes
        __table_args__ = (
            Index('idx_bug_severity', 'severity'),
            Index('idx_bug_status', 'status'),
        )

    class FeedbackEntry(Base):
        __tablename__ = 'feedback_entries'

        id = Column(Integer, primary_key=True, autoincrement=True)
        user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
        service_name = Column(String(100), nullable=False, index=True)
        rating = Column(Float, nullable=False)
        comment = Column(Text, nullable=True)
        submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
        processed = Column(Boolean, default=False, nullable=False, index=True)
        response = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        # Relationships
        user = relationship("User", back_populates="feedback_entries")

        # Indexes
        __table_args__ = (
            Index('idx_feedback_service', 'service_name'),
            Index('idx_feedback_processed', 'processed'),
        )

    # CRUD Operations

    # User Operations

    def add_user(self, username: str, email: str) -> Optional[int]:
        """
        Adds a new user to the database.

        Args:
            username (str): The username of the user.
            email (str): The email address of the user.

        Returns:
            Optional[int]: The user ID if added successfully, else None.
        """
        with self.get_session() as session:
            try:
                new_user = self.User(username=username, email=email)
                session.add(new_user)
                session.flush()  # Flush to assign an ID
                user_id = new_user.id
                self.logger.info(f"Added new user '{username}' with ID '{user_id}'.")

                # Integrate with Vector and Graph Databases
                self.vector_db.index_user(user_id=user_id, username=username, email=email)
                self.graph_db.add_user_node(user_id=user_id, username=username, email=email)
                self.shared_memory.update_user(user_id=user_id, username=username, email=email)

                return user_id
            except IntegrityError as e:
                self.logger.error(f"Integrity error while adding user '{username}': {e}", exc_info=True)
                return None
            except Exception as e:
                self.logger.error(f"Unexpected error while adding user '{username}': {e}", exc_info=True)
                return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a user's details by their ID.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: The user's details if found, else None.
        """
        with self.get_session() as session:
            try:
                user = session.query(self.User).filter(self.User.id == user_id).first()
                if user:
                    user_data = {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'created_at': user.created_at.isoformat(),
                        'updated_at': user.updated_at.isoformat()
                    }
                    self.logger.debug(f"Retrieved user data for ID '{user_id}'.")
                    return user_data
                else:
                    self.logger.warning(f"No user found with ID '{user_id}'.")
                    return None
            except Exception as e:
                self.logger.error(f"Unexpected error while retrieving user ID '{user_id}': {e}", exc_info=True)
                return None

    def update_user_email(self, user_id: int, new_email: str) -> bool:
        """
        Updates a user's email address.

        Args:
            user_id (int): The unique identifier of the user.
            new_email (str): The new email address.

        Returns:
            bool: True if updated successfully, False otherwise.
        """
        with self.get_session() as session:
            try:
                user = session.query(self.User).filter(self.User.id == user_id).first()
                if user:
                    user.email = new_email
                    self.logger.info(f"Updated email for user ID '{user_id}' to '{new_email}'.")

                    # Update integrations
                    self.vector_db.update_user_email(user_id=user_id, new_email=new_email)
                    self.graph_db.update_user_node_email(user_id=user_id, new_email=new_email)
                    self.shared_memory.update_user_email(user_id=user_id, new_email=new_email)

                    return True
                else:
                    self.logger.warning(f"No user found with ID '{user_id}'.")
                    return False
            except IntegrityError as e:
                self.logger.error(f"Integrity error while updating email for user ID '{user_id}': {e}", exc_info=True)
                return False
            except Exception as e:
                self.logger.error(f"Unexpected error while updating email for user ID '{user_id}': {e}", exc_info=True)
                return False

    def delete_user(self, user_id: int) -> bool:
        """
        Deletes a user from the database.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if deleted successfully, False otherwise.
        """
        with self.get_session() as session:
            try:
                user = session.query(self.User).filter(self.User.id == user_id).first()
                if user:
                    session.delete(user)
                    self.logger.info(f"Deleted user with ID '{user_id}'.")

                    # Update integrations
                    self.vector_db.delete_user(user_id=user_id)
                    self.graph_db.delete_user_node(user_id=user_id)
                    self.shared_memory.delete_user(user_id=user_id)

                    return True
                else:
                    self.logger.warning(f"No user found with ID '{user_id}'.")
                    return False
            except Exception as e:
                self.logger.error(f"Unexpected error while deleting user ID '{user_id}': {e}", exc_info=True)
                return False

    # BugReport Operations

    def submit_bug_report(self, user_id: int, title: str, description: str, severity: str) -> Optional[int]:
        """
        Submits a bug report from a user.

        Args:
            user_id (int): The unique identifier of the user.
            title (str): The title of the bug report.
            description (str): The detailed description of the bug.
            severity (str): The severity level of the bug ('Low', 'Medium', 'High', 'Critical').

        Returns:
            Optional[int]: The bug report ID if submission is successful, else None.
        """
        valid_severities = ['Low', 'Medium', 'High', 'Critical']
        if severity not in valid_severities:
            self.logger.error(f"Invalid severity level '{severity}' provided.")
            return None

        with self.get_session() as session:
            try:
                # Verify user exists
                user = session.query(self.User).filter(self.User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                bug_report = self.BugReport(
                    user_id=user_id,
                    title=title,
                    description=description,
                    severity=severity,
                    status='Open',
                    reported_at=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(bug_report)
                session.flush()  # Assign an ID
                bug_report_id = bug_report.id
                self.logger.info(f"Bug report submitted successfully with ID '{bug_report_id}' by user ID '{user_id}'.")

                # Integrate with Vector and Graph Databases
                self.vector_db.index_bug_report(bug_report_id=bug_report_id, title=title, description=description, severity=severity)
                self.graph_db.add_bug_report_node(bug_report_id=bug_report_id, user_id=user_id, severity=severity)
                self.shared_memory.add_bug_report(bug_report_id=bug_report_id, title=title, description=description, severity=severity, status='Open')

                return bug_report_id
            except IntegrityError as e:
                self.logger.error(f"Integrity error while submitting bug report: {e}", exc_info=True)
                return None
            except Exception as e:
                self.logger.error(f"Unexpected error while submitting bug report: {e}", exc_info=True)
                return None

    def get_bug_report(self, bug_report_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a bug report's details by its ID.

        Args:
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            Optional[Dict[str, Any]]: The bug report details if found, else None.
        """
        with self.get_session() as session:
            try:
                bug_report = session.query(self.BugReport).filter(self.BugReport.id == bug_report_id).first()
                if bug_report:
                    report_data = {
                        'id': bug_report.id,
                        'user_id': bug_report.user_id,
                        'title': bug_report.title,
                        'description': bug_report.description,
                        'severity': bug_report.severity,
                        'status': bug_report.status,
                        'reported_at': bug_report.reported_at.isoformat(),
                        'resolved_at': bug_report.resolved_at.isoformat() if bug_report.resolved_at else None,
                        'comments': bug_report.comments,
                        'created_at': bug_report.created_at.isoformat(),
                        'updated_at': bug_report.updated_at.isoformat()
                    }
                    self.logger.debug(f"Retrieved bug report data for ID '{bug_report_id}'.")
                    return report_data
                else:
                    self.logger.warning(f"No bug report found with ID '{bug_report_id}'.")
                    return None
            except Exception as e:
                self.logger.error(f"Unexpected error while retrieving bug report ID '{bug_report_id}': {e}", exc_info=True)
                return None

    def update_bug_report_status(self, bug_report_id: int, new_status: str, comments: Optional[str] = None) -> bool:
        """
        Updates the status of an existing bug report.

        Args:
            bug_report_id (int): The unique identifier of the bug report.
            new_status (str): The new status ('Open', 'In Progress', 'Resolved', 'Closed').
            comments (Optional[str], optional): Additional comments or resolution details. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        valid_statuses = ['Open', 'In Progress', 'Resolved', 'Closed']
        if new_status not in valid_statuses:
            self.logger.error(f"Invalid status '{new_status}' provided.")
            return False

        with self.get_session() as session:
            try:
                bug_report = session.query(self.BugReport).filter(self.BugReport.id == bug_report_id).first()
                if not bug_report:
                    self.logger.error(f"Bug report with ID '{bug_report_id}' does not exist.")
                    return False

                bug_report.status = new_status
                if new_status in ['Resolved', 'Closed']:
                    bug_report.resolved_at = datetime.utcnow()
                if comments:
                    bug_report.comments = comments
                bug_report.updated_at = datetime.utcnow()

                self.logger.info(f"Bug report ID '{bug_report_id}' updated to status '{new_status}'.")

                # Update integrations
                self.vector_db.update_bug_report_status(bug_report_id=bug_report_id, new_status=new_status)
                self.graph_db.update_bug_report_node_status(bug_report_id=bug_report_id, new_status=new_status, comments=comments)
                self.shared_memory.update_bug_report_status(bug_report_id=bug_report_id, new_status=new_status, comments=comments)

                return True
            except IntegrityError as e:
                self.logger.error(f"Integrity error while updating bug report ID '{bug_report_id}': {e}", exc_info=True)
                return False
            except Exception as e:
                self.logger.error(f"Unexpected error while updating bug report ID '{bug_report_id}': {e}", exc_info=True)
                return False

    def delete_bug_report(self, bug_report_id: int) -> bool:
        """
        Deletes a bug report from the database.

        Args:
            bug_report_id (int): The unique identifier of the bug report.

        Returns:
            bool: True if deleted successfully, False otherwise.
        """
        with self.get_session() as session:
            try:
                bug_report = session.query(self.BugReport).filter(self.BugReport.id == bug_report_id).first()
                if bug_report:
                    session.delete(bug_report)
                    self.logger.info(f"Deleted bug report with ID '{bug_report_id}'.")

                    # Update integrations
                    self.vector_db.delete_bug_report(bug_report_id=bug_report_id)
                    self.graph_db.delete_bug_report_node(bug_report_id=bug_report_id)
                    self.shared_memory.delete_bug_report(bug_report_id=bug_report_id)

                    return True
                else:
                    self.logger.warning(f"No bug report found with ID '{bug_report_id}'.")
                    return False
            except Exception as e:
                self.logger.error(f"Unexpected error while deleting bug report ID '{bug_report_id}': {e}", exc_info=True)
                return False

    # FeedbackEntry Operations

    def submit_feedback(self, user_id: int, service_name: str, rating: float, comment: Optional[str] = None) -> Optional[int]:
        """
        Submits a feedback entry from a user.

        Args:
            user_id (int): The unique identifier of the user.
            service_name (str): The name of the service being reviewed.
            rating (float): The rating given by the user (1.0 to 5.0).
            comment (Optional[str], optional): Additional comments. Defaults to None.

        Returns:
            Optional[int]: The feedback entry ID if submission is successful, else None.
        """
        if not (1.0 <= rating <= 5.0):
            self.logger.error(f"Invalid rating '{rating}' provided. Must be between 1.0 and 5.0.")
            return None

        with self.get_session() as session:
            try:
                # Verify user exists
                user = session.query(self.User).filter(self.User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                feedback = self.FeedbackEntry(
                    user_id=user_id,
                    service_name=service_name,
                    rating=rating,
                    comment=comment,
                    submitted_at=datetime.utcnow(),
                    processed=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(feedback)
                session.flush()  # Assign an ID
                feedback_id = feedback.id
                self.logger.info(f"Feedback entry submitted successfully with ID '{feedback_id}' by user ID '{user_id}'.")

                # Integrate with Vector and Graph Databases
                self.vector_db.index_feedback(feedback_id=feedback_id, service_name=service_name, rating=rating, comment=comment)
                self.graph_db.add_feedback_entry_node(feedback_id=feedback_id, user_id=user_id, service_name=service_name, rating=rating)
                self.shared_memory.add_feedback_entry(feedback_id=feedback_id, service_name=service_name, rating=rating, comment=comment, processed=False)

                return feedback_id
            except IntegrityError as e:
                self.logger.error(f"Integrity error while submitting feedback: {e}", exc_info=True)
                return None
            except Exception as e:
                self.logger.error(f"Unexpected error while submitting feedback: {e}", exc_info=True)
                return None

    def get_feedback_entry(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a feedback entry's details by its ID.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            Optional[Dict[str, Any]]: The feedback entry details if found, else None.
        """
        with self.get_session() as session:
            try:
                feedback = session.query(self.FeedbackEntry).filter(self.FeedbackEntry.id == feedback_id).first()
                if feedback:
                    feedback_data = {
                        'id': feedback.id,
                        'user_id': feedback.user_id,
                        'service_name': feedback.service_name,
                        'rating': feedback.rating,
                        'comment': feedback.comment,
                        'submitted_at': feedback.submitted_at.isoformat(),
                        'processed': feedback.processed,
                        'response': feedback.response,
                        'created_at': feedback.created_at.isoformat(),
                        'updated_at': feedback.updated_at.isoformat()
                    }
                    self.logger.debug(f"Retrieved feedback entry data for ID '{feedback_id}'.")
                    return feedback_data
                else:
                    self.logger.warning(f"No feedback entry found with ID '{feedback_id}'.")
                    return None
            except Exception as e:
                self.logger.error(f"Unexpected error while retrieving feedback entry ID '{feedback_id}': {e}", exc_info=True)
                return None

    def update_feedback_entry(self, feedback_id: int, new_rating: Optional[float] = None, new_comment: Optional[str] = None) -> bool:
        """
        Updates a feedback entry's rating and/or comment.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.
            new_rating (Optional[float], optional): The new rating to update. Defaults to None.
            new_comment (Optional[str], optional): The new comment to update. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        with self.get_session() as session:
            try:
                feedback = session.query(self.FeedbackEntry).filter(self.FeedbackEntry.id == feedback_id).first()
                if feedback:
                    if new_rating is not None:
                        if not (1.0 <= new_rating <= 5.0):
                            self.logger.error(f"Invalid new rating '{new_rating}' provided. Must be between 1.0 and 5.0.")
                            return False
                        feedback.rating = new_rating
                        self.logger.info(f"Updated rating for feedback ID '{feedback_id}' to '{new_rating}'.")
                    if new_comment is not None:
                        feedback.comment = new_comment
                        self.logger.info(f"Updated comment for feedback ID '{feedback_id}'.")

                    feedback.updated_at = datetime.utcnow()

                    # Update integrations
                    self.vector_db.update_feedback_entry(feedback_id=feedback_id, new_rating=new_rating, new_comment=new_comment)
                    self.graph_db.update_feedback_entry_node(feedback_id=feedback_id, new_rating=new_rating, new_comment=new_comment)
                    self.shared_memory.update_feedback_entry(feedback_id=feedback_id, new_rating=new_rating, new_comment=new_comment)

                    return True
                else:
                    self.logger.warning(f"No feedback entry found with ID '{feedback_id}'.")
                    return False
            except IntegrityError as e:
                self.logger.error(f"Integrity error while updating feedback entry ID '{feedback_id}': {e}", exc_info=True)
                return False
            except Exception as e:
                self.logger.error(f"Unexpected error while updating feedback entry ID '{feedback_id}': {e}", exc_info=True)
                return False

    def delete_feedback_entry(self, feedback_id: int) -> bool:
        """
        Deletes a feedback entry from the database.

        Args:
            feedback_id (int): The unique identifier of the feedback entry.

        Returns:
            bool: True if deleted successfully, False otherwise.
        """
        with self.get_session() as session:
            try:
                feedback = session.query(self.FeedbackEntry).filter(self.FeedbackEntry.id == feedback_id).first()
                if feedback:
                    session.delete(feedback)
                    self.logger.info(f"Deleted feedback entry with ID '{feedback_id}'.")

                    # Update integrations
                    self.vector_db.delete_feedback_entry(feedback_id=feedback_id)
                    self.graph_db.delete_feedback_entry_node(feedback_id=feedback_id)
                    self.shared_memory.delete_feedback_entry(feedback_id=feedback_id)

                    return True
                else:
                    self.logger.warning(f"No feedback entry found with ID '{feedback_id}'.")
                    return False
            except Exception as e:
                self.logger.error(f"Unexpected error while deleting feedback entry ID '{feedback_id}': {e}", exc_info=True)
                return False

    # Additional Operations

    def process_unprocessed_feedbacks(self):
        """
        Processes all unprocessed feedback entries.
        Marks them as processed and performs necessary actions (e.g., updating vector and graph databases).
        """
        with self.get_session() as session:
            try:
                feedbacks = session.query(self.FeedbackEntry).filter(self.FeedbackEntry.processed == False).all()
                for feedback in feedbacks:
                    # Example processing: Acknowledge feedback
                    feedback.processed = True
                    feedback.response = f"Thank you for your feedback on {feedback.service_name}!"
                    feedback.updated_at = datetime.utcnow()
                    self.logger.info(f"Processed feedback ID '{feedback.id}' from user ID '{feedback.user_id}'.")

                    # Update integrations
                    self.vector_db.mark_feedback_processed(feedback.id)
                    self.graph_db.update_feedback_entry_node_processed(feedback.id, feedback.response)
                    self.shared_memory.update_feedback_entry_processed(feedback.id, response=feedback.response)

                self.logger.info(f"Processed {len(feedbacks)} unprocessed feedback entries.")
            except Exception as e:
                self.logger.error(f"Unexpected error while processing feedback entries: {e}", exc_info=True)

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

    # Utility Methods

    def refresh_integrations(self) -> bool:
        """
        Refreshes all integrations by re-indexing data from SQLite to Vector and Graph Databases.

        Returns:
            bool: True if refresh is successful, False otherwise.
        """
        try:
            # Re-index all users
            with self.get_session() as session:
                users = session.query(self.User).all()
                for user in users:
                    self.vector_db.index_user(user_id=user.id, username=user.username, email=user.email)
                    self.graph_db.add_user_node(user_id=user.id, username=user.username, email=user.email)
                    self.shared_memory.update_user(user_id=user.id, username=user.username, email=user.email)

            # Re-index all bug reports
            with self.get_session() as session:
                bug_reports = session.query(self.BugReport).all()
                for bug in bug_reports:
                    self.vector_db.index_bug_report(bug_report_id=bug.id, title=bug.title, description=bug.description, severity=bug.severity)
                    self.graph_db.add_bug_report_node(bug_report_id=bug.id, user_id=bug.user_id, severity=bug.severity)
                    self.shared_memory.add_bug_report(bug_report_id=bug.id, title=bug.title, description=bug.description, severity=bug.severity, status=bug.status)

            # Re-index all feedback entries
            with self.get_session() as session:
                feedback_entries = session.query(self.FeedbackEntry).all()
                for feedback in feedback_entries:
                    self.vector_db.index_feedback(feedback_id=feedback.id, service_name=feedback.service_name, rating=feedback.rating, comment=feedback.comment)
                    self.graph_db.add_feedback_entry_node(feedback_id=feedback.id, user_id=feedback.user_id, service_name=feedback.service_name, rating=feedback.rating)
                    self.shared_memory.add_feedback_entry(feedback_id=feedback.id, service_name=feedback.service_name, rating=feedback.rating, comment=feedback.comment, processed=feedback.processed)

            self.logger.info("All integrations refreshed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to refresh integrations: {e}", exc_info=True)
            return False

    def dispose_engine(self):
        """
        Disposes the engine, closing all sessions.
        """
        try:
            self.SessionFactory.remove()
            self.engine.dispose()
            self.logger.info("SQLiteDatabase engine and sessions disposed successfully.")

            # Close integrations
            self.vector_db.close()
            self.graph_db.close()
            self.shared_memory.close()

        except Exception as e:
            self.logger.error(f"Failed to dispose SQLiteDatabase engine: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Failed to dispose SQLiteDatabase engine: {e}")

    def create_all_tables(self):
        """
        Creates all tables defined by the Base metadata.
        """
        try:
            Base.metadata.create_all(self.engine)
            self.logger.info("All SQLite database tables created successfully.")
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error during table creation: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"SQLAlchemy error during table creation: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during table creation: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Unexpected error during table creation: {e}")

    # Additional CRUD operations for User, BugReport, and FeedbackEntry can be added here as needed

    # Integration with Potential Additional Database (e.g., Time Series Database)

    def log_event(self, event_type: str, details: Dict[str, Any], timestamp: Optional[datetime] = None) -> bool:
        """
        Logs an event to an additional database (e.g., Time Series Database) for monitoring and analytics.

        Args:
            event_type (str): The type of the event (e.g., 'user_created', 'bug_report_submitted').
            details (Dict[str, Any]): Additional details about the event.
            timestamp (Optional[datetime], optional): The time of the event. Defaults to current UTC time.

        Returns:
            bool: True if logging is successful, False otherwise.
        """
        try:
            from databases.time_series_db import TimeSeriesDatabase  # Assuming a time_series_db.py exists
            ts_db = TimeSeriesDatabase()
            return ts_db.log_event(event_type=event_type, details=details, timestamp=timestamp or datetime.utcnow())
        except Exception as e:
            self.logger.error(f"Failed to log event to Time Series Database: {e}", exc_info=True)
            return False

    # Example Method to Perform RAG Operation

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
            similar_bug_reports = self.vector_db.search_bug_reports(query_text=query_text, top_k=top_k)
            similar_feedbacks = self.vector_db.search_feedback(query_text=query_text, top_k=top_k)

            rag_result = {
                'query': query_text,
                'similar_bug_reports': similar_bug_reports,
                'similar_feedbacks': similar_feedbacks
            }

            # Integrate with GraphDatabase to fetch related entities
            for report in similar_bug_reports:
                related_users = self.graph_db.find_related_users(service_name=report['metadata'].get('service_name', ''))
                rag_result.setdefault('related_users', []).extend(related_users or [])

            for feedback in similar_feedbacks:
                related_users = self.graph_db.find_related_users(service_name=feedback['metadata'].get('service_name', ''))
                rag_result.setdefault('related_users', []).extend(related_users or [])

            # Optionally, fetch data from shared memory
            # Example: Fetch detailed data for the first similar bug report
            if similar_bug_reports:
                first_bug_id = similar_bug_reports[0]['metadata'].get('bug_report_id')
                detailed_bug = self.retrieve_shared_memory_data(data_type='bug_report', data_id=first_bug_id)
                rag_result['detailed_bug_report'] = detailed_bug

            self.logger.debug(f"RAG operation completed for query: '{query_text}'.")
            return rag_result
        except Exception as e:
            self.logger.error(f"Failed to perform RAG operation for query '{query_text}': {e}", exc_info=True)
            return None

    # Additional utility methods can be added here as needed

    def get_all_users(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all users from the database.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of users if successful, else None.
        """
        with self.get_session() as session:
            try:
                users = session.query(self.User).all()
                user_list = [{
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'created_at': user.created_at.isoformat(),
                    'updated_at': user.updated_at.isoformat()
                } for user in users]
                self.logger.debug(f"Retrieved all users. Count: {len(user_list)}.")
                return user_list
            except Exception as e:
                self.logger.error(f"Unexpected error while retrieving all users: {e}", exc_info=True)
                return None

    def get_all_bug_reports(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all bug reports from the database.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of bug reports if successful, else None.
        """
        with self.get_session() as session:
            try:
                bugs = session.query(self.BugReport).all()
                bug_list = [{
                    'id': bug.id,
                    'user_id': bug.user_id,
                    'title': bug.title,
                    'description': bug.description,
                    'severity': bug.severity,
                    'status': bug.status,
                    'reported_at': bug.reported_at.isoformat(),
                    'resolved_at': bug.resolved_at.isoformat() if bug.resolved_at else None,
                    'comments': bug.comments,
                    'created_at': bug.created_at.isoformat(),
                    'updated_at': bug.updated_at.isoformat()
                } for bug in bugs]
                self.logger.debug(f"Retrieved all bug reports. Count: {len(bug_list)}.")
                return bug_list
            except Exception as e:
                self.logger.error(f"Unexpected error while retrieving all bug reports: {e}", exc_info=True)
                return None

    def get_all_feedback_entries(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all feedback entries from the database.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of feedback entries if successful, else None.
        """
        with self.get_session() as session:
            try:
                feedbacks = session.query(self.FeedbackEntry).all()
                feedback_list = [{
                    'id': fb.id,
                    'user_id': fb.user_id,
                    'service_name': fb.service_name,
                    'rating': fb.rating,
                    'comment': fb.comment,
                    'submitted_at': fb.submitted_at.isoformat(),
                    'processed': fb.processed,
                    'response': fb.response,
                    'created_at': fb.created_at.isoformat(),
                    'updated_at': fb.updated_at.isoformat()
                } for fb in feedbacks]
                self.logger.debug(f"Retrieved all feedback entries. Count: {len(feedback_list)}.")
                return feedback_list
            except Exception as e:
                self.logger.error(f"Unexpected error while retrieving all feedback entries: {e}", exc_info=True)
                return None

    # Additional Methods for Enhanced Functionality can be added here

    # Integration with Additional Database: Key-Value Store (e.g., Redis)

    def cache_user_data(self, user_id: int) -> bool:
        """
        Caches user data in Redis for faster access.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if caching is successful, False otherwise.
        """
        try:
            user_data = self.get_user_by_id(user_id)
            if user_data:
                # Serialize user data as JSON
                user_json = json.dumps(user_data)
                # Assuming shared_memory has a method to cache data
                self.shared_memory.cache_user(user_id=user_id, data=user_json)
                self.logger.debug(f"Cached user data for user ID '{user_id}' in Redis.")
                return True
            else:
                self.logger.warning(f"No user data found to cache for user ID '{user_id}'.")
                return False
        except Exception as e:
            self.logger.error(f"Failed to cache user data for user ID '{user_id}': {e}", exc_info=True)
            return False

    def get_cached_user_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached user data from Redis.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: The cached user data if found, else None.
        """
        try:
            user_json = self.shared_memory.get_cached_user(user_id=user_id)
            if user_json:
                user_data = json.loads(user_json)
                self.logger.debug(f"Retrieved cached user data for user ID '{user_id}' from Redis.")
                return user_data
            else:
                self.logger.debug(f"No cached user data found for user ID '{user_id}' in Redis.")
                return None
        except Exception as e:
            self.logger.error(f"Failed to retrieve cached user data for user ID '{user_id}': {e}", exc_info=True)
            return None

    # Suggested Additional Database Integration: Time Series Database (e.g., InfluxDB)

    def log_event_to_time_series_db(self, event_type: str, details: Dict[str, Any], timestamp: Optional[datetime] = None) -> bool:
        """
        Logs an event to the Time Series Database for monitoring and analytics.

        Args:
            event_type (str): The type of the event (e.g., 'user_created', 'bug_report_submitted').
            details (Dict[str, Any]): Additional details about the event.
            timestamp (Optional[datetime], optional): The time of the event. Defaults to current UTC time.

        Returns:
            bool: True if logging is successful, False otherwise.
        """
        try:
            from databases.time_series_db import TimeSeriesDatabase  # Assuming a time_series_db.py exists
            ts_db = TimeSeriesDatabase()
            return ts_db.log_event(event_type=event_type, details=details, timestamp=timestamp or datetime.utcnow())
        except Exception as e:
            self.logger.error(f"Failed to log event to Time Series Database: {e}", exc_info=True)
            return False

    # Final Clean-up and Resource Management

    def close(self):
        """
        Closes the database engine and all sessions.
        """
        try:
            self.SessionFactory.remove()
            self.engine.dispose()
            self.logger.info("SQLiteDatabase engine and sessions closed successfully.")

            # Close integrations
            self.vector_db.close()
            self.graph_db.close()
            self.shared_memory.close()

        except Exception as e:
            self.logger.error(f"Error while closing SQLiteDatabase: {e}", exc_info=True)
            raise SQLiteDatabaseError(f"Error while closing SQLiteDatabase: {e}")

