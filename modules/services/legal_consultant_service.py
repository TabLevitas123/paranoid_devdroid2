# services/legal_consultant_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
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

class LegalConsultant(Base):
    __tablename__ = 'legal_consultants'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    specialization = Column(String, nullable=False)  # e.g., Corporate Law, Intellectual Property
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    rating = Column(Float, default=5.0)
    available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    consultations = relationship("UserConsultation", back_populates="consultant")

class LegalDocument(Base):
    __tablename__ = 'legal_documents'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    document_type = Column(String, nullable=False)  # e.g., NDA, Contract
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    reviewed = Column(Boolean, default=False)
    review_notes = Column(Text, nullable=True)
    consultant_id = Column(String, ForeignKey('legal_consultants.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    consultant = relationship("LegalConsultant", back_populates="consultations")
    user = relationship("User", backref="legal_documents")

class UserConsultation(Base):
    __tablename__ = 'user_consultations'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    consultant_id = Column(String, ForeignKey('legal_consultants.id'), nullable=False)
    consultation_time = Column(DateTime, nullable=False)
    status = Column(String, default='scheduled')  # scheduled, completed, cancelled
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    consultant = relationship("LegalConsultant", back_populates="consultations")
    user = relationship("User", backref="consultations")

class LegalConsultantServiceError(Exception):
    """Custom exception for LegalConsultantService-related errors."""
    pass

class LegalConsultantService:
    """
    Provides legal consulting capabilities, including managing legal documents, scheduling consultations,
    providing legal advice, and tracking consultation outcomes. Utilizes SQLAlchemy for database
    interactions and integrates with third-party APIs for document analysis and communication.
    Ensures secure handling of user data and compliance with legal privacy regulations.
    """

    def __init__(self):
        """
        Initializes the LegalConsultantService with necessary configurations and authentication.
        """
        self.logger = setup_logging('LegalConsultantService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.document_analysis_api_url = self.config_loader.get('DOCUMENT_ANALYSIS_API_URL', 'https://api.docanalysis.com')
        self.document_analysis_api_key_encrypted = self.config_loader.get('DOCUMENT_ANALYSIS_API_KEY')
        self.document_analysis_api_key = self.encryption_manager.decrypt_data(self.document_analysis_api_key_encrypted).decode('utf-8')
        self.communication_api_url = self.config_loader.get('COMMUNICATION_API_URL', 'https://api.communication.com')
        self.communication_api_key_encrypted = self.config_loader.get('COMMUNICATION_API_KEY')
        self.communication_api_key = self.encryption_manager.decrypt_data(self.communication_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("LegalConsultantService initialized successfully.")

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
                raise LegalConsultantServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise LegalConsultantServiceError(f"Error initializing database: {e}")

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
            raise LegalConsultantServiceError(f"Unsupported database type '{db_type}'.")

    def register_consultant(self, name: str, specialization: str, email: str, phone: str) -> Optional[str]:
        """
        Registers a new legal consultant.

        Args:
            name (str): The consultant's name.
            specialization (str): The consultant's area of specialization.
            email (str): The consultant's email address.
            phone (str): The consultant's phone number.

        Returns:
            Optional[str]: The consultant ID if registration is successful, else None.
        """
        try:
            self.logger.debug(f"Registering legal consultant '{name}' with specialization '{specialization}'.")
            with self.lock:
                existing_consultant = self.session.query(LegalConsultant).filter(
                    (LegalConsultant.email.ilike(email)) | (LegalConsultant.phone == phone)
                ).first()
                if existing_consultant:
                    self.logger.error(f"Consultant with email '{email}' or phone '{phone}' already exists.")
                    return None

                consultant = LegalConsultant(
                    name=name,
                    specialization=specialization,
                    email=email,
                    phone=phone,
                    rating=5.0,
                    available=True
                )
                self.session.add(consultant)
                self.session.commit()
                consultant_id = consultant.id
                self.logger.info(f"Legal consultant '{name}' registered successfully with ID '{consultant_id}'.")
                return consultant_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while registering consultant '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while registering consultant '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def upload_legal_document(self, user_id: str, document_type: str, file_path: str) -> Optional[str]:
        """
        Uploads a legal document for review.

        Args:
            user_id (str): The unique identifier of the user.
            document_type (str): The type of legal document (e.g., NDA, Contract).
            file_path (str): The path to the uploaded document file.

        Returns:
            Optional[str]: The document ID if upload is successful, else None.
        """
        try:
            self.logger.debug(f"Uploading '{document_type}' document for user ID '{user_id}' from '{file_path}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                # Optionally, integrate with a storage service to handle file uploads securely

                document = LegalDocument(
                    user_id=user_id,
                    document_type=document_type,
                    file_path=file_path,
                    reviewed=False
                )
                self.session.add(document)
                self.session.commit()
                document_id = document.id

                # Optionally, trigger document analysis via external API
                analysis_result = self._analyze_document(document_id, file_path)
                if analysis_result:
                    document.review_notes = analysis_result.get('summary', '')
                    document.reviewed = True
                    self.session.commit()

                self.logger.info(f"Legal document uploaded successfully with ID '{document_id}' for user ID '{user_id}'.")
                return document_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while uploading document for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while uploading document for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _analyze_document(self, document_id: str, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes a legal document using an external document analysis API.

        Args:
            document_id (str): The unique identifier of the document.
            file_path (str): The path to the document file.

        Returns:
            Optional[Dict[str, Any]]: The analysis result if successful, else None.
        """
        try:
            self.logger.debug(f"Analyzing document ID '{document_id}' using external API.")
            headers = {
                'Authorization': f"Bearer {self.document_analysis_api_key}"
            }
            files = {
                'file': open(file_path, 'rb')
            }
            response = self.session_requests.post(
                f"{self.document_analysis_api_url}/analyze",
                headers=headers,
                files=files,
                timeout=15
            )
            files['file'].close()
            if response.status_code == 200:
                analysis_data = response.json()
                self.logger.debug(f"Document ID '{document_id}' analysis result: {analysis_data}.")
                return analysis_data
            else:
                self.logger.error(f"Failed to analyze document ID '{document_id}'. Status Code: {response.status_code}, Response: {response.text}")
                return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception while analyzing document ID '{document_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while analyzing document ID '{document_id}': {e}", exc_info=True)
            return None

    def schedule_consultation(self, user_id: str, consultant_id: str, consultation_time: datetime) -> Optional[str]:
        """
        Schedules a consultation between a user and a legal consultant.

        Args:
            user_id (str): The unique identifier of the user.
            consultant_id (str): The unique identifier of the legal consultant.
            consultation_time (datetime): The scheduled time for the consultation.

        Returns:
            Optional[str]: The consultation ID if scheduling is successful, else None.
        """
        try:
            self.logger.debug(f"Scheduling consultation between user ID '{user_id}' and consultant ID '{consultant_id}' at '{consultation_time}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                consultant = self.session.query(LegalConsultant).filter(LegalConsultant.id == consultant_id, LegalConsultant.available == True).first()
                if not consultant:
                    self.logger.error(f"Consultant with ID '{consultant_id}' does not exist or is unavailable.")
                    return None

                # Check for consultant's availability
                conflicting_consultation = self.session.query(UserConsultation).filter(
                    UserConsultation.consultant_id == consultant_id,
                    UserConsultation.consultation_time == consultation_time,
                    UserConsultation.status == 'scheduled'
                ).first()
                if conflicting_consultation:
                    self.logger.error(f"Consultant ID '{consultant_id}' is already booked at '{consultation_time}'.")
                    return None

                consultation = UserConsultation(
                    user_id=user_id,
                    consultant_id=consultant_id,
                    consultation_time=consultation_time,
                    status='scheduled',
                    notes=None
                )
                self.session.add(consultation)
                self.session.commit()
                consultation_id = consultation.id
                self.logger.info(f"Consultation scheduled successfully with ID '{consultation_id}' between user ID '{user_id}' and consultant ID '{consultant_id}'.")
                return consultation_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while scheduling consultation for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while scheduling consultation for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def cancel_consultation(self, consultation_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancels a scheduled consultation.

        Args:
            consultation_id (str): The unique identifier of the consultation.
            reason (Optional[str], optional): The reason for cancellation. Defaults to None.

        Returns:
            bool: True if cancellation is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Cancelling consultation ID '{consultation_id}' with reason: '{reason}'.")
            with self.lock:
                consultation = self.session.query(UserConsultation).filter(UserConsultation.id == consultation_id).first()
                if not consultation:
                    self.logger.error(f"Consultation with ID '{consultation_id}' does not exist.")
                    return False
                if consultation.status in ['completed', 'cancelled']:
                    self.logger.error(f"Cannot cancel consultation ID '{consultation_id}' as it is already '{consultation.status}'.")
                    return False

                consultation.status = 'cancelled'
                consultation.notes = reason
                self.session.commit()

                # Optionally, notify consultant and user via communication API
                self._notify_parties(consultation, cancellation=True)

                self.logger.info(f"Consultation ID '{consultation_id}' cancelled successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while cancelling consultation ID '{consultation_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while cancelling consultation ID '{consultation_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def complete_consultation(self, consultation_id: str, notes: Optional[str] = None, rating: Optional[float] = None) -> bool:
        """
        Marks a consultation as completed and records feedback.

        Args:
            consultation_id (str): The unique identifier of the consultation.
            notes (Optional[str], optional): Notes from the consultation. Defaults to None.
            rating (Optional[float], optional): Rating for the consultant (1.0 to 5.0). Defaults to None.

        Returns:
            bool: True if completion is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Completing consultation ID '{consultation_id}' with notes: '{notes}' and rating: '{rating}'.")
            if rating is not None and not (1.0 <= rating <= 5.0):
                self.logger.error("Rating must be between 1.0 and 5.0.")
                return False

            with self.lock:
                consultation = self.session.query(UserConsultation).filter(
                    UserConsultation.id == consultation_id,
                    UserConsultation.status == 'scheduled'
                ).first()
                if not consultation:
                    self.logger.error(f"Consultation with ID '{consultation_id}' does not exist or is not scheduled.")
                    return False

                consultation.status = 'completed'
                consultation.notes = notes
                self.session.commit()

                if rating is not None:
                    consultant = self.session.query(LegalConsultant).filter(LegalConsultant.id == consultation.consultant_id).first()
                    if consultant:
                        total_consultations = self.session.query(UserConsultation).filter(
                            UserConsultation.consultant_id == consultant.id,
                            UserConsultation.status == 'completed'
                        ).count()
                        consultant.rating = ((consultant.rating * (total_consultations - 1)) + rating) / total_consultations
                        self.session.commit()
                        self.logger.info(f"Consultant ID '{consultant.id}' rating updated to '{consultant.rating}' based on new rating '{rating}'.")

                # Optionally, notify user and consultant via communication API
                self._notify_parties(consultation, completion=True)

                self.logger.info(f"Consultation ID '{consultation_id}' marked as completed successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while completing consultation ID '{consultation_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while completing consultation ID '{consultation_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _notify_parties(self, consultation: 'UserConsultation', cancellation: bool = False, completion: bool = False):
        """
        Notifies the user and consultant about consultation status changes via external communication API.

        Args:
            consultation (UserConsultation): The consultation instance.
            cancellation (bool, optional): Flag indicating if the notification is for cancellation. Defaults to False.
            completion (bool, optional): Flag indicating if the notification is for completion. Defaults to False.
        """
        try:
            self.logger.debug(f"Notifying parties for consultation ID '{consultation.id}'. Cancellation: {cancellation}, Completion: {completion}.")
            headers = {
                'Authorization': f"Bearer {self.communication_api_key}",
                'Content-Type': 'application/json'
            }

            messages = []
            if cancellation:
                message_user = f"Your consultation scheduled at {consultation.consultation_time} has been cancelled."
                message_consultant = f"A consultation with user ID '{consultation.user_id}' scheduled at {consultation.consultation_time} has been cancelled."
                messages.append({'recipient': consultation.user.email, 'message': message_user})
                messages.append({'recipient': consultation.consultant.email, 'message': message_consultant})
            if completion:
                message_user = f"Your consultation scheduled at {consultation.consultation_time} has been completed. Thank you for your feedback!"
                message_consultant = f"A consultation with user ID '{consultation.user_id}' has been completed."
                messages.append({'recipient': consultation.user.email, 'message': message_user})
                messages.append({'recipient': consultation.consultant.email, 'message': message_consultant})

            for msg in messages:
                payload = {
                    'to': msg['recipient'],
                    'message': msg['message']
                }
                response = self.session_requests.post(
                    f"{self.communication_api_url}/send",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to send notification to '{msg['recipient']}'. Status Code: {response.status_code}, Response: {response.text}")
                else:
                    self.logger.debug(f"Notification sent to '{msg['recipient']}' successfully.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending notifications: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while sending notifications: {e}", exc_info=True)

    def list_consultants(self, specialization: Optional[str] = None, available: Optional[bool] = True) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of legal consultants, optionally filtering by specialization and availability.

        Args:
            specialization (Optional[str], optional): The specialization to filter consultants. Defaults to None.
            available (Optional[bool], optional): Whether to filter by availability. Defaults to True.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of consultants if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Listing consultants with specialization='{specialization}' and available='{available}'.")
            with self.lock:
                query = self.session.query(LegalConsultant)
                if specialization:
                    query = query.filter(LegalConsultant.specialization.ilike(f"%{specialization}%"))
                if available is not None:
                    query = query.filter(LegalConsultant.available == available)
                consultants = query.all()
                consultant_list = [
                    {
                        'id': consultant.id,
                        'name': consultant.name,
                        'specialization': consultant.specialization,
                        'email': consultant.email,
                        'phone': consultant.phone,
                        'rating': consultant.rating,
                        'available': consultant.available,
                        'created_at': consultant.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': consultant.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for consultant in consultants
                ]
                self.logger.info(f"Retrieved {len(consultant_list)} consultants based on filters.")
                return consultant_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while listing consultants: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while listing consultants: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing LegalConsultantService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("LegalConsultantService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing LegalConsultantService: {e}", exc_info=True)
            raise LegalConsultantServiceError(f"Error closing LegalConsultantService: {e}")
