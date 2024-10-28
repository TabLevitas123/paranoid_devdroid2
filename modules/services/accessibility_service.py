# services/accessibility_service.py

import json
import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
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

class AccessibilityFeature(Base):
    __tablename__ = 'accessibility_features'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)  # e.g., Screen Reader, High Contrast Mode
    description = Column(Text, nullable=False)
    enabled_by_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_settings = relationship("UserAccessibilitySetting", back_populates="feature")

class UserAccessibilitySetting(Base):
    __tablename__ = 'user_accessibility_settings'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    feature_id = Column(String, ForeignKey('accessibility_features.id'), nullable=False)
    enabled = Column(Boolean, default=False)
    preferences = Column(Text, nullable=True)  # JSON string for feature-specific preferences
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    feature = relationship("AccessibilityFeature", back_populates="user_settings")
    user = relationship("User", backref="accessibility_settings")

class AccessibilityAudit(Base):
    __tablename__ = 'accessibility_audits'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    auditor_id = Column(String, ForeignKey('users.id'), nullable=False)  # Assuming auditors are users with a specific role
    audit_date = Column(DateTime, nullable=False)
    findings = Column(Text, nullable=True)
    status = Column(String, default='pending')  # pending, passed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    auditor = relationship("User", backref="accessibility_audits")

class AccessibilityServiceError(Exception):
    """Custom exception for AccessibilityService-related errors."""
    pass

class AccessibilityService:
    """
    Provides accessibility management functionalities, including managing accessibility features,
    customizing user accessibility settings, conducting accessibility audits, and ensuring compliance
    with accessibility standards (e.g., WCAG). Utilizes SQLAlchemy for database interactions and
    integrates with third-party APIs for accessibility testing and user notifications.
    Ensures secure handling of user data and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the AccessibilityService with necessary configurations and authentication.
        """
        self.logger = setup_logging('AccessibilityService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.accessibility_testing_api_url = self.config_loader.get('ACCESSIBILITY_TESTING_API_URL', 'https://api.accessibilitytest.com')
        self.accessibility_testing_api_key_encrypted = self.config_loader.get('ACCESSIBILITY_TESTING_API_KEY')
        self.accessibility_testing_api_key = self.encryption_manager.decrypt_data(self.accessibility_testing_api_key_encrypted).decode('utf-8')
        self.notification_api_url = self.config_loader.get('NOTIFICATION_API_URL', 'https://api.notification.com')
        self.notification_api_key_encrypted = self.config_loader.get('NOTIFICATION_API_KEY')
        self.notification_api_key = self.encryption_manager.decrypt_data(self.notification_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("AccessibilityService initialized successfully.")

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
                raise AccessibilityServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise AccessibilityServiceError(f"Error initializing database: {e}")

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
            raise AccessibilityServiceError(f"Unsupported database type '{db_type}'.")

    def add_accessibility_feature(self, name: str, description: str, enabled_by_default: bool = False) -> Optional[str]:
        """
        Adds a new accessibility feature.

        Args:
            name (str): The name of the accessibility feature.
            description (str): A detailed description of the feature.
            enabled_by_default (bool, optional): Whether the feature is enabled by default. Defaults to False.

        Returns:
            Optional[str]: The feature ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding accessibility feature '{name}'.")
            with self.lock:
                existing_feature = self.session.query(AccessibilityFeature).filter(AccessibilityFeature.name.ilike(name)).first()
                if existing_feature:
                    self.logger.error(f"Accessibility feature '{name}' already exists.")
                    return None

                feature = AccessibilityFeature(
                    name=name,
                    description=description,
                    enabled_by_default=enabled_by_default
                )
                self.session.add(feature)
                self.session.commit()
                feature_id = feature.id
                self.logger.info(f"Accessibility feature '{name}' added successfully with ID '{feature_id}'.")
                return feature_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding accessibility feature '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while adding accessibility feature '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_accessibility_feature(self, feature_id: str, name: Optional[str] = None, description: Optional[str] = None,
                                     enabled_by_default: Optional[bool] = None) -> bool:
        """
        Updates an existing accessibility feature.

        Args:
            feature_id (str): The unique identifier of the accessibility feature.
            name (Optional[str], optional): The new name of the feature. Defaults to None.
            description (Optional[str], optional): The new description of the feature. Defaults to None.
            enabled_by_default (Optional[bool], optional): The new default enabled status. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating accessibility feature ID '{feature_id}'.")
            with self.lock:
                feature = self.session.query(AccessibilityFeature).filter(AccessibilityFeature.id == feature_id).first()
                if not feature:
                    self.logger.error(f"Accessibility feature with ID '{feature_id}' does not exist.")
                    return False

                if name:
                    feature.name = name
                if description:
                    feature.description = description
                if enabled_by_default is not None:
                    feature.enabled_by_default = enabled_by_default

                self.session.commit()
                self.logger.info(f"Accessibility feature ID '{feature_id}' updated successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating accessibility feature ID '{feature_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating accessibility feature ID '{feature_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def customize_user_setting(self, user_id: str, feature_id: str, enabled: bool, preferences: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Customizes a user's accessibility settings for a specific feature.

        Args:
            user_id (str): The unique identifier of the user.
            feature_id (str): The unique identifier of the accessibility feature.
            enabled (bool): Whether the feature is enabled for the user.
            preferences (Optional[Dict[str, Any]], optional): Feature-specific preferences. Defaults to None.

        Returns:
            Optional[str]: The setting ID if customization is successful, else None.
        """
        try:
            self.logger.debug(f"Customizing accessibility setting for user ID '{user_id}' on feature ID '{feature_id}'. Enabled: {enabled}.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                feature = self.session.query(AccessibilityFeature).filter(AccessibilityFeature.id == feature_id).first()
                if not feature:
                    self.logger.error(f"Accessibility feature with ID '{feature_id}' does not exist.")
                    return None

                existing_setting = self.session.query(UserAccessibilitySetting).filter(
                    UserAccessibilitySetting.user_id == user_id,
                    UserAccessibilitySetting.feature_id == feature_id
                ).first()

                if existing_setting:
                    existing_setting.enabled = enabled
                    existing_setting.preferences = json.dumps(preferences) if preferences else None
                    existing_setting.updated_at = datetime.utcnow()
                    self.session.commit()
                    setting_id = existing_setting.id
                    self.logger.info(f"Accessibility setting updated successfully with ID '{setting_id}' for user ID '{user_id}'.")
                    return setting_id

                setting = UserAccessibilitySetting(
                    user_id=user_id,
                    feature_id=feature_id,
                    enabled=enabled,
                    preferences=json.dumps(preferences) if preferences else None
                )
                self.session.add(setting)
                self.session.commit()
                setting_id = setting.id
                self.logger.info(f"Accessibility setting customized successfully with ID '{setting_id}' for user ID '{user_id}'.")
                return setting_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while customizing accessibility setting for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while customizing accessibility setting for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def conduct_accessibility_audit(self, auditor_id: str, audit_date: datetime) -> Optional[str]:
        """
        Conducts an accessibility audit to ensure compliance with accessibility standards.

        Args:
            auditor_id (str): The unique identifier of the auditor.
            audit_date (datetime): The date of the audit.

        Returns:
            Optional[str]: The audit ID if conduction is successful, else None.
        """
        try:
            self.logger.debug(f"Conducting accessibility audit by auditor ID '{auditor_id}' on '{audit_date}'.")
            with self.lock:
                auditor = self.session.query(User).filter(User.id == auditor_id, User.role == 'auditor').first()
                if not auditor:
                    self.logger.error(f"Auditor with ID '{auditor_id}' does not exist or is not authorized.")
                    return None

                existing_audit = self.session.query(AccessibilityAudit).filter(
                    AccessibilityAudit.auditor_id == auditor_id,
                    AccessibilityAudit.audit_date == audit_date
                ).first()
                if existing_audit:
                    self.logger.error(f"Accessibility audit by auditor ID '{auditor_id}' on '{audit_date}' already exists.")
                    return None

                audit = AccessibilityAudit(
                    auditor_id=auditor_id,
                    audit_date=audit_date,
                    status='pending',
                    findings=None
                )
                self.session.add(audit)
                self.session.commit()
                audit_id = audit.id

                # Optionally, trigger automated accessibility testing via external API
                findings = self._perform_accessibility_tests()
                if findings:
                    audit.findings = findings.get('summary', '')
                    audit.status = 'passed' if findings.get('passed') else 'failed'
                    self.session.commit()

                self.logger.info(f"Accessibility audit conducted successfully with ID '{audit_id}'.")
                return audit_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while conducting accessibility audit: {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while conducting accessibility audit: {e}", exc_info=True)
            self.session.rollback()
            return None

    def _perform_accessibility_tests(self) -> Optional[Dict[str, Any]]:
        """
        Performs automated accessibility tests using an external accessibility testing API.

        Returns:
            Optional[Dict[str, Any]]: The test results if successful, else None.
        """
        try:
            self.logger.debug("Performing automated accessibility tests using external API.")
            headers = {
                'Authorization': f"Bearer {self.accessibility_testing_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'application_url': self.config_loader.get('APPLICATION_URL', 'https://www.example.com')
            }
            response = self.session_requests.post(
                f"{self.accessibility_testing_api_url}/test",
                headers=headers,
                json=payload,
                timeout=20
            )
            if response.status_code == 200:
                test_results = response.json()
                self.logger.debug(f"Accessibility test results: {test_results}.")
                return test_results
            else:
                self.logger.error(f"Failed to perform accessibility tests. Status Code: {response.status_code}, Response: {response.text}")
                return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception while performing accessibility tests: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while performing accessibility tests: {e}", exc_info=True)
            return None

    def generate_audit_report(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """
        Generates a detailed report for a specific accessibility audit.

        Args:
            audit_id (str): The unique identifier of the audit.

        Returns:
            Optional[Dict[str, Any]]: The audit report if generation is successful, else None.
        """
        try:
            self.logger.debug(f"Generating report for accessibility audit ID '{audit_id}'.")
            with self.lock:
                audit = self.session.query(AccessibilityAudit).filter(AccessibilityAudit.id == audit_id).first()
                if not audit:
                    self.logger.error(f"Accessibility audit with ID '{audit_id}' does not exist.")
                    return None

                report = {
                    'audit_id': audit.id,
                    'auditor_id': audit.auditor_id,
                    'audit_date': audit.audit_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'status': audit.status,
                    'findings': audit.findings,
                    'created_at': audit.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': audit.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                self.logger.info(f"Accessibility audit report generated for audit ID '{audit_id}': {report}.")
                return report
        except Exception as e:
            self.logger.error(f"Error generating audit report for audit ID '{audit_id}': {e}", exc_info=True)
            return None

    def notify_users_of_accessibility_features(self, user_id: str, feature_id: str):
        """
        Notifies a user about new or updated accessibility features.

        Args:
            user_id (str): The unique identifier of the user.
            feature_id (str): The unique identifier of the accessibility feature.
        """
        try:
            self.logger.debug(f"Notifying user ID '{user_id}' about accessibility feature ID '{feature_id}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return

                feature = self.session.query(AccessibilityFeature).filter(AccessibilityFeature.id == feature_id).first()
                if not feature:
                    self.logger.error(f"Accessibility feature with ID '{feature_id}' does not exist.")
                    return

                headers = {
                    'Authorization': f"Bearer {self.notification_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'to': user.email,
                    'message': f"New accessibility feature available: {feature.name}. Details: {feature.description}"
                }
                response = self.session_requests.post(
                    f"{self.notification_api_url}/send",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to send notification to '{user.email}'. Status Code: {response.status_code}, Response: {response.text}")
                else:
                    self.logger.debug(f"Notification sent to '{user.email}' successfully.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while notifying user '{user_id}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying user '{user_id}': {e}", exc_info=True)

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing AccessibilityService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("AccessibilityService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing AccessibilityService: {e}", exc_info=True)
            raise AccessibilityServiceError(f"Error closing AccessibilityService: {e}")
