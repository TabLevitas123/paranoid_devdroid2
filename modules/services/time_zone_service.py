# services/time_zone_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import pytz
import requests
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class TimeZone(Base):
    __tablename__ = 'time_zones'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    time_zone_name = Column(String, unique=True, nullable=False)  # e.g., 'America/New_York'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserTimeZonePreference(Base):
    __tablename__ = 'user_time_zone_preferences'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    time_zone_id = Column(String, ForeignKey('time_zones.id'), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="time_zone_preferences")
    time_zone = relationship("TimeZone")

class TimeZoneServiceError(Exception):
    """Custom exception for TimeZoneService-related errors."""
    pass

class TimeZoneService:
    """
    Provides time zone management functionalities, including setting and retrieving user-specific
    time zones, converting timestamps between different time zones, handling daylight saving time changes,
    and integrating with third-party time zone databases or APIs. Utilizes SQLAlchemy for database
    interactions and ensures secure handling of time zone data and adherence to security regulations.
    """

    def __init__(self):
        """
        Initializes the TimeZoneService with necessary configurations and authentication.
        """
        self.logger = setup_logging('TimeZoneService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.time_zone_api_url = self.config_loader.get('TIME_ZONE_API_URL', 'https://api.timezonedb.com/v2.1/get-time-zone')
        self.time_zone_api_key_encrypted = self.config_loader.get('TIME_ZONE_API_KEY')
        self.time_zone_api_key = self.encryption_manager.decrypt_data(self.time_zone_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("TimeZoneService initialized successfully.")

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
                raise TimeZoneServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise TimeZoneServiceError(f"Error initializing database: {e}")

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
            raise TimeZoneServiceError(f"Unsupported database type '{db_type}'.")

    def load_time_zones(self) -> bool:
        """
        Loads all available time zones from pytz into the database.

        Returns:
            bool: True if time zones are loaded successfully, False otherwise.
        """
        try:
            self.logger.debug("Loading time zones into the database.")
            with self.lock:
                existing_time_zones = {tz.time_zone_name for tz in self.session.query(TimeZone).all()}
                for tz in pytz.all_timezones:
                    if tz not in existing_time_zones:
                        time_zone_entry = TimeZone(
                            time_zone_name=tz,
                            is_active=True
                        )
                        self.session.add(time_zone_entry)
                        self.logger.debug(f"Added time zone '{tz}' to the database.")
                self.session.commit()
                self.logger.info("All available time zones loaded successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while loading time zones: {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while loading time zones: {e}", exc_info=True)
            self.session.rollback()
            return False

    def set_user_time_zone(self, user_id: str, time_zone_name: str) -> bool:
        """
        Sets the preferred time zone for a user.

        Args:
            user_id (str): The unique identifier of the user.
            time_zone_name (str): The name of the time zone (e.g., 'America/New_York').

        Returns:
            bool: True if the time zone is set successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Setting time zone for user ID '{user_id}' to '{time_zone_name}'.")
            if time_zone_name not in pytz.all_timezones:
                self.logger.error(f"Time zone '{time_zone_name}' is not recognized.")
                return False

            with self.lock:
                time_zone = self.session.query(TimeZone).filter(TimeZone.time_zone_name == time_zone_name, TimeZone.is_active == True).first()
                if not time_zone:
                    self.logger.error(f"Time zone '{time_zone_name}' is not active or does not exist in the database.")
                    return False

                user_pref = self.session.query(UserTimeZonePreference).filter(UserTimeZonePreference.user_id == user_id).first()
                if user_pref:
                    user_pref.time_zone_id = time_zone.id
                    user_pref.updated_at = datetime.utcnow()
                    self.logger.debug(f"Updated existing time zone preference for user ID '{user_id}'.")
                else:
                    user_pref = UserTimeZonePreference(
                        user_id=user_id,
                        time_zone_id=time_zone.id
                    )
                    self.session.add(user_pref)
                    self.logger.debug(f"Set new time zone preference for user ID '{user_id}'.")

                self.session.commit()
                self.logger.info(f"Time zone for user ID '{user_id}' set to '{time_zone_name}' successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while setting time zone for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while setting time zone for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_user_time_zone(self, user_id: str) -> Optional[pytz.timezone]:
        """
        Retrieves the preferred time zone for a user.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[pytz.timezone]: The user's preferred time zone if set, else the default time zone.
        """
        try:
            self.logger.debug(f"Retrieving time zone preference for user ID '{user_id}'.")
            with self.lock:
                user_pref = self.session.query(UserTimeZonePreference).filter(UserTimeZonePreference.user_id == user_id).first()
                if user_pref:
                    time_zone = self.session.query(TimeZone).filter(TimeZone.id == user_pref.time_zone_id).first()
                    if time_zone and time_zone.time_zone_name in pytz.all_timezones:
                        self.logger.info(f"User ID '{user_id}' prefers time zone '{time_zone.time_zone_name}'.")
                        return pytz.timezone(time_zone.time_zone_name)
                self.logger.info(f"No time zone preference found for user ID '{user_id}'. Using default time zone.")
                return pytz.timezone(self.default_time_zone())
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving time zone for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving time zone for user ID '{user_id}': {e}", exc_info=True)
            return None

    def default_time_zone(self) -> str:
        """
        Retrieves the default time zone from configuration.

        Returns:
            str: The default time zone name.
        """
        return self.config_loader.get('DEFAULT_TIME_ZONE', 'UTC')

    def convert_time_to_user_time_zone(self, user_id: str, naive_datetime: datetime) -> Optional[datetime]:
        """
        Converts a naive datetime object to the user's preferred time zone.

        Args:
            user_id (str): The unique identifier of the user.
            naive_datetime (datetime): The naive datetime object to convert.

        Returns:
            Optional[datetime]: The timezone-aware datetime object if successful, else None.
        """
        try:
            self.logger.debug(f"Converting time '{naive_datetime}' to user ID '{user_id}' preferred time zone.")
            user_tz = self.get_user_time_zone(user_id)
            if user_tz:
                localized_datetime = user_tz.localize(naive_datetime)
                self.logger.debug(f"Converted time: '{localized_datetime}'.")
                return localized_datetime
            else:
                self.logger.error(f"Failed to retrieve time zone for user ID '{user_id}'.")
                return None
        except Exception as e:
            self.logger.error(f"Unexpected error while converting time for user ID '{user_id}': {e}", exc_info=True)
            return None

    def convert_time_from_user_time_zone(self, user_id: str, aware_datetime: datetime, target_time_zone_name: str) -> Optional[datetime]:
        """
        Converts a timezone-aware datetime object from the user's preferred time zone to a target time zone.

        Args:
            user_id (str): The unique identifier of the user.
            aware_datetime (datetime): The timezone-aware datetime object to convert.
            target_time_zone_name (str): The target time zone name (e.g., 'Europe/Berlin').

        Returns:
            Optional[datetime]: The converted datetime object if successful, else None.
        """
        try:
            self.logger.debug(f"Converting time '{aware_datetime}' from user ID '{user_id}' time zone to '{target_time_zone_name}'.")
            if target_time_zone_name not in pytz.all_timezones:
                self.logger.error(f"Target time zone '{target_time_zone_name}' is not recognized.")
                return None

            target_time_zone = pytz.timezone(target_time_zone_name)
            converted_datetime = aware_datetime.astimezone(target_time_zone)
            self.logger.debug(f"Converted time: '{converted_datetime}'.")
            return converted_datetime
        except Exception as e:
            self.logger.error(f"Unexpected error while converting time from user ID '{user_id}' to '{target_time_zone_name}': {e}", exc_info=True)
            return None

    def synchronize_time_zones(self) -> bool:
        """
        Synchronizes the list of time zones with an external API or database to ensure up-to-date information.

        Returns:
            bool: True if synchronization is successful, False otherwise.
        """
        try:
            self.logger.debug("Synchronizing time zones with external source.")
            # Example: Fetch updated time zones from an external API
            headers = {
                'Authorization': f"Bearer {self.time_zone_api_key}",
                'Content-Type': 'application/json'
            }
            params = {
                'format': 'json',
                'by': 'zone',
                'zone': 'all'
            }
            response = self.session_requests.get(
                self.time_zone_api_url,
                headers=headers,
                params=params,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to synchronize time zones. Status Code: {response.status_code}, Response: {response.text}")
                return False

            time_zones = response.json().get('zones', [])
            with self.lock:
                for tz in time_zones:
                    if not self.session.query(TimeZone).filter(TimeZone.time_zone_name == tz).first():
                        new_tz = TimeZone(
                            time_zone_name=tz,
                            is_active=True
                        )
                        self.session.add(new_tz)
                        self.logger.debug(f"Added new time zone '{tz}' to the database.")
                self.session.commit()
                self.logger.info("Time zones synchronized successfully.")
                return True
        except requests.RequestException as e:
            self.logger.error(f"Request exception while synchronizing time zones: {e}", exc_info=True)
            return False
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while synchronizing time zones: {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while synchronizing time zones: {e}", exc_info=True)
            self.session.rollback()
            return False

    def list_available_time_zones(self) -> Optional[List[str]]:
        """
        Lists all available and active time zones in the system.

        Returns:
            Optional[List[str]]: A list of active time zone names if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Listing all available and active time zones.")
            with self.lock:
                time_zones = self.session.query(TimeZone).filter(TimeZone.is_active == True).all()
                time_zones_list = [tz.time_zone_name for tz in time_zones]
                self.logger.info(f"Retrieved {len(time_zones_list)} active time zones.")
                return time_zones_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while listing time zones: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while listing time zones: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing TimeZoneService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("TimeZoneService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing TimeZoneService: {e}", exc_info=True)
            raise TimeZoneServiceError(f"Error closing TimeZoneService: {e}")
