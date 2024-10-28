# services/multi_language_support_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import os
import json
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import gettext
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class Language(Base):
    __tablename__ = 'languages'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    language_code = Column(String, unique=True, nullable=False)  # e.g., en, es, fr
    language_name = Column(String, nullable=False)  # e.g., English, Spanish, French
    is_active = Column(Boolean, default=True)
    translations_path = Column(String, nullable=False)  # Path to the .mo files
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserLanguagePreference(Base):
    __tablename__ = 'user_language_preferences'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    language_id = Column(String, ForeignKey('languages.id'), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="language_preferences")
    language = relationship("Language")

class MultiLanguageSupportServiceError(Exception):
    """Custom exception for MultiLanguageSupportService-related errors."""
    pass

class MultiLanguageSupportService:
    """
    Provides multi-language support functionalities, including loading and managing
    language translations, allowing users to select their preferred language,
    dynamically switching application languages, and integrating with third-party
    translation services. Utilizes SQLAlchemy for database interactions and ensures
    secure handling of language data and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the MultiLanguageSupportService with necessary configurations and authentication.
        """
        self.logger = setup_logging('MultiLanguageSupportService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.translations_directory = self.config_loader.get('TRANSLATIONS_DIRECTORY', '/var/app/translations/')
        self.default_language_code = self.config_loader.get('DEFAULT_LANGUAGE_CODE', 'en')
        self.supported_languages = self.config_loader.get('SUPPORTED_LANGUAGES', ['en'])
        self.session_requests = requests.Session()
        self.logger.info("MultiLanguageSupportService initialized successfully.")

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
                raise MultiLanguageSupportServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise MultiLanguageSupportServiceError(f"Error initializing database: {e}")

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
            raise MultiLanguageSupportServiceError(f"Unsupported database type '{db_type}'.")

    def load_languages(self) -> bool:
        """
        Loads supported languages into the database and ensures their translation files are present.

        Returns:
            bool: True if languages are loaded successfully, False otherwise.
        """
        try:
            self.logger.debug("Loading supported languages into the database.")
            with self.lock:
                for lang_code in self.supported_languages:
                    if self.session.query(Language).filter(Language.language_code == lang_code).first():
                        self.logger.debug(f"Language '{lang_code}' already exists in the database.")
                        continue

                    language_name = self._get_language_name(lang_code)
                    translations_path = os.path.join(self.translations_directory, lang_code, 'LC_MESSAGES', 'messages.mo')
                    if not os.path.exists(translations_path):
                        self.logger.error(f"Translation file for language '{lang_code}' not found at '{translations_path}'.")
                        continue

                    language = Language(
                        language_code=lang_code,
                        language_name=language_name,
                        is_active=True,
                        translations_path=translations_path
                    )
                    self.session.add(language)
                    self.logger.info(f"Loaded language '{language_name}' with code '{lang_code}' into the database.")

                self.session.commit()
                self.logger.info("All supported languages loaded successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while loading languages: {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while loading languages: {e}", exc_info=True)
            self.session.rollback()
            return False

    def _get_language_name(self, language_code: str) -> str:
        """
        Retrieves the language name based on its code.

        Args:
            language_code (str): The language code (e.g., 'en', 'es').

        Returns:
            str: The name of the language.
        """
        try:
            # This can be replaced with a more comprehensive mapping or an external service
            language_map = {
                'en': 'English',
                'es': 'Spanish',
                'fr': 'French',
                'de': 'German',
                'zh': 'Chinese',
                'jp': 'Japanese',
                'ru': 'Russian',
                'ar': 'Arabic',
                'pt': 'Portuguese',
                'hi': 'Hindi'
            }
            return language_map.get(language_code, 'Unknown')
        except Exception as e:
            self.logger.error(f"Error retrieving language name for code '{language_code}': {e}", exc_info=True)
            return 'Unknown'

    def set_user_language_preference(self, user_id: str, language_code: str) -> bool:
        """
        Sets the preferred language for a user.

        Args:
            user_id (str): The unique identifier of the user.
            language_code (str): The language code to set as preference.

        Returns:
            bool: True if the preference is set successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting language preference for user ID '{user_id}' to '{language_code}'.")
            with self.lock:
                language = self.session.query(Language).filter(Language.language_code == language_code, Language.is_active == True).first()
                if not language:
                    self.logger.error(f"Language '{language_code}' is not supported or inactive.")
                    return False

                user_pref = self.session.query(UserLanguagePreference).filter(UserLanguagePreference.user_id == user_id).first()
                if user_pref:
                    user_pref.language_id = language.id
                    user_pref.updated_at = datetime.utcnow()
                    self.logger.debug(f"Updated existing language preference for user ID '{user_id}'.")
                else:
                    user_pref = UserLanguagePreference(
                        user_id=user_id,
                        language_id=language.id
                    )
                    self.session.add(user_pref)
                    self.logger.debug(f"Set new language preference for user ID '{user_id}'.")

                self.session.commit()
                self.logger.info(f"Language preference for user ID '{user_id}' set to '{language_code}' successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while setting language preference for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while setting language preference for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_user_language(self, user_id: str) -> Optional[str]:
        """
        Retrieves the preferred language code for a user.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[str]: The language code if found, else None.
        """
        try:
            self.logger.debug(f"Retrieving language preference for user ID '{user_id}'.")
            with self.lock:
                user_pref = self.session.query(UserLanguagePreference).filter(UserLanguagePreference.user_id == user_id).first()
                if user_pref:
                    language = self.session.query(Language).filter(Language.id == user_pref.language_id).first()
                    if language:
                        self.logger.info(f"User ID '{user_id}' prefers language '{language.language_code}'.")
                        return language.language_code
                self.logger.info(f"No language preference found for user ID '{user_id}'. Using default language '{self.default_language_code}'.")
                return self.default_language_code
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving language preference for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving language preference for user ID '{user_id}': {e}", exc_info=True)
            return None

    def load_user_translations(self, user_id: str) -> Optional[gettext.NullTranslations]:
        """
        Loads the translation catalog for a user's preferred language.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[gettext.NullTranslations]: The translation catalog if successful, else None.
        """
        try:
            language_code = self.get_user_language(user_id)
            self.logger.debug(f"Loading translations for language code '{language_code}'.")
            with self.lock:
                language = self.session.query(Language).filter(Language.language_code == language_code, Language.is_active == True).first()
                if not language:
                    self.logger.error(f"Language '{language_code}' is not supported or inactive.")
                    return None

                translation = gettext.translation('messages', localedir=self.translations_directory, languages=[language_code], fallback=True)
                self.logger.info(f"Translations loaded successfully for language '{language_code}'.")
                return translation
        except FileNotFoundError:
            self.logger.error(f"Translation file for language '{language_code}' not found.")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while loading translations for language '{language_code}': {e}", exc_info=True)
            return None

    def translate_text(self, user_id: str, text: str) -> str:
        """
        Translates a given text to the user's preferred language.

        Args:
            user_id (str): The unique identifier of the user.
            text (str): The text to translate.

        Returns:
            str: The translated text.
        """
        try:
            self.logger.debug(f"Translating text for user ID '{user_id}'.")
            translation = self.load_user_translations(user_id)
            if translation:
                translated_text = translation.gettext(text)
                self.logger.debug(f"Translated text: '{translated_text}'.")
                return translated_text
            else:
                self.logger.warning(f"Translations not loaded for user ID '{user_id}'. Returning original text.")
                return text
        except Exception as e:
            self.logger.error(f"Unexpected error while translating text for user ID '{user_id}': {e}", exc_info=True)
            return text

    def add_new_language(self, language_code: str, language_name: str, translation_file_path: str) -> bool:
        """
        Adds a new language to the system.

        Args:
            language_code (str): The language code (e.g., 'de', 'it').
            language_name (str): The name of the language.
            translation_file_path (str): The path to the compiled translation file (.mo).

        Returns:
            bool: True if the language is added successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Adding new language '{language_name}' with code '{language_code}'.")
            with self.lock:
                if self.session.query(Language).filter(Language.language_code == language_code).first():
                    self.logger.error(f"Language with code '{language_code}' already exists.")
                    return False

                if not os.path.exists(translation_file_path):
                    self.logger.error(f"Translation file '{translation_file_path}' does not exist.")
                    return False

                language = Language(
                    language_code=language_code,
                    language_name=language_name,
                    is_active=True,
                    translations_path=translation_file_path
                )
                self.session.add(language)
                self.session.commit()
                self.logger.info(f"Language '{language_name}' with code '{language_code}' added successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding new language '{language_code}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while adding new language '{language_code}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def deactivate_language(self, language_code: str) -> bool:
        """
        Deactivates a language, preventing it from being used by users.

        Args:
            language_code (str): The language code to deactivate.

        Returns:
            bool: True if the language is deactivated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Deactivating language with code '{language_code}'.")
            with self.lock:
                language = self.session.query(Language).filter(Language.language_code == language_code).first()
                if not language:
                    self.logger.error(f"Language with code '{language_code}' does not exist.")
                    return False

                language.is_active = False
                self.session.commit()
                self.logger.info(f"Language '{language.language_name}' with code '{language_code}' deactivated successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while deactivating language '{language_code}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while deactivating language '{language_code}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def list_active_languages(self) -> Optional[List[Dict[str, Any]]]:
        """
        Lists all active languages available in the system.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of active languages if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Listing all active languages.")
            with self.lock:
                languages = self.session.query(Language).filter(Language.is_active == True).all()
                languages_list = [
                    {
                        'language_id': lang.id,
                        'language_code': lang.language_code,
                        'language_name': lang.language_name,
                        'translations_path': lang.translations_path,
                        'created_at': lang.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': lang.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for lang in languages
                ]
                self.logger.info(f"Retrieved {len(languages_list)} active languages.")
                return languages_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while listing active languages: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while listing active languages: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing MultiLanguageSupportService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("MultiLanguageSupportService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing MultiLanguageSupportService: {e}", exc_info=True)
            raise MultiLanguageSupportServiceError(f"Error closing MultiLanguageSupportService: {e}")
