# services/bug_reporting_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class BugReport(Base):
    __tablename__ = 'bug_reports'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, nullable=False)  # e.g., Low, Medium, High, Critical
    status = Column(String, default='Open')  # Open, In Progress, Resolved, Closed
    reported_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="bug_reports")

class BugReportingServiceError(Exception):
    """Custom exception for BugReportingService-related errors."""
    pass

class BugReportingService:
    """
    Provides bug reporting functionalities, including collecting bug reports from users,
    logging them into the database, notifying developers via email or external systems,
    tracking the status of bug reports, and integrating with third-party bug tracking tools.
    Utilizes SQLAlchemy for database interactions and ensures secure handling of user data
    and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the BugReportingService with necessary configurations and authentication.
        """
        self.logger = setup_logging('BugReportingService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.developer_email = self.config_loader.get('DEVELOPER_EMAIL')
        self.smtp_server = self.config_loader.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = self.config_loader.get('SMTP_PORT', 587)
        self.smtp_username_encrypted = self.config_loader.get('SMTP_USERNAME')
        self.smtp_password_encrypted = self.config_loader.get('SMTP_PASSWORD')
        self.smtp_username = self.encryption_manager.decrypt_data(self.smtp_username_encrypted).decode('utf-8')
        self.smtp_password = self.encryption_manager.decrypt_data(self.smtp_password_encrypted).decode('utf-8')
        self.bug_tracking_api_url = self.config_loader.get('BUG_TRACKING_API_URL', 'https://api.bugtrackingsystem.com/report')
        self.bug_tracking_api_key_encrypted = self.config_loader.get('BUG_TRACKING_API_KEY')
        self.bug_tracking_api_key = self.encryption_manager.decrypt_data(self.bug_tracking_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("BugReportingService initialized successfully.")

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
                raise BugReportingServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise BugReportingServiceError(f"Error initializing database: {e}")

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
            raise BugReportingServiceError(f"Unsupported database type '{db_type}'.")

    def submit_bug_report(self, user_id: str, title: str, description: str, severity: str) -> Optional[str]:
        """
        Submits a bug report from a user.

        Args:
            user_id (str): The unique identifier of the user.
            title (str): The title of the bug report.
            description (str): The detailed description of the bug.
            severity (str): The severity level of the bug ('Low', 'Medium', 'High', 'Critical').

        Returns:
            Optional[str]: The bug report ID if submission is successful, else None.
        """
        try:
            self.logger.debug(f"Submitting bug report from user ID '{user_id}' with title '{title}' and severity '{severity}'.")
            if severity not in ['Low', 'Medium', 'High', 'Critical']:
                self.logger.error("Invalid severity level provided.")
                return None

            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                bug_report = BugReport(
                    user_id=user_id,
                    title=title,
                    description=description,
                    severity=severity,
                    status='Open',
                    reported_at=datetime.utcnow()
                )
                self.session.add(bug_report)
                self.session.commit()
                bug_report_id = bug_report.id
                self.logger.info(f"Bug report submitted successfully with ID '{bug_report_id}' by user ID '{user_id}'.")

                # Notify developers about the new bug report
                self._notify_developers(bug_report)

                # Optionally, integrate with external bug tracking system
                self._integrate_with_bug_tracking_system(bug_report)

                return bug_report_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while submitting bug report: {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while submitting bug report: {e}", exc_info=True)
            self.session.rollback()
            return None

    def _notify_developers(self, bug_report: 'BugReport'):
        """
        Sends an email notification to developers about the new bug report.

        Args:
            bug_report (BugReport): The BugReport instance.
        """
        try:
            self.logger.debug(f"Notifying developers about bug report ID '{bug_report.id}'.")
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.developer_email
            msg['Subject'] = f"New Bug Report Submitted: {bug_report.title}"

            body = f"""
            A new bug report has been submitted.

            Bug Report ID: {bug_report.id}
            User ID: {bug_report.user_id}
            Title: {bug_report.title}
            Description: {bug_report.description}
            Severity: {bug_report.severity}
            Reported At: {bug_report.reported_at.strftime('%Y-%m-%d %H:%M:%S')}

            Please review and address this issue accordingly.
            """
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.smtp_username, self.developer_email, msg.as_string())
            server.quit()

            self.logger.info(f"Developers notified successfully about bug report ID '{bug_report.id}'.")
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error while notifying developers: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying developers: {e}", exc_info=True)

    def _integrate_with_bug_tracking_system(self, bug_report: 'BugReport'):
        """
        Integrates the bug report with an external bug tracking system via API.

        Args:
            bug_report (BugReport): The BugReport instance.
        """
        try:
            self.logger.debug(f"Integrating bug report ID '{bug_report.id}' with external bug tracking system.")
            headers = {
                'Authorization': f"Bearer {self.bug_tracking_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'bug_id': bug_report.id,
                'title': bug_report.title,
                'description': bug_report.description,
                'severity': bug_report.severity,
                'reported_by': bug_report.user_id,
                'reported_at': bug_report.reported_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            response = self.session_requests.post(
                self.bug_tracking_api_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 201:
                self.logger.error(f"Failed to integrate with bug tracking system. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Bug report ID '{bug_report.id}' integrated successfully with bug tracking system.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while integrating with bug tracking system: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while integrating with bug tracking system: {e}", exc_info=True)

    def update_bug_report_status(self, bug_report_id: str, new_status: str, comments: Optional[str] = None) -> bool:
        """
        Updates the status of an existing bug report.

        Args:
            bug_report_id (str): The unique identifier of the bug report.
            new_status (str): The new status ('Open', 'In Progress', 'Resolved', 'Closed').
            comments (Optional[str], optional): Additional comments or resolution details. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating status of bug report ID '{bug_report_id}' to '{new_status}'.")
            if new_status not in ['Open', 'In Progress', 'Resolved', 'Closed']:
                self.logger.error("Invalid status provided.")
                return False

            with self.lock:
                bug_report = self.session.query(BugReport).filter(BugReport.id == bug_report_id).first()
                if not bug_report:
                    self.logger.error(f"Bug report with ID '{bug_report_id}' does not exist.")
                    return False

                bug_report.status = new_status
                if new_status == 'Resolved' or new_status == 'Closed':
                    bug_report.resolved_at = datetime.utcnow()
                if comments:
                    bug_report.comments = comments

                self.session.commit()
                self.logger.info(f"Bug report ID '{bug_report_id}' updated successfully to status '{new_status}'.")

                # Notify user about the status update
                self._notify_user_status_update(bug_report)

                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating bug report ID '{bug_report_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating bug report ID '{bug_report_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_user_status_update(self, bug_report: 'BugReport'):
        """
        Sends an email notification to the user about the status update of their bug report.

        Args:
            bug_report (BugReport): The BugReport instance.
        """
        try:
            self.logger.debug(f"Notifying user ID '{bug_report.user_id}' about status update of bug report ID '{bug_report.id}'.")
            user = self.session.query(User).filter(User.id == bug_report.user_id).first()
            if not user:
                self.logger.error(f"User with ID '{bug_report.user_id}' does not exist.")
                return

            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = user.email
            msg['Subject'] = f"Your Bug Report '{bug_report.title}' has been {bug_report.status}"

            body = f"""
            Dear {user.name},

            We would like to inform you that your bug report titled "{bug_report.title}" has been updated to the status: {bug_report.status}.

            {f"Comments: {bug_report.comments}" if bug_report.comments else ""}

            Thank you for helping us improve our services.

            Best regards,
            Support Team
            """
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.smtp_username, user.email, msg.as_string())
            server.quit()

            self.logger.info(f"User ID '{bug_report.user_id}' notified successfully about status update of bug report ID '{bug_report.id}'.")
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error while notifying user about bug report status update: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying user about bug report status update: {e}", exc_info=True)

    def get_bug_report_details(self, bug_report_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the details of a specific bug report.

        Args:
            bug_report_id (str): The unique identifier of the bug report.

        Returns:
            Optional[Dict[str, Any]]: The bug report details if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving details for bug report ID '{bug_report_id}'.")
            with self.lock:
                bug_report = self.session.query(BugReport).filter(BugReport.id == bug_report_id).first()
                if not bug_report:
                    self.logger.error(f"Bug report with ID '{bug_report_id}' does not exist.")
                    return None

                bug_report_details = {
                    'bug_report_id': bug_report.id,
                    'user_id': bug_report.user_id,
                    'title': bug_report.title,
                    'description': bug_report.description,
                    'severity': bug_report.severity,
                    'status': bug_report.status,
                    'reported_at': bug_report.reported_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'resolved_at': bug_report.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if bug_report.resolved_at else None,
                    'comments': bug_report.comments,
                    'created_at': bug_report.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': bug_report.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                self.logger.info(f"Details for bug report ID '{bug_report_id}' retrieved successfully.")
                return bug_report_details
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving bug report ID '{bug_report_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving bug report ID '{bug_report_id}': {e}", exc_info=True)
            return None

    def list_bug_reports(self, status_filter: Optional[List[str]] = None,
                        severity_filter: Optional[List[str]] = None,
                        start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Lists bug reports based on optional filters.

        Args:
            status_filter (Optional[List[str]], optional): List of statuses to filter bug reports. Defaults to None.
            severity_filter (Optional[List[str]], optional): List of severities to filter bug reports. Defaults to None.
            start_date (Optional[datetime], optional): The start date for filtering. Defaults to None.
            end_date (Optional[datetime], optional): The end date for filtering. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of bug reports matching the filters if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Listing bug reports with status_filter={status_filter}, severity_filter={severity_filter}, start_date={start_date}, end_date={end_date}.")
            with self.lock:
                query = self.session.query(BugReport)
                if status_filter:
                    query = query.filter(BugReport.status.in_(status_filter))
                if severity_filter:
                    query = query.filter(BugReport.severity.in_(severity_filter))
                if start_date:
                    query = query.filter(BugReport.reported_at >= start_date)
                if end_date:
                    query = query.filter(BugReport.reported_at <= end_date)

                bug_reports = query.order_by(BugReport.reported_at.desc()).all()
                bug_reports_list = [
                    {
                        'bug_report_id': bug_report.id,
                        'user_id': bug_report.user_id,
                        'title': bug_report.title,
                        'severity': bug_report.severity,
                        'status': bug_report.status,
                        'reported_at': bug_report.reported_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'resolved_at': bug_report.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if bug_report.resolved_at else None,
                        'comments': bug_report.comments
                    } for bug_report in bug_reports
                ]
                self.logger.info(f"Retrieved {len(bug_reports_list)} bug reports based on the provided filters.")
                return bug_reports_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while listing bug reports: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while listing bug reports: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing BugReportingService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("BugReportingService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing BugReportingService: {e}", exc_info=True)
            raise BugReportingServiceError(f"Error closing BugReportingService: {e}")
