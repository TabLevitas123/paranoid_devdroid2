# services/notification_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class NotificationTemplate(Base):
    __tablename__ = 'notification_templates'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)  # e.g., Welcome Email, Password Reset
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)  # Template body with placeholders
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserNotification(Base):
    __tablename__ = 'user_notifications'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    template_id = Column(String, ForeignKey('notification_templates.id'), nullable=False)
    sent_at = Column(DateTime, nullable=False)
    status = Column(String, default='sent')  # sent, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    template = relationship("NotificationTemplate")
    user = relationship("User", backref="notifications")

class NotificationServiceError(Exception):
    """Custom exception for NotificationService-related errors."""
    pass

class NotificationService:
    """
    Provides notification management functionalities, including sending emails, SMS, and push notifications,
    managing notification templates, tracking notification statuses, and integrating with third-party
    notification APIs. Utilizes SQLAlchemy for database interactions and ensures secure handling of user
    data and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the NotificationService with necessary configurations and authentication.
        """
        self.logger = setup_logging('NotificationService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.email_server = self.config_loader.get('EMAIL_SERVER', 'smtp.gmail.com')
        self.email_port = self.config_loader.get('EMAIL_PORT', 587)
        self.email_username_encrypted = self.config_loader.get('EMAIL_USERNAME')
        self.email_password_encrypted = self.config_loader.get('EMAIL_PASSWORD')
        self.email_username = self.encryption_manager.decrypt_data(self.email_username_encrypted).decode('utf-8')
        self.email_password = self.encryption_manager.decrypt_data(self.email_password_encrypted).decode('utf-8')
        self.sms_api_url = self.config_loader.get('SMS_API_URL', 'https://api.smsprovider.com/send')
        self.sms_api_key_encrypted = self.config_loader.get('SMS_API_KEY')
        self.sms_api_key = self.encryption_manager.decrypt_data(self.sms_api_key_encrypted).decode('utf-8')
        self.push_api_url = self.config_loader.get('PUSH_API_URL', 'https://api.pushservice.com/notify')
        self.push_api_key_encrypted = self.config_loader.get('PUSH_API_KEY')
        self.push_api_key = self.encryption_manager.decrypt_data(self.push_api_key_encrypted).decode('utf-8')
        self.frontend_api_url = self.config_loader.get('FRONTEND_API_URL', 'https://api.frontend.com')
        self.frontend_api_key_encrypted = self.config_loader.get('FRONTEND_API_KEY')
        self.frontend_api_key = self.encryption_manager.decrypt_data(self.frontend_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("NotificationService initialized successfully.")

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
                raise NotificationServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise NotificationServiceError(f"Error initializing database: {e}")

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
            raise NotificationServiceError(f"Unsupported database type '{db_type}'.")

    def add_notification_template(self, name: str, subject: str, body: str) -> Optional[str]:
        """
        Adds a new notification template.

        Args:
            name (str): The name of the notification template.
            subject (str): The subject line of the notification.
            body (str): The body of the notification with placeholders for dynamic content.

        Returns:
            Optional[str]: The template ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding notification template '{name}'.")
            with self.lock:
                existing_template = self.session.query(NotificationTemplate).filter(NotificationTemplate.name.ilike(name)).first()
                if existing_template:
                    self.logger.error(f"Notification template '{name}' already exists.")
                    return None

                template = NotificationTemplate(
                    name=name,
                    subject=subject,
                    body=body
                )
                self.session.add(template)
                self.session.commit()
                template_id = template.id
                self.logger.info(f"Notification template '{name}' added successfully with ID '{template_id}'.")
                return template_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding notification template '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while adding notification template '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_notification_template(self, template_id: str, name: Optional[str] = None,
                                     subject: Optional[str] = None, body: Optional[str] = None) -> bool:
        """
        Updates an existing notification template.

        Args:
            template_id (str): The unique identifier of the notification template.
            name (Optional[str], optional): The new name of the template. Defaults to None.
            subject (Optional[str], optional): The new subject line. Defaults to None.
            body (Optional[str], optional): The new body of the notification. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating notification template ID '{template_id}'.")
            with self.lock:
                template = self.session.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
                if not template:
                    self.logger.error(f"Notification template with ID '{template_id}' does not exist.")
                    return False

                if name:
                    template.name = name
                if subject:
                    template.subject = subject
                if body:
                    template.body = body

                self.session.commit()
                self.logger.info(f"Notification template ID '{template_id}' updated successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating notification template ID '{template_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating notification template ID '{template_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def send_email_notification(self, user_id: str, template_id: str, placeholders: Dict[str, Any]) -> Optional[str]:
        """
        Sends an email notification to a user based on a template.

        Args:
            user_id (str): The unique identifier of the user.
            template_id (str): The unique identifier of the notification template.
            placeholders (Dict[str, Any]): A dictionary of placeholder values to personalize the email.

        Returns:
            Optional[str]: The notification ID if sending is successful, else None.
        """
        try:
            self.logger.debug(f"Sending email notification to user ID '{user_id}' using template ID '{template_id}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                template = self.session.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
                if not template:
                    self.logger.error(f"Notification template with ID '{template_id}' does not exist.")
                    return None

                subject = self._populate_placeholders(template.subject, placeholders)
                body = self._populate_placeholders(template.body, placeholders)

                # Send email using SMTP
                msg = MIMEMultipart()
                msg['From'] = self.email_username
                msg['To'] = user.email
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'html'))

                server = smtplib.SMTP(self.email_server, self.email_port)
                server.starttls()
                server.login(self.email_username, self.email_password)
                server.sendmail(self.email_username, user.email, msg.as_string())
                server.quit()

                # Log the sent notification
                notification = UserNotification(
                    user_id=user_id,
                    template_id=template_id,
                    sent_at=datetime.utcnow(),
                    status='sent',
                    error_message=None
                )
                self.session.add(notification)
                self.session.commit()
                notification_id = notification.id
                self.logger.info(f"Email notification sent successfully with ID '{notification_id}' to user ID '{user_id}'.")
                return notification_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending email notification to user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error while sending email to user ID '{user_id}': {e}", exc_info=True)
            # Log the failed notification
            notification = UserNotification(
                user_id=user_id,
                template_id=template_id,
                sent_at=datetime.utcnow(),
                status='failed',
                error_message=str(e)
            )
            self.session.add(notification)
            self.session.commit()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while sending email to user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _populate_placeholders(self, text: str, placeholders: Dict[str, Any]) -> str:
        """
        Replaces placeholders in the text with actual values.

        Args:
            text (str): The text containing placeholders in the format {{placeholder}}.
            placeholders (Dict[str, Any]): A dictionary of placeholder values.

        Returns:
            str: The text with placeholders replaced by actual values.
        """
        for key, value in placeholders.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text

    def send_sms_notification(self, user_id: str, template_id: str, placeholders: Dict[str, Any]) -> Optional[str]:
        """
        Sends an SMS notification to a user based on a template.

        Args:
            user_id (str): The unique identifier of the user.
            template_id (str): The unique identifier of the notification template.
            placeholders (Dict[str, Any]): A dictionary of placeholder values to personalize the SMS.

        Returns:
            Optional[str]: The notification ID if sending is successful, else None.
        """
        try:
            self.logger.debug(f"Sending SMS notification to user ID '{user_id}' using template ID '{template_id}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                template = self.session.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
                if not template:
                    self.logger.error(f"Notification template with ID '{template_id}' does not exist.")
                    return None

                subject = self._populate_placeholders(template.subject, placeholders)
                body = self._populate_placeholders(template.body, placeholders)

                # Send SMS using external SMS API
                payload = {
                    'api_key': self.sms_api_key,
                    'to': user.phone,
                    'message': f"{subject}\n{body}"
                }
                response = self.session_requests.post(
                    self.sms_api_url,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception(f"SMS API responded with status code {response.status_code}: {response.text}")

                # Log the sent notification
                notification = UserNotification(
                    user_id=user_id,
                    template_id=template_id,
                    sent_at=datetime.utcnow(),
                    status='sent',
                    error_message=None
                )
                self.session.add(notification)
                self.session.commit()
                notification_id = notification.id
                self.logger.info(f"SMS notification sent successfully with ID '{notification_id}' to user ID '{user_id}'.")
                return notification_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending SMS notification to user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Error while sending SMS to user ID '{user_id}': {e}", exc_info=True)
            # Log the failed notification
            notification = UserNotification(
                user_id=user_id,
                template_id=template_id,
                sent_at=datetime.utcnow(),
                status='failed',
                error_message=str(e)
            )
            self.session.add(notification)
            self.session.commit()
            return None

    def send_push_notification(self, user_id: str, template_id: str, placeholders: Dict[str, Any]) -> Optional[str]:
        """
        Sends a push notification to a user based on a template.

        Args:
            user_id (str): The unique identifier of the user.
            template_id (str): The unique identifier of the notification template.
            placeholders (Dict[str, Any]): A dictionary of placeholder values to personalize the push notification.

        Returns:
            Optional[str]: The notification ID if sending is successful, else None.
        """
        try:
            self.logger.debug(f"Sending push notification to user ID '{user_id}' using template ID '{template_id}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                template = self.session.query(NotificationTemplate).filter(NotificationTemplate.id == template_id).first()
                if not template:
                    self.logger.error(f"Notification template with ID '{template_id}' does not exist.")
                    return None

                subject = self._populate_placeholders(template.subject, placeholders)
                body = self._populate_placeholders(template.body, placeholders)

                # Send push notification using external Push API
                payload = {
                    'api_key': self.push_api_key,
                    'user_id': user.id,
                    'title': subject,
                    'message': body
                }
                response = self.session_requests.post(
                    self.push_api_url,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception(f"Push API responded with status code {response.status_code}: {response.text}")

                # Log the sent notification
                notification = UserNotification(
                    user_id=user_id,
                    template_id=template_id,
                    sent_at=datetime.utcnow(),
                    status='sent',
                    error_message=None
                )
                self.session.add(notification)
                self.session.commit()
                notification_id = notification.id
                self.logger.info(f"Push notification sent successfully with ID '{notification_id}' to user ID '{user_id}'.")
                return notification_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending push notification to user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Error while sending push notification to user ID '{user_id}': {e}", exc_info=True)
            # Log the failed notification
            notification = UserNotification(
                user_id=user_id,
                template_id=template_id,
                sent_at=datetime.utcnow(),
                status='failed',
                error_message=str(e)
            )
            self.session.add(notification)
            self.session.commit()
            return None

    def create_user_notification(self, user_id: str, template_id: str, sent_at: datetime, status: str = 'sent',
                                 error_message: Optional[str] = None) -> Optional[str]:
        """
        Records a user notification in the database.

        Args:
            user_id (str): The unique identifier of the user.
            template_id (str): The unique identifier of the notification template.
            sent_at (datetime): The timestamp when the notification was sent.
            status (str, optional): The status of the notification ('sent', 'failed'). Defaults to 'sent'.
            error_message (Optional[str], optional): The error message if the notification failed. Defaults to None.

        Returns:
            Optional[str]: The notification ID if recording is successful, else None.
        """
        try:
            self.logger.debug(f"Recording user notification for user ID '{user_id}' with status '{status}'.")
            with self.lock:
                notification = UserNotification(
                    user_id=user_id,
                    template_id=template_id,
                    sent_at=sent_at,
                    status=status,
                    error_message=error_message
                )
                self.session.add(notification)
                self.session.commit()
                notification_id = notification.id
                self.logger.info(f"User notification recorded successfully with ID '{notification_id}' for user ID '{user_id}'.")
                return notification_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while recording notification for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while recording notification for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def get_notification_history(self, user_id: str, status_filter: Optional[List[str]] = None,
                                 start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the notification history for a user based on optional filters.

        Args:
            user_id (str): The unique identifier of the user.
            status_filter (Optional[List[str]], optional): A list of statuses to filter notifications. Defaults to None.
            start_date (Optional[datetime], optional): The start date for filtering notifications. Defaults to None.
            end_date (Optional[datetime], optional): The end date for filtering notifications. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of notifications if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving notification history for user ID '{user_id}' with filters status={status_filter}, start_date={start_date}, end_date={end_date}.")
            with self.lock:
                query = self.session.query(UserNotification).filter(UserNotification.user_id == user_id)
                if status_filter:
                    query = query.filter(UserNotification.status.in_(status_filter))
                if start_date:
                    query = query.filter(UserNotification.sent_at >= start_date)
                if end_date:
                    query = query.filter(UserNotification.sent_at <= end_date)

                notifications = query.order_by(UserNotification.sent_at.desc()).all()
                notifications_list = [
                    {
                        'notification_id': notif.id,
                        'template_name': notif.template.name,
                        'subject': notif.template.subject,
                        'body': notif.template.body,
                        'sent_at': notif.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'status': notif.status,
                        'error_message': notif.error_message
                    } for notif in notifications
                ]
                self.logger.info(f"Retrieved {len(notifications_list)} notifications for user ID '{user_id}'.")
                return notifications_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving notifications for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving notifications for user ID '{user_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing NotificationService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("NotificationService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing NotificationService: {e}", exc_info=True)
            raise NotificationServiceError(f"Error closing NotificationService: {e}")
