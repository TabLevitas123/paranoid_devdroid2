# services/update_manager_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import os
import requests
import shutil
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class Update(Base):
    __tablename__ = 'updates'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    version = Column(String, nullable=False)
    release_notes = Column(Text, nullable=False)
    download_url = Column(String, nullable=False)
    status = Column(String, default='Pending')  # Pending, Downloaded, Installed, Failed
    scheduled_at = Column(DateTime, nullable=True)
    installed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UpdateManagerServiceError(Exception):
    """Custom exception for UpdateManagerService-related errors."""
    pass

class UpdateManagerService:
    """
    Provides update management functionalities, including checking for updates,
    downloading and installing updates, scheduling update tasks, notifying users,
    and integrating with third-party update distribution systems. Utilizes SQLAlchemy
    for database interactions and ensures secure handling of update data and adherence
    to security regulations.
    """

    def __init__(self):
        """
        Initializes the UpdateManagerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('UpdateManagerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.update_server_url = self.config_loader.get('UPDATE_SERVER_URL', 'https://updates.example.com/api/check')
        self.update_api_key_encrypted = self.config_loader.get('UPDATE_API_KEY')
        self.update_api_key = self.encryption_manager.decrypt_data(self.update_api_key_encrypted).decode('utf-8')
        self.download_directory = self.config_loader.get('DOWNLOAD_DIRECTORY', '/var/updates/')
        self.installation_script_path = self.config_loader.get('INSTALLATION_SCRIPT_PATH', '/usr/local/bin/install_update.sh')
        self.notification_api_url = self.config_loader.get('NOTIFICATION_API_URL', 'https://api.notificationservice.com/notify')
        self.notification_api_key_encrypted = self.config_loader.get('NOTIFICATION_API_KEY')
        self.notification_api_key = self.encryption_manager.decrypt_data(self.notification_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.update_thread = threading.Thread(target=self._monitor_updates, daemon=True)
        self.update_thread.start()
        self.logger.info("UpdateManagerService initialized successfully.")

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
                raise UpdateManagerServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise UpdateManagerServiceError(f"Error initializing database: {e}")

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
            raise UpdateManagerServiceError(f"Unsupported database type '{db_type}'.")

    def _monitor_updates(self):
        """
        Continuously monitors for available updates at specified intervals.
        """
        self.logger.debug("Starting update monitoring loop.")
        monitoring_interval = self.config_loader.get('UPDATE_CHECK_INTERVAL_SECONDS', 3600)  # default to 1 hour
        while True:
            try:
                self.logger.debug("Checking for available updates.")
                latest_update = self._check_for_updates()
                if latest_update:
                    self.logger.info(f"New update available: Version {latest_update['version']}")
                    self._download_update(latest_update)
                else:
                    self.logger.info("No new updates available.")
            except Exception as e:
                self.logger.error(f"Error during update monitoring: {e}", exc_info=True)
            finally:
                threading.Event().wait(monitoring_interval)

    def _check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        Checks the update server for the latest available update.

        Returns:
            Optional[Dict[str, Any]]: The latest update details if available, else None.
        """
        try:
            headers = {
                'Authorization': f"Bearer {self.update_api_key}",
                'Content-Type': 'application/json'
            }
            response = self.session_requests.get(
                self.update_server_url,
                headers=headers,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to check for updates. Status Code: {response.status_code}, Response: {response.text}")
                return None

            update_info = response.json()
            current_version = self.config_loader.get('CURRENT_VERSION', '1.0.0')
            if self._is_newer_version(update_info.get('version'), current_version):
                return update_info
            else:
                return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception while checking for updates: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while checking for updates: {e}", exc_info=True)
            return None

    def _is_newer_version(self, new_version: str, current_version: str) -> bool:
        """
        Compares two version strings to determine if the new version is newer.

        Args:
            new_version (str): The new version string.
            current_version (str): The current version string.

        Returns:
            bool: True if new_version is newer than current_version, else False.
        """
        def version_tuple(v):
            return tuple(map(int, (v.split("."))))
        return version_tuple(new_version) > version_tuple(current_version)

    def _download_update(self, update_info: Dict[str, Any]) -> bool:
        """
        Downloads the update package from the provided URL.

        Args:
            update_info (Dict[str, Any]): The update information containing version and download URL.

        Returns:
            bool: True if download is successful, False otherwise.
        """
        try:
            version = update_info['version']
            download_url = update_info['download_url']
            self.logger.debug(f"Downloading update version '{version}' from '{download_url}'.")
            response = self.session_requests.get(download_url, stream=True, timeout=60)
            if response.status_code != 200:
                self.logger.error(f"Failed to download update. Status Code: {response.status_code}, Response: {response.text}")
                return False

            os.makedirs(self.download_directory, exist_ok=True)
            file_path = os.path.join(self.download_directory, f"update_{version}.zip")
            with open(file_path, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            self.logger.info(f"Update version '{version}' downloaded successfully to '{file_path}'.")

            # Log the downloaded update
            with self.lock:
                update_entry = Update(
                    version=version,
                    release_notes=update_info.get('release_notes', ''),
                    download_url=download_url,
                    status='Downloaded',
                    scheduled_at=None
                )
                self.session.add(update_entry)
                self.session.commit()
                update_id = update_entry.id
                self.logger.info(f"Update logged successfully with ID '{update_id}'.")
                return True
        except requests.RequestException as e:
            self.logger.error(f"Request exception while downloading update: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while downloading update: {e}", exc_info=True)
            return False

    def install_update(self, update_id: str) -> bool:
        """
        Installs the downloaded update.

        Args:
            update_id (str): The unique identifier of the update to install.

        Returns:
            bool: True if installation is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Installing update with ID '{update_id}'.")
            with self.lock:
                update = self.session.query(Update).filter(Update.id == update_id).first()
                if not update:
                    self.logger.error(f"Update with ID '{update_id}' does not exist.")
                    return False
                if update.status != 'Downloaded':
                    self.logger.error(f"Update with ID '{update_id}' is not in a downloadable state.")
                    return False

                # Execute the installation script with the update file as an argument
                update_file_path = os.path.join(self.download_directory, f"update_{update.version}.zip")
                if not os.path.exists(update_file_path):
                    self.logger.error(f"Update file '{update_file_path}' does not exist.")
                    update.status = 'Failed'
                    update.error_message = 'Update file not found.'
                    self.session.commit()
                    return False

                # Assuming the installation script accepts the file path as an argument
                installation_command = f"sh {self.installation_script_path} {update_file_path}"
                self.logger.debug(f"Executing installation command: {installation_command}")
                result = os.system(installation_command)
                if result != 0:
                    self.logger.error(f"Installation script failed with exit code {result}.")
                    update.status = 'Failed'
                    update.error_message = f"Installation script failed with exit code {result}."
                    self.session.commit()
                    return False

                # Update the status of the update
                update.status = 'Installed'
                update.installed_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Update ID '{update_id}' installed successfully.")

                # Notify users about the successful update
                self._notify_users_about_update(update)

                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while installing update ID '{update_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while installing update ID '{update_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def schedule_update_installation(self, update_id: str, scheduled_time: datetime) -> bool:
        """
        Schedules the installation of an update at a specified time.

        Args:
            update_id (str): The unique identifier of the update to schedule.
            scheduled_time (datetime): The time at which to install the update.

        Returns:
            bool: True if scheduling is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Scheduling installation of update ID '{update_id}' at '{scheduled_time}'.")
            with self.lock:
                update = self.session.query(Update).filter(Update.id == update_id).first()
                if not update:
                    self.logger.error(f"Update with ID '{update_id}' does not exist.")
                    return False
                if update.status != 'Downloaded':
                    self.logger.error(f"Update with ID '{update_id}' is not in a downloadable state.")
                    return False

                update.scheduled_at = scheduled_time
                self.session.commit()
                self.logger.info(f"Installation of update ID '{update_id}' scheduled at '{scheduled_time}' successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while scheduling installation for update ID '{update_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while scheduling installation for update ID '{update_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_users_about_update(self, update: 'Update'):
        """
        Sends notifications to all users about the successful installation of an update.

        Args:
            update (Update): The Update instance that was installed.
        """
        try:
            self.logger.debug(f"Notifying users about the installation of update ID '{update.id}'.")
            headers = {
                'Authorization': f"Bearer {self.notification_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'subject': f"Application Updated to Version {update.version}",
                'message': f"The application has been successfully updated to version {update.version}. Please restart the application to apply the changes."
            }
            response = self.session_requests.post(
                f"{self.notification_api_url}/users/notify",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify users about the update. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug("Users notified successfully about the update.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying users about the update: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying users about the update: {e}", exc_info=True)

    def list_available_updates(self) -> Optional[List[Dict[str, Any]]]:
        """
        Lists all available updates with their statuses.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of available updates if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Listing all available updates.")
            with self.lock:
                updates = self.session.query(Update).order_by(Update.reported_at.desc()).all()
                updates_list = [
                    {
                        'update_id': update.id,
                        'version': update.version,
                        'release_notes': update.release_notes,
                        'download_url': update.download_url,
                        'status': update.status,
                        'scheduled_at': update.scheduled_at.strftime('%Y-%m-%d %H:%M:%S') if update.scheduled_at else None,
                        'installed_at': update.installed_at.strftime('%Y-%m-%d %H:%M:%S') if update.installed_at else None,
                        'error_message': update.error_message
                    } for update in updates
                ]
                self.logger.info(f"Retrieved {len(updates_list)} available updates.")
                return updates_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while listing available updates: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while listing available updates: {e}", exc_info=True)
            return None

    def rollback_update(self, update_id: str) -> bool:
        """
        Rolls back a previously installed update.

        Args:
            update_id (str): The unique identifier of the update to rollback.

        Returns:
            bool: True if rollback is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Rolling back update ID '{update_id}'.")
            with self.lock:
                update = self.session.query(Update).filter(Update.id == update_id).first()
                if not update:
                    self.logger.error(f"Update with ID '{update_id}' does not exist.")
                    return False
                if update.status != 'Installed':
                    self.logger.error(f"Update with ID '{update_id}' is not in an installed state.")
                    return False

                # Execute the rollback script
                rollback_script_path = self.config_loader.get('ROLLBACK_SCRIPT_PATH', '/usr/local/bin/rollback_update.sh')
                rollback_command = f"sh {rollback_script_path} {update.download_url}"
                self.logger.debug(f"Executing rollback command: {rollback_command}")
                result = os.system(rollback_command)
                if result != 0:
                    self.logger.error(f"Rollback script failed with exit code {result}.")
                    update.status = 'Failed'
                    update.error_message = f"Rollback script failed with exit code {result}."
                    self.session.commit()
                    return False

                # Update the status of the update
                update.status = 'Rolled Back'
                update.installed_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Update ID '{update_id}' rolled back successfully.")

                # Notify users about the rollback
                self._notify_users_about_rollback(update)

                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while rolling back update ID '{update_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while rolling back update ID '{update_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_users_about_rollback(self, update: 'Update'):
        """
        Sends notifications to all users about the rollback of an update.

        Args:
            update (Update): The Update instance that was rolled back.
        """
        try:
            self.logger.debug(f"Notifying users about the rollback of update ID '{update.id}'.")
            headers = {
                'Authorization': f"Bearer {self.notification_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'subject': f"Update to Version {update.version} Rolled Back",
                'message': f"The recent update to version {update.version} has been rolled back due to unforeseen issues. We apologize for the inconvenience."
            }
            response = self.session_requests.post(
                f"{self.notification_api_url}/users/notify",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify users about the rollback. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug("Users notified successfully about the rollback.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying users about the rollback: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying users about the rollback: {e}", exc_info=True)

    def get_update_details(self, update_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the details of a specific update.

        Args:
            update_id (str): The unique identifier of the update.

        Returns:
            Optional[Dict[str, Any]]: The update details if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving details for update ID '{update_id}'.")
            with self.lock:
                update = self.session.query(Update).filter(Update.id == update_id).first()
                if not update:
                    self.logger.error(f"Update with ID '{update_id}' does not exist.")
                    return None

                update_details = {
                    'update_id': update.id,
                    'version': update.version,
                    'release_notes': update.release_notes,
                    'download_url': update.download_url,
                    'status': update.status,
                    'scheduled_at': update.scheduled_at.strftime('%Y-%m-%d %H:%M:%S') if update.scheduled_at else None,
                    'installed_at': update.installed_at.strftime('%Y-%m-%d %H:%M:%S') if update.installed_at else None,
                    'error_message': update.error_message,
                    'created_at': update.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': update.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                self.logger.info(f"Details for update ID '{update_id}' retrieved successfully.")
                return update_details
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving update ID '{update_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving update ID '{update_id}': {e}", exc_info=True)
            return None

    def list_all_updates(self) -> Optional[List[Dict[str, Any]]]:
        """
        Lists all updates with their statuses.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of all updates if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Listing all updates.")
            with self.lock:
                updates = self.session.query(Update).order_by(Update.reported_at.desc()).all()
                updates_list = [
                    {
                        'update_id': update.id,
                        'version': update.version,
                        'release_notes': update.release_notes,
                        'download_url': update.download_url,
                        'status': update.status,
                        'scheduled_at': update.scheduled_at.strftime('%Y-%m-%d %H:%M:%S') if update.scheduled_at else None,
                        'installed_at': update.installed_at.strftime('%Y-%m-%d %H:%M:%S') if update.installed_at else None,
                        'error_message': update.error_message
                    } for update in updates
                ]
                self.logger.info(f"Retrieved {len(updates_list)} updates.")
                return updates_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while listing updates: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while listing updates: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing UpdateManagerService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("UpdateManagerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing UpdateManagerService: {e}", exc_info=True)
            raise UpdateManagerServiceError(f"Error closing UpdateManagerService: {e}")
