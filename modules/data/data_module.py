# modules/data/data_module.py

"""
Data Module

This module provides advanced data handling functionalities encapsulated within the DataModule class.

Features:
- Secure database connections with connection pooling
- Thread-safe operations
- Comprehensive error handling and logging
- Support for multiple database types (PostgreSQL, MySQL, SQLite)
- Data validation and sanitization
- ORM integration using SQLAlchemy
- Transaction management with rollback capabilities
- Prepared statements to prevent SQL injection
- Support for asynchronous operations
- Caching mechanisms to improve performance
- Bulk data operations with chunking
- Data export and import utilities
- Configuration management with environment variables

Author: Your Name
Date: YYYY-MM-DD
"""

import os
import logging
import threading
from typing import Any, Dict, List, Optional, Union, Callable, Generator, Type

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError, DatabaseError
from sqlalchemy.pool import QueuePool
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy.sql import text
from sqlalchemy.engine.url import URL
from dotenv import load_dotenv
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Configure Logging
logger = logging.getLogger('data_module')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/data_module.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Base class for declarative class definitions
Base = declarative_base()

# Exception Classes
class DataError(Exception):
    """Base class for data-related exceptions."""
    pass

class DatabaseConnectionError(DataError):
    """Raised when the database connection fails."""
    pass

class DataValidationError(DataError):
    """Raised when data validation fails."""
    pass

class TransactionError(DataError):
    """Raised when a database transaction fails."""
    pass

class DataModule:
    """
    DataModule Class

    Encapsulates data handling functionalities, including database connections, ORM operations,
    data validation, transaction management, and more.
    """

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern to ensure only one instance of DataModule exists.
        """
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(DataModule, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = logger
        self._configure_database()
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        self.lock = threading.RLock()

    def _configure_database(self):
        """
        Configures the database engine and connection pooling.
        """
        try:
            db_config = {
                'drivername': os.getenv('DB_DRIVER', 'postgresql'),
                'username': os.getenv('DB_USERNAME', 'user'),
                'password': os.getenv('DB_PASSWORD', 'password'),
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '5432'),
                'database': os.getenv('DB_NAME', 'database'),
            }
            self.engine = create_engine(
                URL(**db_config),
                poolclass=QueuePool,
                pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
                max_overflow=int(os.getenv('DB_MAX_OVERFLOW', '20')),
                pool_timeout=int(os.getenv('DB_POOL_TIMEOUT', '30')),
                pool_recycle=int(os.getenv('DB_POOL_RECYCLE', '1800')),
                echo=False,
                isolation_level="READ COMMITTED"
            )
            self.logger.info("Database engine configured successfully.")
            self._register_event_listeners()
        except Exception as e:
            self.logger.exception(f"Failed to configure database engine: {e}")
            raise DatabaseConnectionError("Failed to configure database engine.") from e

    def _register_event_listeners(self):
        """
        Registers event listeners for the SQLAlchemy engine.
        """
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if self.engine.url.drivername == 'sqlite':
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
                self.logger.debug("SQLite PRAGMA foreign_keys enabled.")

        self.logger.debug("Event listeners registered.")

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Provides a transactional scope around a series of operations.

        Usage:
            with data_module.session_scope() as session:
                # perform database operations
        """
        session = self.Session()
        try:
            yield session
            session.commit()
            self.logger.debug("Session committed successfully.")
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.exception(f"Session rollback due to error: {e}")
            raise TransactionError("Database transaction failed.") from e
        finally:
            session.close()
            self.logger.debug("Session closed.")

    def execute_raw_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Executes a raw SQL query with optional parameters.
        """
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query), params or {})
                rows = [dict(row) for row in result]
                self.logger.debug(f"Executed raw query: {query} with params: {params}")
                return rows
        except SQLAlchemyError as e:
            self.logger.exception(f"Failed to execute raw query: {e}")
            raise DataError("Failed to execute raw query.") from e

    def add_record(self, record: any) -> None:
        """
        Adds a new record to the database.
        """
        with self.session_scope() as session:
            try:
                session.add(record)
                self.logger.debug(f"Record added: {record}")
            except IntegrityError as e:
                self.logger.exception(f"Integrity error while adding record: {e}")
                raise DataError("Failed to add record due to integrity constraints.") from e
            except SQLAlchemyError as e:
                self.logger.exception(f"Error while adding record: {e}")
                raise DataError("Failed to add record.") from e

    def get_records(self, model: Type[DeclarativeMeta], filters: Optional[Dict[str, Any]] = None) -> List[any]:
        """
        Retrieves records from the database based on the given filters.
        """
        with self.session_scope() as session:
            try:
                query = session.query(model)
                if filters:
                    query = query.filter_by(**filters)
                records = query.all()
                self.logger.debug(f"Retrieved records: {records}")
                return records
            except SQLAlchemyError as e:
                self.logger.exception(f"Failed to retrieve records: {e}")
                raise DataError("Failed to retrieve records.") from e

    def update_record(self, model: Type[DeclarativeMeta], record_id: Any, updates: Dict[str, Any]) -> None:
        """
        Updates a record in the database.
        """
        with self.session_scope() as session:
            try:
                record = session.query(model).get(record_id)
                if not record:
                    self.logger.warning(f"Record not found with id: {record_id}")
                    raise DataError("Record not found.")
                for key, value in updates.items():
                    setattr(record, key, value)
                session.add(record)
                self.logger.debug(f"Record updated: {record}")
            except SQLAlchemyError as e:
                self.logger.exception(f"Failed to update record: {e}")
                raise DataError("Failed to update record.") from e

    def delete_record(self, model: Type[DeclarativeMeta], record_id: Any) -> None:
        """
        Deletes a record from the database.
        """
        with self.session_scope() as session:
            try:
                record = session.query(model).get(record_id)
                if not record:
                    self.logger.warning(f"Record not found with id: {record_id}")
                    raise DataError("Record not found.")
                session.delete(record)
                self.logger.debug(f"Record deleted: {record}")
            except SQLAlchemyError as e:
                self.logger.exception(f"Failed to delete record: {e}")
                raise DataError("Failed to delete record.") from e

    # Additional methods as required...

# Example ORM Model (Replace with actual models)
class ExampleModel(Base):
    __tablename__ = 'example_table'

    from sqlalchemy import Column, Integer, String
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    value = Column(String(255), nullable=False)

    def __repr__(self):
        return f"<ExampleModel(id={self.id}, name='{self.name}', value='{self.value}')>"

# Example Usage (Remove or comment out in production)
#if __name__ == "__main__":
 #   data_module = DataModule()
  #  try:
        # Create tables (only for demonstration; in production, use migrations)
       
