# services/database_management_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
import os
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, scoped_session
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class DatabaseManagementServiceError(Exception):
    """Custom exception for DatabaseManagementService-related errors."""
    pass


class DatabaseManagementService:
    """
    Provides comprehensive database management capabilities, including connecting to databases,
    executing queries, managing transactions, and handling schema migrations. Utilizes SQLAlchemy
    for ORM support and ensures secure handling of database credentials and operations.
    """

    def __init__(self):
        """
        Initializes the DatabaseManagementService with necessary configurations and authentication.
        """
        self.logger = setup_logging('DatabaseManagementService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.engine: Optional[Engine] = None
        self.Session: Optional[scoped_session] = None
        self._initialize_engine()
        self.logger.info("DatabaseManagementService initialized successfully.")

    def _initialize_engine(self):
        """
        Initializes the SQLAlchemy engine based on configuration settings.
        """
        try:
            self.logger.debug("Initializing database engine.")
            db_config = self.config_loader.get('DATABASE_CONFIG', {})
            db_type = db_config.get('type')
            username = db_config.get('username')
            password_encrypted = db_config.get('password')
            host = db_config.get('host', 'localhost')
            port = db_config.get('port')
            database = db_config.get('database')

            if not all([db_type, username, password_encrypted, host, port, database]):
                self.logger.error("Incomplete database configuration.")
                raise DatabaseManagementServiceError("Incomplete database configuration.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')

            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            self.Session = scoped_session(sessionmaker(bind=self.engine))
            self.logger.debug("Database engine initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing database engine: {e}", exc_info=True)
            raise DatabaseManagementServiceError(f"Error initializing database engine: {e}")

    def _build_connection_string(self, db_type: str, username: str, password: str, host: str, port: int, database: str) -> str:
        """
        Builds the database connection string based on the database type.

        Args:
            db_type (str): The type of the database ('postgresql', 'mysql', 'sqlite', etc.).
            username (str): The database username.
            password (str): The database password.
            host (str): The database host.
            port (int): The database port.
            database (str): The database name.

        Returns:
            str: The formatted connection string.
        """
        if db_type.lower() == 'postgresql':
            return f"postgresql://{username}:{password}@{host}:{port}/{database}"
        elif db_type.lower() == 'mysql':
            return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
        elif db_type.lower() == 'sqlite':
            return f"sqlite:///{database}"
        else:
            self.logger.error(f"Unsupported database type '{db_type}'.")
            raise DatabaseManagementServiceError(f"Unsupported database type '{db_type}'.")

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Executes a SQL query and returns the results.

        Args:
            query (str): The SQL query to execute.
            params (Optional[Dict[str, Any]], optional): The parameters for parameterized queries. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: The query results as a list of dictionaries, or None if execution fails.
        """
        try:
            self.logger.debug(f"Executing query: {query} with params: {params}.")
            with self.lock:
                session = self.Session()
                result = session.execute(text(query), params or {})
                if result.returns_rows:
                    rows = result.fetchall()
                    columns = result.keys()
                    result_list = [dict(zip(columns, row)) for row in rows]
                    self.logger.debug(f"Query executed successfully. Retrieved {len(result_list)} rows.")
                    return result_list
                else:
                    session.commit()
                    self.logger.debug("Query executed successfully. No rows returned.")
                    return []
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error executing query: {e}", exc_info=True)
            if self.Session:
                self.Session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Error executing query: {e}", exc_info=True)
            return None
        finally:
            if self.Session:
                self.Session.remove()

    def execute_transaction(self, queries: List[Tuple[str, Optional[Dict[str, Any]]]]) -> bool:
        """
        Executes a list of SQL queries within a single transaction.

        Args:
            queries (List[Tuple[str, Optional[Dict[str, Any]]]]): A list of tuples containing queries and their parameters.

        Returns:
            bool: True if all queries are executed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Executing transaction with {len(queries)} queries.")
            with self.lock:
                session = self.Session()
                for idx, (query, params) in enumerate(queries, start=1):
                    self.logger.debug(f"Executing query {idx}: {query} with params: {params}.")
                    session.execute(text(query), params or {})
                session.commit()
                self.logger.info("Transaction executed successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error during transaction: {e}", exc_info=True)
            if self.Session:
                self.Session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Error during transaction: {e}", exc_info=True)
            if self.Session:
                self.Session.rollback()
            return False
        finally:
            if self.Session:
                self.Session.remove()

    def create_table(self, table_name: str, columns: List[Column]) -> bool:
        """
        Creates a new table in the database.

        Args:
            table_name (str): The name of the table to create.
            columns (List[Column]): A list of SQLAlchemy Column objects defining the table schema.

        Returns:
            bool: True if the table is created successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Creating table '{table_name}' with columns {[col.name for col in columns]}.")
            metadata = MetaData()
            table = Table(table_name, metadata, *columns)
            metadata.create_all(self.engine)
            self.logger.info(f"Table '{table_name}' created successfully.")
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error creating table '{table_name}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Error creating table '{table_name}': {e}", exc_info=True)
            return False

    def drop_table(self, table_name: str) -> bool:
        """
        Drops an existing table from the database.

        Args:
            table_name (str): The name of the table to drop.

        Returns:
            bool: True if the table is dropped successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Dropping table '{table_name}'.")
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=self.engine)
            table.drop(self.engine)
            self.logger.info(f"Table '{table_name}' dropped successfully.")
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error dropping table '{table_name}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Error dropping table '{table_name}': {e}", exc_info=True)
            return False

    def migrate_schema(self, migrations: List[str]) -> bool:
        """
        Applies schema migrations to the database.

        Args:
            migrations (List[str]): A list of SQL migration scripts to execute.

        Returns:
            bool: True if all migrations are applied successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Applying {len(migrations)} schema migrations.")
            with self.lock:
                session = self.Session()
                for idx, migration in enumerate(migrations, start=1):
                    self.logger.debug(f"Applying migration {idx}: {migration}.")
                    session.execute(text(migration))
                session.commit()
                self.logger.info("All schema migrations applied successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error during schema migrations: {e}", exc_info=True)
            if self.Session:
                self.Session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Error during schema migrations: {e}", exc_info=True)
            if self.Session:
                self.Session.rollback()
            return False
        finally:
            if self.Session:
                self.Session.remove()

    def get_table_columns(self, table_name: str) -> Optional[List[str]]:
        """
        Retrieves the column names of a specified table.

        Args:
            table_name (str): The name of the table.

        Returns:
            Optional[List[str]]: A list of column names, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Retrieving columns for table '{table_name}'.")
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=self.engine)
            columns = [column.name for column in table.columns]
            self.logger.debug(f"Columns for table '{table_name}': {columns}.")
            return columns
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error retrieving columns for table '{table_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving columns for table '{table_name}': {e}", exc_info=True)
            return None

    def get_all_tables(self) -> Optional[List[str]]:
        """
        Retrieves all table names in the connected database.

        Returns:
            Optional[List[str]]: A list of table names, or None if retrieval fails.
        """
        try:
            self.logger.debug("Retrieving all table names from the database.")
            inspector = self.engine.dialect.get_inspector(self.engine)
            tables = inspector.get_table_names()
            self.logger.debug(f"Tables in the database: {tables}.")
            return tables
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error retrieving table names: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving table names: {e}", exc_info=True)
            return None

    def backup_database(self, backup_path: str) -> bool:
        """
        Creates a backup of the current database.

        Args:
            backup_path (str): The file path where the backup will be stored.

        Returns:
            bool: True if the backup is created successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Creating database backup at '{backup_path}'.")
            db_config = self.config_loader.get('DATABASE_CONFIG', {})
            db_type = db_config.get('type').lower()

            if db_type == 'postgresql':
                import subprocess
                cmd = [
                    'pg_dump',
                    '-h', db_config.get('host', 'localhost'),
                    '-p', str(db_config.get('port', 5432)),
                    '-U', db_config.get('username'),
                    '-F', 'c',
                    '-b',
                    '-v',
                    '-f', backup_path,
                    db_config.get('database')
                ]
                env = os.environ.copy()
                env['PGPASSWORD'] = self.encryption_manager.decrypt_data(db_config.get('password')).decode('utf-8')
                subprocess.run(cmd, check=True, env=env)
            elif db_type == 'mysql':
                import subprocess
                cmd = [
                    'mysqldump',
                    '-h', db_config.get('host', 'localhost'),
                    '-P', str(db_config.get('port', 3306)),
                    '-u', db_config.get('username'),
                    f"-p{self.encryption_manager.decrypt_data(db_config.get('password')).decode('utf-8')}",
                    db_config.get('database'),
                    '--result-file', backup_path
                ]
                subprocess.run(cmd, check=True)
            elif db_type == 'sqlite':
                import shutil
                shutil.copyfile(db_config.get('database'), backup_path)
            else:
                self.logger.error(f"Unsupported database type '{db_type}' for backup.")
                return False

            self.logger.info(f"Database backup created successfully at '{backup_path}'.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error during database backup: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Error creating database backup at '{backup_path}': {e}", exc_info=True)
            return False

    def restore_database(self, backup_path: str) -> bool:
        """
        Restores the database from a backup file.

        Args:
            backup_path (str): The file path to the backup file.

        Returns:
            bool: True if the database is restored successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Restoring database from backup '{backup_path}'.")
            db_config = self.config_loader.get('DATABASE_CONFIG', {})
            db_type = db_config.get('type').lower()

            if db_type == 'postgresql':
                import subprocess
                cmd = [
                    'pg_restore',
                    '-h', db_config.get('host', 'localhost'),
                    '-p', str(db_config.get('port', 5432)),
                    '-U', db_config.get('username'),
                    '-d', db_config.get('database'),
                    '-v',
                    backup_path
                ]
                env = os.environ.copy()
                env['PGPASSWORD'] = self.encryption_manager.decrypt_data(db_config.get('password')).decode('utf-8')
                subprocess.run(cmd, check=True, env=env)
            elif db_type == 'mysql':
                import subprocess
                cmd = [
                    'mysql',
                    '-h', db_config.get('host', 'localhost'),
                    '-P', str(db_config.get('port', 3306)),
                    '-u', db_config.get('username'),
                    f"-p{self.encryption_manager.decrypt_data(db_config.get('password')).decode('utf-8')}",
                    db_config.get('database')
                ]
                with open(backup_path, 'r') as f:
                    subprocess.run(cmd, stdin=f, check=True)
            elif db_type == 'sqlite':
                import shutil
                shutil.copyfile(backup_path, db_config.get('database'))
            else:
                self.logger.error(f"Unsupported database type '{db_type}' for restoration.")
                return False

            self.logger.info(f"Database restored successfully from '{backup_path}'.")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error during database restoration: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Error restoring database from backup '{backup_path}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing DatabaseManagementService resources.")
            if self.engine:
                self.engine.dispose()
                self.logger.debug("Database engine disposed.")
            self.logger.info("DatabaseManagementService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing DatabaseManagementService: {e}", exc_info=True)
            raise DatabaseManagementServiceError(f"Error closing DatabaseManagementService: {e}")
