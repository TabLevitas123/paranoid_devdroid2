# services/theme_customization_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import json
import requests
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class Theme(Base):
    __tablename__ = 'themes'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=False)
    settings = Column(Text, nullable=False)  # JSON string containing theme settings
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_settings = relationship("UserThemeSetting", back_populates="theme")

class UserThemeSetting(Base):
    __tablename__ = 'user_theme_settings'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    theme_id = Column(String, ForeignKey('themes.id'), nullable=False)
    preferences = Column(Text, nullable=True)  # JSON string for user-specific preferences
    applied_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    theme = relationship("Theme", back_populates="user_settings")
    user = relationship("User", backref="theme_settings")

class ThemeCustomizationServiceError(Exception):
    """Custom exception for ThemeCustomizationService-related errors."""
    pass

class ThemeCustomizationService:
    """
    Provides theme customization capabilities, including managing available themes,
    allowing users to select and customize themes, and applying theme settings across the application.
    Utilizes SQLAlchemy for database interactions and integrates with frontend APIs for real-time theme application.
    Ensures secure handling of user data and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the ThemeCustomizationService with necessary configurations and authentication.
        """
        self.logger = setup_logging('ThemeCustomizationService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.frontend_api_url = self.config_loader.get('FRONTEND_API_URL', 'https://api.frontend.com')
        self.frontend_api_key_encrypted = self.config_loader.get('FRONTEND_API_KEY')
        self.frontend_api_key = self.encryption_manager.decrypt_data(self.frontend_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("ThemeCustomizationService initialized successfully.")

    def _initialize_database(self):
        """
        Initializes the database connection and creates tables if they do not exist.
        """
        try:
            self.logger.debug("Initializing database connection.")
            db_config = self.config_loader.get('DATABASE_CONFIG', {})
            db_type = db_config.get('type')
            username = db_config.get('username')
            password_encrypted = db_config.get('password')
            host = db_config.get('host', 'localhost')
            port = db_config.get('port')
            database = db_config.get('database')

            if not all([db_type, username, password_encrypted, host, port, database]):
                self.logger.error("Database configuration is incomplete.")
                raise ThemeCustomizationServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise ThemeCustomizationServiceError(f"Error initializing database: {e}")

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
            raise ThemeCustomizationServiceError(f"Unsupported database type '{db_type}'.")

    def add_theme(self, name: str, description: str, settings: Dict[str, Any], enabled_by_default: bool = False) -> Optional[str]:
        """
        Adds a new theme to the system.

        Args:
            name (str): The name of the theme.
            description (str): A detailed description of the theme.
            settings (Dict[str, Any]): The theme settings in JSON-serializable format.
            enabled_by_default (bool, optional): Whether the theme is enabled by default. Defaults to False.

        Returns:
            Optional[str]: The theme ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding theme '{name}'.")
            with self.lock:
                existing_theme = self.session.query(Theme).filter(Theme.name.ilike(name)).first()
                if existing_theme:
                    self.logger.error(f"Theme '{name}' already exists.")
                    return None

                theme = Theme(
                    name=name,
                    description=description,
                    settings=json.dumps(settings)
                )
                self.session.add(theme)
                self.session.commit()
                theme_id = theme.id
                self.logger.info(f"Theme '{name}' added successfully with ID '{theme_id}'.")

                # Optionally, notify frontend to update available themes
                self._notify_frontend_new_theme(theme)

                return theme_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding theme '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while adding theme '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _notify_frontend_new_theme(self, theme: 'Theme'):
        """
        Notifies the frontend application about a new theme addition.

        Args:
            theme (Theme): The Theme instance that was added.
        """
        try:
            self.logger.debug(f"Notifying frontend about new theme '{theme.name}'.")
            headers = {
                'Authorization': f"Bearer {self.frontend_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'theme_id': theme.id,
                'name': theme.name,
                'description': theme.description,
                'settings': json.loads(theme.settings),
                'created_at': theme.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            response = self.session_requests.post(
                f"{self.frontend_api_url}/themes/add",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify frontend about new theme '{theme.name}'. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Frontend notified successfully about new theme '{theme.name}'.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying frontend about theme '{theme.name}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying frontend about theme '{theme.name}': {e}", exc_info=True)

    def update_theme(self, theme_id: str, name: Optional[str] = None, description: Optional[str] = None,
                    settings: Optional[Dict[str, Any]] = None) -> bool:
        """
        Updates an existing theme.

        Args:
            theme_id (str): The unique identifier of the theme.
            name (Optional[str], optional): The new name of the theme. Defaults to None.
            description (Optional[str], optional): The new description of the theme. Defaults to None.
            settings (Optional[Dict[str, Any]], optional): The new theme settings. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating theme ID '{theme_id}'.")
            with self.lock:
                theme = self.session.query(Theme).filter(Theme.id == theme_id).first()
                if not theme:
                    self.logger.error(f"Theme with ID '{theme_id}' does not exist.")
                    return False

                if name:
                    theme.name = name
                if description:
                    theme.description = description
                if settings:
                    theme.settings = json.dumps(settings)

                self.session.commit()
                self.logger.info(f"Theme ID '{theme_id}' updated successfully.")

                # Optionally, notify frontend about theme update
                self._notify_frontend_update_theme(theme)

                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating theme ID '{theme_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating theme ID '{theme_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_frontend_update_theme(self, theme: 'Theme'):
        """
        Notifies the frontend application about a theme update.

        Args:
            theme (Theme): The Theme instance that was updated.
        """
        try:
            self.logger.debug(f"Notifying frontend about updated theme '{theme.name}'.")
            headers = {
                'Authorization': f"Bearer {self.frontend_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'theme_id': theme.id,
                'name': theme.name,
                'description': theme.description,
                'settings': json.loads(theme.settings),
                'updated_at': theme.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            response = self.session_requests.post(
                f"{self.frontend_api_url}/themes/update",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify frontend about updated theme '{theme.name}'. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Frontend notified successfully about updated theme '{theme.name}'.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying frontend about theme update '{theme.name}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying frontend about theme update '{theme.name}': {e}", exc_info=True)

    def get_available_themes(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of all available themes.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of themes if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Retrieving list of available themes.")
            with self.lock:
                themes = self.session.query(Theme).all()
                theme_list = [
                    {
                        'id': theme.id,
                        'name': theme.name,
                        'description': theme.description,
                        'settings': json.loads(theme.settings),
                        'created_at': theme.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': theme.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for theme in themes
                ]
                self.logger.info(f"Retrieved {len(theme_list)} themes successfully.")
                return theme_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving themes: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving themes: {e}", exc_info=True)
            return None

    def apply_theme_to_user(self, user_id: str, theme_id: str, preferences: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Applies a selected theme to a user's profile.

        Args:
            user_id (str): The unique identifier of the user.
            theme_id (str): The unique identifier of the theme.
            preferences (Optional[Dict[str, Any]], optional): User-specific preferences for the theme. Defaults to None.

        Returns:
            Optional[str]: The user theme setting ID if application is successful, else None.
        """
        try:
            self.logger.debug(f"Applying theme ID '{theme_id}' to user ID '{user_id}' with preferences '{preferences}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                theme = self.session.query(Theme).filter(Theme.id == theme_id).first()
                if not theme:
                    self.logger.error(f"Theme with ID '{theme_id}' does not exist.")
                    return None

                existing_setting = self.session.query(UserThemeSetting).filter(
                    UserThemeSetting.user_id == user_id,
                    UserThemeSetting.theme_id == theme_id
                ).first()

                if existing_setting:
                    existing_setting.preferences = json.dumps(preferences) if preferences else None
                    existing_setting.applied_at = datetime.utcnow()
                    self.session.commit()
                    setting_id = existing_setting.id
                    self.logger.info(f"Theme ID '{theme_id}' applied to user ID '{user_id}' successfully with setting ID '{setting_id}'.")
                    return setting_id

                setting = UserThemeSetting(
                    user_id=user_id,
                    theme_id=theme_id,
                    enabled=True,
                    preferences=json.dumps(preferences) if preferences else None,
                    applied_at=datetime.utcnow()
                )
                self.session.add(setting)
                self.session.commit()
                setting_id = setting.id
                self.logger.info(f"Theme ID '{theme_id}' applied to user ID '{user_id}' successfully with setting ID '{setting_id}'.")

                # Optionally, notify frontend to update the user's theme in real-time
                self._notify_frontend_apply_theme(user, theme, preferences)

                return setting_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while applying theme ID '{theme_id}' to user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while applying theme ID '{theme_id}' to user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _notify_frontend_apply_theme(self, user: 'User', theme: 'Theme', preferences: Optional[Dict[str, Any]]):
        """
        Notifies the frontend application to apply the selected theme to the user's interface.

        Args:
            user (User): The User instance.
            theme (Theme): The Theme instance.
            preferences (Optional[Dict[str, Any]]): User-specific preferences.
        """
        try:
            self.logger.debug(f"Notifying frontend to apply theme '{theme.name}' for user '{user.email}'.")
            headers = {
                'Authorization': f"Bearer {self.frontend_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'user_id': user.id,
                'theme_id': theme.id,
                'preferences': preferences or {}
            }
            response = self.session_requests.post(
                f"{self.frontend_api_url}/themes/apply",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify frontend to apply theme '{theme.name}' for user '{user.email}'. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Frontend notified successfully to apply theme '{theme.name}' for user '{user.email}'.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying frontend to apply theme '{theme.name}' for user '{user.email}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying frontend to apply theme '{theme.name}' for user '{user.email}': {e}", exc_info=True)

    def get_user_theme_settings(self, user_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all theme settings applied to a user.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of user theme settings if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving theme settings for user ID '{user_id}'.")
            with self.lock:
                settings = self.session.query(UserThemeSetting).filter(UserThemeSetting.user_id == user_id).all()
                settings_list = [
                    {
                        'setting_id': setting.id,
                        'theme_id': setting.theme.id,
                        'theme_name': setting.theme.name,
                        'preferences': json.loads(setting.preferences) if setting.preferences else {},
                        'applied_at': setting.applied_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for setting in settings
                ]
                self.logger.info(f"Retrieved {len(settings_list)} theme settings for user ID '{user_id}'.")
                return settings_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving theme settings for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving theme settings for user ID '{user_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing ThemeCustomizationService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("ThemeCustomizationService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing ThemeCustomizationService: {e}", exc_info=True)
            raise ThemeCustomizationServiceError(f"Error closing ThemeCustomizationService: {e}")
