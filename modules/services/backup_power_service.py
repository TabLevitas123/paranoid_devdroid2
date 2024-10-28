# services/backup_power_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import requests
import json
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class BackupPowerDevice(Base):
    __tablename__ = 'backup_power_devices'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_name = Column(String, unique=True, nullable=False)
    device_type = Column(String, nullable=False)  # e.g., UPS, Generator
    status = Column(String, default='offline')  # online, offline, maintenance
    last_checked = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    power_logs = relationship("PowerLog", back_populates="device")

class PowerLog(Base):
    __tablename__ = 'power_logs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, ForeignKey('backup_power_devices.id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event = Column(String, nullable=False)  # e.g., power_on, power_off, error
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    device = relationship("BackupPowerDevice", back_populates="power_logs")

class BackupPowerServiceError(Exception):
    """Custom exception for BackupPowerService-related errors."""
    pass

class BackupPowerService:
    """
    Provides backup power management functionalities, including monitoring backup power devices,
    logging power events, scheduling maintenance, and integrating with third-party APIs for device
    status updates and notifications. Utilizes SQLAlchemy for database interactions and ensures
    secure handling of device data and adherence to security regulations.
    """

    def __init__(self):
        """
        Initializes the BackupPowerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('BackupPowerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.device_api_url = self.config_loader.get('DEVICE_API_URL', 'https://api.backuppower.com/devices')
        self.device_api_key_encrypted = self.config_loader.get('DEVICE_API_KEY')
        self.device_api_key = self.encryption_manager.decrypt_data(self.device_api_key_encrypted).decode('utf-8')
        self.notification_api_url = self.config_loader.get('NOTIFICATION_API_URL', 'https://api.notification.com')
        self.notification_api_key_encrypted = self.config_loader.get('NOTIFICATION_API_KEY')
        self.notification_api_key = self.encryption_manager.decrypt_data(self.notification_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.monitoring_interval = self.config_loader.get('MONITORING_INTERVAL_SECONDS', 60)  # default to 60 seconds
        self.logger.info("BackupPowerService initialized successfully.")

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
                raise BackupPowerServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise BackupPowerServiceError(f"Error initializing database: {e}")

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
            raise BackupPowerServiceError(f"Unsupported database type '{db_type}'.")

    def register_backup_power_device(self, device_name: str, device_type: str) -> Optional[str]:
        """
        Registers a new backup power device.

        Args:
            device_name (str): The name of the backup power device.
            device_type (str): The type of the device (e.g., UPS, Generator).

        Returns:
            Optional[str]: The device ID if registration is successful, else None.
        """
        try:
            self.logger.debug(f"Registering backup power device '{device_name}' of type '{device_type}'.")
            with self.lock:
                existing_device = self.session.query(BackupPowerDevice).filter(BackupPowerDevice.device_name.ilike(device_name)).first()
                if existing_device:
                    self.logger.error(f"Backup power device '{device_name}' already exists.")
                    return None

                device = BackupPowerDevice(
                    device_name=device_name,
                    device_type=device_type,
                    status='offline',
                    last_checked=datetime.utcnow()
                )
                self.session.add(device)
                self.session.commit()
                device_id = device.id
                self.logger.info(f"Backup power device '{device_name}' registered successfully with ID '{device_id}'.")
                return device_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while registering device '{device_name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while registering device '{device_name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_device_status(self, device_id: str, status: str) -> bool:
        """
        Updates the status of a backup power device.

        Args:
            device_id (str): The unique identifier of the device.
            status (str): The new status of the device ('online', 'offline', 'maintenance').

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating status of device ID '{device_id}' to '{status}'.")
            if status not in ['online', 'offline', 'maintenance']:
                self.logger.error("Invalid status. Must be 'online', 'offline', or 'maintenance'.")
                return False

            with self.lock:
                device = self.session.query(BackupPowerDevice).filter(BackupPowerDevice.id == device_id).first()
                if not device:
                    self.logger.error(f"Backup power device with ID '{device_id}' does not exist.")
                    return False

                device.status = status
                device.last_checked = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Status of device ID '{device_id}' updated to '{status}' successfully.")

                # Optionally, notify administrators about the status change
                self._notify_admins_device_status_change(device)

                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating status for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating status for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_admins_device_status_change(self, device: 'BackupPowerDevice'):
        """
        Notifies administrators about a backup power device status change.

        Args:
            device (BackupPowerDevice): The BackupPowerDevice instance.
        """
        try:
            self.logger.debug(f"Notifying administrators about status change of device '{device.device_name}' to '{device.status}'.")
            headers = {
                'Authorization': f"Bearer {self.notification_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'subject': f"Backup Power Device '{device.device_name}' Status Update",
                'message': f"The backup power device '{device.device_name}' is now '{device.status}'. Last checked at {device.last_checked.strftime('%Y-%m-%d %H:%M:%S')}."
            }
            response = self.session_requests.post(
                f"{self.notification_api_url}/admin/notify",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify administrators about device status change. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Administrators notified successfully about device '{device.device_name}' status change.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying administrators about device '{device.device_name}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying administrators about device '{device.device_name}': {e}", exc_info=True)

    def log_power_event(self, device_id: str, event: str, details: Optional[str] = None) -> Optional[str]:
        """
        Logs a power event for a backup power device.

        Args:
            device_id (str): The unique identifier of the device.
            event (str): The type of event (e.g., power_on, power_off, error).
            details (Optional[str], optional): Additional details about the event. Defaults to None.

        Returns:
            Optional[str]: The power log ID if logging is successful, else None.
        """
        try:
            self.logger.debug(f"Logging power event '{event}' for device ID '{device_id}' with details '{details}'.")
            with self.lock:
                device = self.session.query(BackupPowerDevice).filter(BackupPowerDevice.id == device_id).first()
                if not device:
                    self.logger.error(f"Backup power device with ID '{device_id}' does not exist.")
                    return None

                power_log = PowerLog(
                    device_id=device_id,
                    event=event,
                    details=details
                )
                self.session.add(power_log)
                self.session.commit()
                power_log_id = power_log.id
                self.logger.info(f"Power event '{event}' logged successfully with ID '{power_log_id}' for device ID '{device_id}'.")
                return power_log_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while logging power event for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while logging power event for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def schedule_maintenance(self, device_id: str, maintenance_time: datetime, description: Optional[str] = None) -> Optional[str]:
        """
        Schedules maintenance for a backup power device.

        Args:
            device_id (str): The unique identifier of the device.
            maintenance_time (datetime): The scheduled time for maintenance.
            description (Optional[str], optional): A description of the maintenance. Defaults to None.

        Returns:
            Optional[str]: The power log ID for the maintenance event if scheduling is successful, else None.
        """
        try:
            self.logger.debug(f"Scheduling maintenance for device ID '{device_id}' at '{maintenance_time}' with description '{description}'.")
            with self.lock:
                device = self.session.query(BackupPowerDevice).filter(BackupPowerDevice.id == device_id).first()
                if not device:
                    self.logger.error(f"Backup power device with ID '{device_id}' does not exist.")
                    return None

                # Update device status to 'maintenance'
                device.status = 'maintenance'
                device.last_checked = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Device ID '{device_id}' status set to 'maintenance'.")

                # Log the maintenance event
                maintenance_log = PowerLog(
                    device_id=device_id,
                    event='maintenance_scheduled',
                    details=description
                )
                self.session.add(maintenance_log)
                self.session.commit()
                maintenance_log_id = maintenance_log.id
                self.logger.info(f"Maintenance event scheduled successfully with ID '{maintenance_log_id}' for device ID '{device_id}'.")

                # Optionally, notify administrators about the scheduled maintenance
                self._notify_admins_scheduled_maintenance(device, maintenance_time, description)

                return maintenance_log_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while scheduling maintenance for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while scheduling maintenance for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _notify_admins_scheduled_maintenance(self, device: 'BackupPowerDevice', maintenance_time: datetime, description: Optional[str]):
        """
        Notifies administrators about a scheduled maintenance for a backup power device.

        Args:
            device (BackupPowerDevice): The BackupPowerDevice instance.
            maintenance_time (datetime): The scheduled time for maintenance.
            description (Optional[str]): A description of the maintenance.
        """
        try:
            self.logger.debug(f"Notifying administrators about scheduled maintenance for device '{device.device_name}' at '{maintenance_time}'.")
            headers = {
                'Authorization': f"Bearer {self.notification_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'subject': f"Scheduled Maintenance for Backup Power Device '{device.device_name}'",
                'message': f"The backup power device '{device.device_name}' is scheduled for maintenance at {maintenance_time.strftime('%Y-%m-%d %H:%M:%S')}. Description: {description or 'No description provided.'}"
            }
            response = self.session_requests.post(
                f"{self.notification_api_url}/admin/notify",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify administrators about scheduled maintenance. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Administrators notified successfully about scheduled maintenance for device '{device.device_name}'.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying administrators about maintenance for device '{device.device_name}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying administrators about maintenance for device '{device.device_name}': {e}", exc_info=True)

    def perform_status_check(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Performs a status check on a backup power device using an external device monitoring API.

        Args:
            device_id (str): The unique identifier of the device.

        Returns:
            Optional[Dict[str, Any]]: The status data if successful, else None.
        """
        try:
            self.logger.debug(f"Performing status check for device ID '{device_id}'.")
            with self.lock:
                device = self.session.query(BackupPowerDevice).filter(BackupPowerDevice.id == device_id).first()
                if not device:
                    self.logger.error(f"Backup power device with ID '{device_id}' does not exist.")
                    return None

                headers = {
                    'Authorization': f"Bearer {self.device_api_key}",
                    'Content-Type': 'application/json'
                }
                params = {
                    'device_id': device_id
                }
                response = self.session_requests.get(
                    self.device_api_url,
                    headers=headers,
                    params=params,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to perform status check for device ID '{device_id}'. Status Code: {response.status_code}, Response: {response.text}")
                    return None

                status_data = response.json()
                device.status = status_data.get('status', device.status)
                device.last_checked = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Status check for device ID '{device_id}' completed successfully with status '{device.status}'.")
                return status_data
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while performing status check for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while performing status check for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def schedule_regular_status_checks(self, device_id: str, interval_seconds: int = 3600) -> bool:
        """
        Schedules regular status checks for a backup power device at specified intervals.

        Args:
            device_id (str): The unique identifier of the device.
            interval_seconds (int, optional): The interval in seconds between status checks. Defaults to 3600 (1 hour).

        Returns:
            bool: True if scheduling is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Scheduling regular status checks for device ID '{device_id}' every '{interval_seconds}' seconds.")
            with self.lock:
                # Here, we can implement a background thread or a scheduler like APScheduler
                # For simplicity, we'll assume a background thread is started here

                def status_check_loop():
                    while True:
                        self.perform_status_check(device_id)
                        threading.Event().wait(interval_seconds)

                status_thread = threading.Thread(target=status_check_loop, daemon=True)
                status_thread.start()
                self.logger.info(f"Regular status checks scheduled successfully for device ID '{device_id}'.")
                return True
        except Exception as e:
            self.logger.error(f"Error while scheduling regular status checks for device ID '{device_id}': {e}", exc_info=True)
            return False

    def get_device_power_logs(self, device_id: str, start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the power logs for a specific backup power device based on optional date filters.

        Args:
            device_id (str): The unique identifier of the device.
            start_date (Optional[datetime], optional): The start date for filtering logs. Defaults to None.
            end_date (Optional[datetime], optional): The end date for filtering logs. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of power logs if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving power logs for device ID '{device_id}' with filters start_date='{start_date}', end_date='{end_date}'.")
            with self.lock:
                query = self.session.query(PowerLog).filter(PowerLog.device_id == device_id)
                if start_date:
                    query = query.filter(PowerLog.timestamp >= start_date)
                if end_date:
                    query = query.filter(PowerLog.timestamp <= end_date)

                logs = query.order_by(PowerLog.timestamp.desc()).all()
                logs_list = [
                    {
                        'log_id': log.id,
                        'event': log.event,
                        'details': log.details,
                        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    } for log in logs
                ]
                self.logger.info(f"Retrieved {len(logs_list)} power logs for device ID '{device_id}'.")
                return logs_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving power logs for device ID '{device_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving power logs for device ID '{device_id}': {e}", exc_info=True)
            return None

    def initiate_emergency_shutdown(self, device_id: str, reason: str) -> bool:
        """
        Initiates an emergency shutdown of a backup power device.

        Args:
            device_id (str): The unique identifier of the device.
            reason (str): The reason for the emergency shutdown.

        Returns:
            bool: True if the shutdown is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Initiating emergency shutdown for device ID '{device_id}' due to '{reason}'.")
            with self.lock:
                device = self.session.query(BackupPowerDevice).filter(BackupPowerDevice.id == device_id).first()
                if not device:
                    self.logger.error(f"Backup power device with ID '{device_id}' does not exist.")
                    return False

                # Send shutdown command via external device API
                headers = {
                    'Authorization': f"Bearer {self.device_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'device_id': device_id,
                    'command': 'shutdown',
                    'reason': reason
                }
                response = self.session_requests.post(
                    f"{self.device_api_url}/command",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception(f"Device API responded with status code {response.status_code}: {response.text}")

                # Update device status to 'offline'
                device.status = 'offline'
                device.last_checked = datetime.utcnow()
                self.session.commit()

                # Log the shutdown event
                shutdown_log = PowerLog(
                    device_id=device_id,
                    event='emergency_shutdown',
                    details=reason
                )
                self.session.add(shutdown_log)
                self.session.commit()
                shutdown_log_id = shutdown_log.id
                self.logger.info(f"Emergency shutdown initiated successfully with log ID '{shutdown_log_id}' for device ID '{device_id}'.")

                # Notify administrators about the emergency shutdown
                self._notify_admins_emergency_shutdown(device, reason)

                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while initiating emergency shutdown for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while initiating emergency shutdown for device ID '{device_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_admins_emergency_shutdown(self, device: 'BackupPowerDevice', reason: str):
        """
        Notifies administrators about an emergency shutdown of a backup power device.

        Args:
            device (BackupPowerDevice): The BackupPowerDevice instance.
            reason (str): The reason for the emergency shutdown.
        """
        try:
            self.logger.debug(f"Notifying administrators about emergency shutdown of device '{device.device_name}'.")
            headers = {
                'Authorization': f"Bearer {self.notification_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'subject': f"Emergency Shutdown of Backup Power Device '{device.device_name}'",
                'message': f"The backup power device '{device.device_name}' has been shut down due to the following reason: {reason}. Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}."
            }
            response = self.session_requests.post(
                f"{self.notification_api_url}/admin/notify",
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to notify administrators about emergency shutdown. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Administrators notified successfully about emergency shutdown of device '{device.device_name}'.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying administrators about emergency shutdown of device '{device.device_name}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying administrators about emergency shutdown of device '{device.device_name}': {e}", exc_info=True)

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing BackupPowerService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("BackupPowerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing BackupPowerService: {e}", exc_info=True)
            raise BackupPowerServiceError(f"Error closing BackupPowerService: {e}")
