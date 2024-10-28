# services/compliance_service.py

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

class CompliancePolicy(Base):
    __tablename__ = 'compliance_policies'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=False)
    regulation_type = Column(String, nullable=False)  # e.g., GDPR, HIPAA
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    audits = relationship("ComplianceAudit", back_populates="policy")

class ComplianceAudit(Base):
    __tablename__ = 'compliance_audits'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(String, ForeignKey('compliance_policies.id'), nullable=False)
    auditor_id = Column(String, ForeignKey('users.id'), nullable=False)  # Assuming auditors are users with a specific role
    audit_date = Column(DateTime, nullable=False)
    findings = Column(Text, nullable=True)
    status = Column(String, default='pending')  # pending, passed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    policy = relationship("CompliancePolicy", back_populates="audits")
    auditor = relationship("User", backref="compliance_audits")

class UserConsent(Base):
    __tablename__ = 'user_consents'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    policy_id = Column(String, ForeignKey('compliance_policies.id'), nullable=False)
    consent_given = Column(Boolean, default=False)
    consent_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="consents")
    policy = relationship("CompliancePolicy", backref="user_consents")

class ComplianceServiceError(Exception):
    """Custom exception for ComplianceService-related errors."""
    pass

class ComplianceService:
    """
    Provides compliance management functionalities, including managing compliance policies,
    conducting audits, tracking user consents, and ensuring adherence to legal regulations.
    Utilizes SQLAlchemy for database interactions and integrates with third-party APIs for
    regulatory updates and notifications. Ensures secure handling of user data and compliance
    with privacy regulations.
    """

    def __init__(self):
        """
        Initializes the ComplianceService with necessary configurations and authentication.
        """
        self.logger = setup_logging('ComplianceService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.regulatory_update_api_url = self.config_loader.get('REGULATORY_UPDATE_API_URL', 'https://api.regupdates.com')
        self.regulatory_update_api_key_encrypted = self.config_loader.get('REGULATORY_UPDATE_API_KEY')
        self.regulatory_update_api_key = self.encryption_manager.decrypt_data(self.regulatory_update_api_key_encrypted).decode('utf-8')
        self.notification_api_url = self.config_loader.get('NOTIFICATION_API_URL', 'https://api.notification.com')
        self.notification_api_key_encrypted = self.config_loader.get('NOTIFICATION_API_KEY')
        self.notification_api_key = self.encryption_manager.decrypt_data(self.notification_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("ComplianceService initialized successfully.")

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
                raise ComplianceServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise ComplianceServiceError(f"Error initializing database: {e}")

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
            raise ComplianceServiceError(f"Unsupported database type '{db_type}'.")

    def add_compliance_policy(self, name: str, description: str, regulation_type: str) -> Optional[str]:
        """
        Adds a new compliance policy.

        Args:
            name (str): The name of the compliance policy.
            description (str): A detailed description of the policy.
            regulation_type (str): The type of regulation (e.g., GDPR, HIPAA).

        Returns:
            Optional[str]: The policy ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding compliance policy '{name}' of type '{regulation_type}'.")
            with self.lock:
                existing_policy = self.session.query(CompliancePolicy).filter(CompliancePolicy.name.ilike(name)).first()
                if existing_policy:
                    self.logger.error(f"Compliance policy '{name}' already exists.")
                    return None

                policy = CompliancePolicy(
                    name=name,
                    description=description,
                    regulation_type=regulation_type
                )
                self.session.add(policy)
                self.session.commit()
                policy_id = policy.id
                self.logger.info(f"Compliance policy '{name}' added successfully with ID '{policy_id}'.")
                return policy_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding compliance policy '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while adding compliance policy '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_compliance_policy(self, policy_id: str, name: Optional[str] = None, description: Optional[str] = None,
                                 regulation_type: Optional[str] = None) -> bool:
        """
        Updates an existing compliance policy.

        Args:
            policy_id (str): The unique identifier of the compliance policy.
            name (Optional[str], optional): The new name of the policy. Defaults to None.
            description (Optional[str], optional): The new description of the policy. Defaults to None.
            regulation_type (Optional[str], optional): The new regulation type. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating compliance policy ID '{policy_id}'.")
            with self.lock:
                policy = self.session.query(CompliancePolicy).filter(CompliancePolicy.id == policy_id).first()
                if not policy:
                    self.logger.error(f"Compliance policy with ID '{policy_id}' does not exist.")
                    return False

                if name:
                    policy.name = name
                if description:
                    policy.description = description
                if regulation_type:
                    policy.regulation_type = regulation_type

                self.session.commit()
                self.logger.info(f"Compliance policy ID '{policy_id}' updated successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating compliance policy ID '{policy_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating compliance policy ID '{policy_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def conduct_audit(self, policy_id: str, auditor_id: str, audit_date: datetime) -> Optional[str]:
        """
        Conducts a compliance audit for a specific policy.

        Args:
            policy_id (str): The unique identifier of the compliance policy.
            auditor_id (str): The unique identifier of the auditor.
            audit_date (datetime): The date of the audit.

        Returns:
            Optional[str]: The audit ID if conduction is successful, else None.
        """
        try:
            self.logger.debug(f"Conducting audit for policy ID '{policy_id}' by auditor ID '{auditor_id}' on '{audit_date}'.")
            with self.lock:
                policy = self.session.query(CompliancePolicy).filter(CompliancePolicy.id == policy_id).first()
                if not policy:
                    self.logger.error(f"Compliance policy with ID '{policy_id}' does not exist.")
                    return None

                auditor = self.session.query(User).filter(User.id == auditor_id, User.role == 'auditor').first()
                if not auditor:
                    self.logger.error(f"Auditor with ID '{auditor_id}' does not exist or is not authorized.")
                    return None

                # Check for existing audit on the same date
                existing_audit = self.session.query(ComplianceAudit).filter(
                    ComplianceAudit.policy_id == policy_id,
                    ComplianceAudit.auditor_id == auditor_id,
                    ComplianceAudit.audit_date == audit_date
                ).first()
                if existing_audit:
                    self.logger.error(f"Audit for policy ID '{policy_id}' by auditor ID '{auditor_id}' on '{audit_date}' already exists.")
                    return None

                audit = ComplianceAudit(
                    policy_id=policy_id,
                    auditor_id=auditor_id,
                    audit_date=audit_date,
                    status='pending',
                    findings=None
                )
                self.session.add(audit)
                self.session.commit()
                audit_id = audit.id
                self.logger.info(f"Compliance audit conducted successfully with ID '{audit_id}' for policy ID '{policy_id}'.")
                return audit_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while conducting audit for policy ID '{policy_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while conducting audit for policy ID '{policy_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_audit_status(self, audit_id: str, status: str, findings: Optional[str] = None) -> bool:
        """
        Updates the status and findings of a compliance audit.

        Args:
            audit_id (str): The unique identifier of the audit.
            status (str): The new status of the audit ('pending', 'passed', 'failed').
            findings (Optional[str], optional): The findings from the audit. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating audit ID '{audit_id}' to status '{status}' with findings: '{findings}'.")
            if status not in ['pending', 'passed', 'failed']:
                self.logger.error("Invalid audit status. Must be 'pending', 'passed', or 'failed'.")
                return False

            with self.lock:
                audit = self.session.query(ComplianceAudit).filter(ComplianceAudit.id == audit_id).first()
                if not audit:
                    self.logger.error(f"Audit with ID '{audit_id}' does not exist.")
                    return False

                audit.status = status
                if findings:
                    audit.findings = findings

                self.session.commit()
                self.logger.info(f"Audit ID '{audit_id}' updated successfully to status '{status}'.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating audit ID '{audit_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating audit ID '{audit_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def track_user_consent(self, user_id: str, policy_id: str, consent_given: bool) -> Optional[str]:
        """
        Tracks a user's consent for a specific compliance policy.

        Args:
            user_id (str): The unique identifier of the user.
            policy_id (str): The unique identifier of the compliance policy.
            consent_given (bool): Whether the user has given consent.

        Returns:
            Optional[str]: The consent ID if tracking is successful, else None.
        """
        try:
            self.logger.debug(f"Tracking consent for user ID '{user_id}' on policy ID '{policy_id}' with consent_given='{consent_given}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                policy = self.session.query(CompliancePolicy).filter(CompliancePolicy.id == policy_id).first()
                if not policy:
                    self.logger.error(f"Compliance policy with ID '{policy_id}' does not exist.")
                    return None

                existing_consent = self.session.query(UserConsent).filter(
                    UserConsent.user_id == user_id,
                    UserConsent.policy_id == policy_id
                ).first()

                if existing_consent:
                    existing_consent.consent_given = consent_given
                    existing_consent.consent_date = datetime.utcnow() if consent_given else None
                    self.session.commit()
                    consent_id = existing_consent.id
                    self.logger.info(f"Consent updated successfully with ID '{consent_id}' for user ID '{user_id}' on policy ID '{policy_id}'.")
                    return consent_id

                consent = UserConsent(
                    user_id=user_id,
                    policy_id=policy_id,
                    consent_given=consent_given,
                    consent_date=datetime.utcnow() if consent_given else None
                )
                self.session.add(consent)
                self.session.commit()
                consent_id = consent.id
                self.logger.info(f"Consent tracked successfully with ID '{consent_id}' for user ID '{user_id}' on policy ID '{policy_id}'.")
                return consent_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while tracking consent for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while tracking consent for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def get_compliance_updates(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the latest compliance updates from an external regulatory update API.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of compliance updates if retrieval is successful, else None.
        """
        try:
            self.logger.debug("Fetching latest compliance updates from external API.")
            headers = {
                'Authorization': f"Bearer {self.regulatory_update_api_key}",
                'Content-Type': 'application/json'
            }
            response = self.session_requests.get(
                f"{self.regulatory_update_api_url}/latest",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                updates = response.json().get('updates', [])
                self.logger.debug(f"Compliance updates retrieved: {updates}.")
                return updates
            else:
                self.logger.error(f"Failed to retrieve compliance updates. Status Code: {response.status_code}, Response: {response.text}")
                return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception while fetching compliance updates: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching compliance updates: {e}", exc_info=True)
            return None

    def notify_users_of_updates(self, updates: List[Dict[str, Any]]):
        """
        Notifies users about new compliance updates via external notification API.

        Args:
            updates (List[Dict[str, Any]]): A list of compliance updates.
        """
        try:
            self.logger.debug(f"Notifying users about {len(updates)} compliance updates.")
            headers = {
                'Authorization': f"Bearer {self.notification_api_key}",
                'Content-Type': 'application/json'
            }
            for update in updates:
                policy_name = update.get('policy_name')
                description = update.get('description')
                affected_users = self.session.query(User).filter(User.consents.any(UserConsent.policy_id == update.get('policy_id'), UserConsent.consent_given == True)).all()
                for user in affected_users:
                    payload = {
                        'to': user.email,
                        'message': f"New compliance update: {policy_name}. Details: {description}"
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
            self.logger.error(f"Request exception while notifying users: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while notifying users: {e}", exc_info=True)

    def perform_regular_audits(self, policy_id: str, auditor_id: str, frequency: str = 'monthly') -> bool:
        """
        Schedules and performs regular audits based on the specified frequency.

        Args:
            policy_id (str): The unique identifier of the compliance policy.
            auditor_id (str): The unique identifier of the auditor.
            frequency (str, optional): The frequency of audits ('monthly', 'quarterly', 'yearly'). Defaults to 'monthly'.

        Returns:
            bool: True if audits are scheduled successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Scheduling regular '{frequency}' audits for policy ID '{policy_id}' by auditor ID '{auditor_id}'.")
            if frequency not in ['monthly', 'quarterly', 'yearly']:
                self.logger.error("Invalid frequency. Must be 'monthly', 'quarterly', or 'yearly'.")
                return False

            interval_days = {'monthly': 30, 'quarterly': 90, 'yearly': 365}.get(frequency)
            next_audit_date = datetime.utcnow() + timedelta(days=interval_days)

            audit_id = self.conduct_audit(policy_id, auditor_id, next_audit_date)
            if audit_id:
                self.logger.info(f"Regular '{frequency}' audit scheduled successfully with ID '{audit_id}'. Next audit on '{next_audit_date}'.")
                return True
            else:
                self.logger.error(f"Failed to schedule regular '{frequency}' audit for policy ID '{policy_id}'.")
                return False
        except Exception as e:
            self.logger.error(f"Unexpected error while scheduling regular audits: {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing ComplianceService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("ComplianceService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing ComplianceService: {e}", exc_info=True)
            raise ComplianceServiceError(f"Error closing ComplianceService: {e}")
