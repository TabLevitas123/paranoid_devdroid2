# services/performance_analytics_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import json
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
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

class PerformanceReport(Base):
    __tablename__ = 'performance_reports'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_name = Column(String, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    report_data = Column(Text, nullable=False)  # JSON string containing report details
    chart_image = Column(Text, nullable=False)  # Base64 encoded image
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PerformanceAnalyticsServiceError(Exception):
    """Custom exception for PerformanceAnalyticsService-related errors."""
    pass

class PerformanceAnalyticsService:
    """
    Provides performance analytics functionalities, including analyzing system resource usage data,
    generating comprehensive reports, visualizing performance metrics, and integrating with
    third-party analytics and reporting tools. Utilizes SQLAlchemy for database interactions and
    ensures secure handling of performance data and adherence to security regulations.
    """

    def __init__(self):
        """
        Initializes the PerformanceAnalyticsService with necessary configurations and authentication.
        """
        self.logger = setup_logging('PerformanceAnalyticsService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.analytics_api_url = self.config_loader.get('ANALYTICS_API_URL', 'https://api.analyticsservice.com/reports')
        self.analytics_api_key_encrypted = self.config_loader.get('ANALYTICS_API_KEY')
        self.analytics_api_key = self.encryption_manager.decrypt_data(self.analytics_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("PerformanceAnalyticsService initialized successfully.")

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
                raise PerformanceAnalyticsServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise PerformanceAnalyticsServiceError(f"Error initializing database: {e}")

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
            raise PerformanceAnalyticsServiceError(f"Unsupported database type '{db_type}'.")

    def generate_performance_report(self, report_name: str, start_date: Optional[datetime] = None,
                                    end_date: Optional[datetime] = None) -> Optional[str]:
        """
        Generates a comprehensive performance report based on system resource usage data.

        Args:
            report_name (str): The name of the performance report.
            start_date (Optional[datetime], optional): The start date for the report data. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the report data. Defaults to None.

        Returns:
            Optional[str]: The report ID if generation is successful, else None.
        """
        try:
            self.logger.debug(f"Generating performance report '{report_name}' from '{start_date}' to '{end_date}'.")
            with self.lock:
                query = self.session.query(SystemResourceUsage)
                if start_date:
                    query = query.filter(SystemResourceUsage.timestamp >= start_date)
                if end_date:
                    query = query.filter(SystemResourceUsage.timestamp <= end_date)
                data = query.order_by(SystemResourceUsage.timestamp).all()

                if not data:
                    self.logger.error("No data available for the specified date range.")
                    return None

                # Convert data to DataFrame for analysis
                df = pd.DataFrame([{
                    'timestamp': record.timestamp,
                    'CPU': record.cpu_usage,
                    'Memory': record.memory_usage,
                    'Disk': record.disk_usage,
                    'Network': record.network_usage
                } for record in data])

                # Perform analysis
                summary = df.describe().to_dict()
                correlation = df.corr().to_dict()

                # Generate visualization
                chart_image = self._generate_performance_chart(df, report_name)

                # Compile report data
                report_data = {
                    'report_name': report_name,
                    'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    'summary': summary,
                    'correlation': correlation,
                    'start_date': start_date.strftime('%Y-%m-%d %H:%M:%S') if start_date else None,
                    'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S') if end_date else None
                }

                # Encode chart image to base64
                chart_base64 = base64.b64encode(chart_image.getvalue()).decode('utf-8')

                # Save report to database
                report = PerformanceReport(
                    report_name=report_name,
                    generated_at=datetime.utcnow(),
                    report_data=json.dumps(report_data),
                    chart_image=chart_base64
                )
                self.session.add(report)
                self.session.commit()
                report_id = report.id
                self.logger.info(f"Performance report '{report_name}' generated successfully with ID '{report_id}'.")
                return report_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while generating performance report '{report_name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while generating performance report '{report_name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _generate_performance_chart(self, df: pd.DataFrame, report_name: str) -> io.BytesIO:
        """
        Generates a performance chart from the DataFrame and returns it as a BytesIO object.

        Args:
            df (pd.DataFrame): The DataFrame containing resource usage data.
            report_name (str): The name of the report for chart titling.

        Returns:
            io.BytesIO: The in-memory bytes buffer containing the chart image.
        """
        try:
            self.logger.debug(f"Generating performance chart for report '{report_name}'.")
            plt.figure(figsize=(10, 6))
            sns.lineplot(x='timestamp', y='CPU', data=df, label='CPU Usage (%)')
            sns.lineplot(x='timestamp', y='Memory', data=df, label='Memory Usage (%)')
            sns.lineplot(x='timestamp', y='Disk', data=df, label='Disk Usage (%)')
            sns.lineplot(x='timestamp', y='Network', data=df, label='Network Usage (Mbps)')
            plt.title(f"Performance Report: {report_name}")
            plt.xlabel("Timestamp")
            plt.ylabel("Usage")
            plt.legend()
            plt.tight_layout()

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png')
            plt.close()
            img_buffer.seek(0)
            self.logger.debug(f"Performance chart for report '{report_name}' generated successfully.")
            return img_buffer
        except Exception as e:
            self.logger.error(f"Error generating performance chart for report '{report_name}': {e}", exc_info=True)
            raise PerformanceAnalyticsServiceError(f"Error generating performance chart: {e}")

    def send_report_via_email(self, report_id: str, user_email: str) -> bool:
        """
        Sends the performance report to a user via email using an external analytics API.

        Args:
            report_id (str): The unique identifier of the performance report.
            user_email (str): The email address of the user.

        Returns:
            bool: True if the report is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Sending performance report ID '{report_id}' to user '{user_email}'.")
            with self.lock:
                report = self.session.query(PerformanceReport).filter(PerformanceReport.id == report_id).first()
                if not report:
                    self.logger.error(f"Performance report with ID '{report_id}' does not exist.")
                    return False

                headers = {
                    'Authorization': f"Bearer {self.analytics_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'report_id': report.id,
                    'report_name': report.report_name,
                    'generated_at': report.generated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'report_data': json.loads(report.report_data),
                    'chart_image': report.chart_image,
                    'recipient_email': user_email
                }
                response = self.session_requests.post(
                    self.analytics_api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to send performance report via email. Status Code: {response.status_code}, Response: {response.text}")
                    return False

                self.logger.info(f"Performance report ID '{report_id}' sent successfully to '{user_email}'.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending performance report ID '{report_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending performance report ID '{report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while sending performance report ID '{report_id}': {e}", exc_info=True)
            return False

    def retrieve_performance_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the details of a specific performance report.

        Args:
            report_id (str): The unique identifier of the performance report.

        Returns:
            Optional[Dict[str, Any]]: The report details if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving performance report ID '{report_id}'.")
            with self.lock:
                report = self.session.query(PerformanceReport).filter(PerformanceReport.id == report_id).first()
                if not report:
                    self.logger.error(f"Performance report with ID '{report_id}' does not exist.")
                    return None

                report_details = {
                    'report_id': report.id,
                    'report_name': report.report_name,
                    'generated_at': report.generated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'report_data': json.loads(report.report_data),
                    'chart_image': report.chart_image,
                    'created_at': report.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': report.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                self.logger.info(f"Performance report ID '{report_id}' retrieved successfully.")
                return report_details
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving performance report ID '{report_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving performance report ID '{report_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing PerformanceAnalyticsService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("PerformanceAnalyticsService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing PerformanceAnalyticsService: {e}", exc_info=True)
            raise PerformanceAnalyticsServiceError(f"Error closing PerformanceAnalyticsService: {e}")
