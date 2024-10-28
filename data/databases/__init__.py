
import logging
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

class Database:
    """
    Handles database connections and sessions using SQLAlchemy.
    Implements singleton pattern to ensure only one engine and sessionmaker exist.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """
        Implements singleton pattern.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initializes the database connection.
        """
        if hasattr(self, '_initialized') and self._initialized:
            return
        self.logger = setup_logging('Database')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.engine = None
        self.Session = None
        self._initialize_engine()
        self._initialized = True

    def _initialize_engine(self):
        """
        Creates the SQLAlchemy engine and sessionmaker.
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
            pool_size = db_config.get('pool_size', 10)
            max_overflow = db_config.get('max_overflow', 20)
            connect_args = db_config.get('connect_args', {})

            if not all([db_type, username, password_encrypted, host, port, database]):
                self.logger.error("Database configuration is incomplete.")
                raise DatabaseError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(
                connection_string,
                pool_size=pool_size,
                max_overflow=max_overflow,
                connect_args=connect_args,
                pool_pre_ping=True,
                echo=False  # Disable echo for production
            )
            self.Session = scoped_session(sessionmaker(bind=self.engine))
            self.logger.info("Database engine and sessionmaker initialized successfully.")
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error during engine initialization: {e}", exc_info=True)
            raise DatabaseError(f"SQLAlchemy error during engine initialization: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during engine initialization: {e}", exc_info=True)
            raise DatabaseError(f"Unexpected error during engine initialization: {e}")

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
            raise DatabaseError(f"Unsupported database type '{db_type}'.")

    @contextmanager
    def get_session(self):
        """
        Provides a transactional scope around a series of operations.

        Usage:
            with Database().get_session() as session:
                # Perform database operations
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error during session: {e}", exc_info=True)
            session.rollback()
            raise DatabaseError(f"SQLAlchemy error during session: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during session: {e}", exc_info=True)
            session.rollback()
            raise DatabaseError(f"Unexpected error during session: {e}")
        finally:
            session.close()

    def dispose_engine(self):
        """
        Disposes the engine, closing all connections.
        """
        try:
            self.logger.debug("Disposing database engine.")
            self.engine.dispose()
            self.logger.info("Database engine disposed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to dispose database engine: {e}", exc_info=True)
            raise DatabaseError(f"Failed to dispose database engine: {e}")

    def create_all_tables(self):
        """
        Creates all tables defined by the Base metadata.
        """
        try:
            self.logger.debug("Creating all tables in the database.")
            Base.metadata.create_all(self.engine)
            self.logger.info("All tables created successfully.")
        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy error during table creation: {e}", exc_info=True)
            raise DatabaseError(f"SQLAlchemy error during table creation: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during table creation: {e}", exc_info=True)
            raise DatabaseError(f"Unexpected error during table creation: {e}")
