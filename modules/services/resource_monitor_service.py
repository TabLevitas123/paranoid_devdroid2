# services/resource_monitor_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import json
import psutil
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class SystemResourceUsage(Base):
    __tablename__ = 'system_resource_usage'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow)
    cpu_usage = Column(Float, nullable=False)
    memory_usage = Column(Float, nullable=False)
    disk_usage = Column(Float, nullable=False)
    network_usage = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Alert(Base):
    __tablename__ = 'alerts'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    resource_type = Column(String, nullable=False)  # e.g., CPU, Memory, Disk, Network
    threshold = Column(Float, nullable=False)
    current_value = Column(Float, nullable=False)
    alert_level = Column(String, nullable=False)  # e.g., warning, critical
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ResourceMonitorServiceError(Exception):
    """Custom exception for ResourceMonitorService-related errors."""
    pass

class ResourceMonitorService:
    """
    Provides resource monitoring functionalities, including tracking CPU, memory, disk, and network usage,
    logging resource usage data, generating alerts based on predefined thresholds, and integrating with
    third-party alerting services. Utilizes SQLAlchemy for database interactions and ensures secure handling
    of monitoring data and adherence to security regulations.
    """

    def __init__(self):
        """
        Initializes the ResourceMonitorService with necessary configurations and authentication.
        """
        self.logger = setup_logging('ResourceMonitorService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.alerting_api_url = self.config_loader.get('ALERTING_API_URL', 'https://api.alertingservice.com/alerts')
        self.alerting_api_key_encrypted = self.config_loader.get('ALERTING_API_KEY')
        self.alerting_api_key = self.encryption_manager.decrypt_data(self.alerting_api_key_encrypted).decode('utf-8')
        self.monitoring_interval = self.config_loader.get('MONITORING_INTERVAL_SECONDS', 60)  # default to 60 seconds
        self.alert_thresholds = self.config_loader.get('ALERT_THRESHOLDS', {
            'CPU': 80.0,
            'Memory': 80.0,
            'Disk': 90.0,
            'Network': 1000.0  # in Mbps
        })
        self.session_requests = requests.Session()
        self.monitoring_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.monitoring_thread.start()
        self.logger.info("ResourceMonitorService initialized successfully.")

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
                raise ResourceMonitorServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise ResourceMonitorServiceError(f"Error initializing database: {e}")

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
            raise ResourceMonitorServiceError(f"Unsupported database type '{db_type}'.")

    def _monitor_resources(self):
        """
        Continuously monitors system resources at specified intervals.
        """
        self.logger.debug("Starting resource monitoring loop.")
        while True:
            try:
                self.logger.debug("Collecting system resource usage.")
                cpu = psutil.cpu_percent(interval=None)
                memory = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                network = self._get_network_usage()

                with self.lock:
                    usage = SystemResourceUsage(
                        cpu_usage=cpu,
                        memory_usage=memory,
                        disk_usage=disk,
                        network_usage=network
                    )
                    self.session.add(usage)
                    self.session.commit()
                    self.logger.info(f"Resource usage logged: CPU={cpu}%, Memory={memory}%, Disk={disk}%, Network={network}Mbps.")

                    # Check for alerts
                    self._check_and_trigger_alerts(cpu, memory, disk, network)

            except SQLAlchemyError as e:
                self.logger.error(f"Database error during resource monitoring: {e}", exc_info=True)
                self.session.rollback()
            except Exception as e:
                self.logger.error(f"Unexpected error during resource monitoring: {e}", exc_info=True)
            finally:
                threading.Event().wait(self.monitoring_interval)

    def _get_network_usage(self) -> float:
        """
        Calculates the current network usage in Mbps.

        Returns:
            float: The network usage in Mbps.
        """
        try:
            net_io = psutil.net_io_counters()
            # Simple calculation; in real scenarios, you'd track deltas over time
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            total_bytes = bytes_sent + bytes_recv
            # Convert to Mbps (assuming the monitoring interval is in seconds)
            # Here, as a placeholder, return a mock value
            # Implement actual calculation based on previous readings
            return float(total_bytes) / (1024 * 1024)  # Simplified
        except Exception as e:
            self.logger.error(f"Error calculating network usage: {e}", exc_info=True)
            return 0.0

    def _check_and_trigger_alerts(self, cpu: float, memory: float, disk: float, network: float):
        """
        Checks resource usage against thresholds and triggers alerts if necessary.

        Args:
            cpu (float): CPU usage percentage.
            memory (float): Memory usage percentage.
            disk (float): Disk usage percentage.
            network (float): Network usage in Mbps.
        """
        self.logger.debug("Checking resource usage against thresholds for alerts.")
        alerts_to_trigger = []

        if cpu > self.alert_thresholds.get('CPU', 80.0):
            alerts_to_trigger.append({
                'resource_type': 'CPU',
                'current_value': cpu,
                'threshold': self.alert_thresholds.get('CPU', 80.0),
                'alert_level': 'critical' if cpu > 90.0 else 'warning',
                'message': f"CPU usage is at {cpu}%, exceeding the threshold of {self.alert_thresholds.get('CPU', 80.0)}%."
            })

        if memory > self.alert_thresholds.get('Memory', 80.0):
            alerts_to_trigger.append({
                'resource_type': 'Memory',
                'current_value': memory,
                'threshold': self.alert_thresholds.get('Memory', 80.0),
                'alert_level': 'critical' if memory > 90.0 else 'warning',
                'message': f"Memory usage is at {memory}%, exceeding the threshold of {self.alert_thresholds.get('Memory', 80.0)}%."
            })

        if disk > self.alert_thresholds.get('Disk', 90.0):
            alerts_to_trigger.append({
                'resource_type': 'Disk',
                'current_value': disk,
                'threshold': self.alert_thresholds.get('Disk', 90.0),
                'alert_level': 'critical' if disk > 95.0 else 'warning',
                'message': f"Disk usage is at {disk}%, exceeding the threshold of {self.alert_thresholds.get('Disk', 90.0)}%."
            })

        if network > self.alert_thresholds.get('Network', 1000.0):
            alerts_to_trigger.append({
                'resource_type': 'Network',
                'current_value': network,
                'threshold': self.alert_thresholds.get('Network', 1000.0),
                'alert_level': 'critical' if network > 2000.0 else 'warning',
                'message': f"Network usage is at {network}Mbps, exceeding the threshold of {self.alert_thresholds.get('Network', 1000.0)}Mbps."
            })

        for alert in alerts_to_trigger:
            self.logger.debug(f"Triggering alert for {alert['resource_type']} usage.")
            self._trigger_alert(alert)

    def _trigger_alert(self, alert: Dict[str, Any]):
        """
        Triggers an alert by logging it to the database and sending it to an external alerting service.

        Args:
            alert (Dict[str, Any]): The alert details.
        """
        try:
            # Log alert to database
            alert_entry = Alert(
                resource_type=alert['resource_type'],
                threshold=alert['threshold'],
                current_value=alert['current_value'],
                alert_level=alert['alert_level'],
                message=alert['message']
            )
            self.session.add(alert_entry)
            self.session.commit()
            self.logger.info(f"Alert triggered: {alert['message']}")

            # Send alert to external alerting service
            headers = {
                'Authorization': f"Bearer {self.alerting_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'resource_type': alert['resource_type'],
                'current_value': alert['current_value'],
                'threshold': alert['threshold'],
                'alert_level': alert['alert_level'],
                'message': alert['message'],
                'timestamp': alert_entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }
            response = self.session_requests.post(
                self.alerting_api_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to send alert to external service. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Alert sent to external service successfully for {alert['resource_type']} usage.")
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while triggering alert for {alert['resource_type']}: {e}", exc_info=True)
            self.session.rollback()
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending alert for {alert['resource_type']}: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while triggering alert for {alert['resource_type']}: {e}", exc_info=True)

    def get_resource_usage_history(self, resource_type: str, start_date: Optional[datetime] = None,
                                   end_date: Optional[datetime] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the resource usage history for a specific resource type within an optional date range.

        Args:
            resource_type (str): The type of resource ('CPU', 'Memory', 'Disk', 'Network').
            start_date (Optional[datetime], optional): The start date for filtering. Defaults to None.
            end_date (Optional[datetime], optional): The end date for filtering. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of resource usage records if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving resource usage history for '{resource_type}' between '{start_date}' and '{end_date}'.")
            with self.lock:
                query = self.session.query(SystemResourceUsage).filter(SystemResourceUsage.timestamp >= start_date if start_date else True,
                                                                       SystemResourceUsage.timestamp <= end_date if end_date else True)
                if resource_type.lower() == 'cpu':
                    records = query.order_by(SystemResourceUsage.timestamp.desc()).all()
                    usage_list = [{'timestamp': record.timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'cpu_usage': record.cpu_usage} for record in records]
                elif resource_type.lower() == 'memory':
                    records = query.order_by(SystemResourceUsage.timestamp.desc()).all()
                    usage_list = [{'timestamp': record.timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'memory_usage': record.memory_usage} for record in records]
                elif resource_type.lower() == 'disk':
                    records = query.order_by(SystemResourceUsage.timestamp.desc()).all()
                    usage_list = [{'timestamp': record.timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'disk_usage': record.disk_usage} for record in records]
                elif resource_type.lower() == 'network':
                    records = query.order_by(SystemResourceUsage.timestamp.desc()).all()
                    usage_list = [{'timestamp': record.timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'network_usage': record.network_usage} for record in records]
                else:
                    self.logger.error(f"Invalid resource type '{resource_type}' requested.")
                    return None

                self.logger.info(f"Retrieved {len(usage_list)} records for resource '{resource_type}'.")
                return usage_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving resource usage history for '{resource_type}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving resource usage history for '{resource_type}': {e}", exc_info=True)
            return None

    def resolve_alert(self, alert_id: str) -> bool:
        """
        Marks an alert as resolved.

        Args:
            alert_id (str): The unique identifier of the alert.

        Returns:
            bool: True if the alert is marked as resolved successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Resolving alert ID '{alert_id}'.")
            with self.lock:
                alert = self.session.query(Alert).filter(Alert.id == alert_id).first()
                if not alert:
                    self.logger.error(f"Alert with ID '{alert_id}' does not exist.")
                    return False

                alert.resolved = True
                self.session.commit()
                self.logger.info(f"Alert ID '{alert_id}' marked as resolved successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while resolving alert ID '{alert_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while resolving alert ID '{alert_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_active_alerts(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all active (unresolved) alerts.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of active alerts if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Retrieving all active (unresolved) alerts.")
            with self.lock:
                alerts = self.session.query(Alert).filter(Alert.resolved == False).order_by(Alert.timestamp.desc()).all()
                alerts_list = [
                    {
                        'alert_id': alert.id,
                        'resource_type': alert.resource_type,
                        'current_value': alert.current_value,
                        'threshold': alert.threshold,
                        'alert_level': alert.alert_level,
                        'message': alert.message,
                        'timestamp': alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    } for alert in alerts
                ]
                self.logger.info(f"Retrieved {len(alerts_list)} active alerts.")
                return alerts_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving active alerts: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving active alerts: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing ResourceMonitorService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("ResourceMonitorService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing ResourceMonitorService: {e}", exc_info=True)
            raise ResourceMonitorServiceError(f"Error closing ResourceMonitorService: {e}")
