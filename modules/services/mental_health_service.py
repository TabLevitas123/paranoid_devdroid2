# services/mental_health_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class Therapist(Base):
    __tablename__ = 'therapists'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    specialization = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    rating = Column(Float, default=5.0)
    available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    appointments = relationship("Appointment", back_populates="therapist")

class UserMentalHealthProfile(Base):
    __tablename__ = 'user_mental_health_profiles'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    anxiety_level = Column(Float, default=0.0)
    depression_level = Column(Float, default=0.0)
    stress_level = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    appointments = relationship("Appointment", back_populates="user")
    user = relationship("User", backref="mental_health_profile")

class Appointment(Base):
    __tablename__ = 'appointments'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    therapist_id = Column(String, ForeignKey('therapists.id'), nullable=False)
    appointment_time = Column(DateTime, nullable=False)
    status = Column(String, default='scheduled')  # scheduled, completed, cancelled
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="appointments")
    therapist = relationship("Therapist", back_populates="appointments")

class MentalHealthServiceError(Exception):
    """Custom exception for MentalHealthService-related errors."""
    pass

class MentalHealthService:
    """
    Provides mental health support functionalities, including therapist management,
    appointment scheduling, user mental health profiling, session tracking, and feedback.
    Utilizes SQLAlchemy for database interactions and integrates with third-party APIs
    for notifications (e.g., email, SMS). Ensures secure handling of user data and
    compliance with privacy regulations.
    """

    def __init__(self):
        """
        Initializes the MentalHealthService with necessary configurations and authentication.
        """
        self.logger = setup_logging('MentalHealthService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("MentalHealthService initialized successfully.")

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
                raise MentalHealthServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise MentalHealthServiceError(f"Error initializing database: {e}")

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
            raise MentalHealthServiceError(f"Unsupported database type '{db_type}'.")

    def register_therapist(self, name: str, specialization: str, email: str, phone: str) -> Optional[str]:
        """
        Registers a new therapist.

        Args:
            name (str): The therapist's name.
            specialization (str): The therapist's specialization.
            email (str): The therapist's email address.
            phone (str): The therapist's phone number.

        Returns:
            Optional[str]: The therapist ID if registration is successful, else None.
        """
        try:
            self.logger.debug(f"Registering therapist '{name}' with specialization '{specialization}'.")
            with self.lock:
                existing_therapist = self.session.query(Therapist).filter(
                    (Therapist.email == email) | (Therapist.phone == phone)
                ).first()
                if existing_therapist:
                    self.logger.error("A therapist with the provided email or phone number already exists.")
                    return None

                therapist = Therapist(
                    name=name,
                    specialization=specialization,
                    email=email,
                    phone=phone,
                    available=True
                )
                self.session.add(therapist)
                self.session.commit()
                therapist_id = therapist.id
                self.logger.info(f"Therapist '{name}' registered successfully with ID '{therapist_id}'.")
                return therapist_id
        except Exception as e:
            self.logger.error(f"Error registering therapist '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def schedule_appointment(self, user_id: str, therapist_id: str, appointment_time: datetime) -> Optional[str]:
        """
        Schedules a new appointment between a user and a therapist.

        Args:
            user_id (str): The unique identifier of the user.
            therapist_id (str): The unique identifier of the therapist.
            appointment_time (datetime): The desired time for the appointment.

        Returns:
            Optional[str]: The appointment ID if scheduling is successful, else None.
        """
        try:
            self.logger.debug(f"Scheduling appointment for user ID '{user_id}' with therapist ID '{therapist_id}' at '{appointment_time}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id, User.role == 'customer').first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                therapist = self.session.query(Therapist).filter(Therapist.id == therapist_id, Therapist.available == True).first()
                if not therapist:
                    self.logger.error(f"Therapist with ID '{therapist_id}' does not exist or is unavailable.")
                    return None

                # Check for therapist's availability at the desired time
                conflicting_appointment = self.session.query(Appointment).filter(
                    Appointment.therapist_id == therapist_id,
                    Appointment.appointment_time == appointment_time,
                    Appointment.status == 'scheduled'
                ).first()
                if conflicting_appointment:
                    self.logger.error(f"Therapist ID '{therapist_id}' is already booked at '{appointment_time}'.")
                    return None

                appointment = Appointment(
                    user_id=user_id,
                    therapist_id=therapist_id,
                    appointment_time=appointment_time,
                    status='scheduled',
                    notes=None
                )
                self.session.add(appointment)
                self.session.commit()
                appointment_id = appointment.id
                self.logger.info(f"Appointment scheduled successfully with ID '{appointment_id}'.")
                return appointment_id
        except Exception as e:
            self.logger.error(f"Error scheduling appointment for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def cancel_appointment(self, appointment_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancels an existing appointment.

        Args:
            appointment_id (str): The unique identifier of the appointment.
            reason (Optional[str], optional): The reason for cancellation. Defaults to None.

        Returns:
            bool: True if the appointment is cancelled successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Cancelling appointment ID '{appointment_id}' with reason: {reason}.")
            with self.lock:
                appointment = self.session.query(Appointment).filter(Appointment.id == appointment_id).first()
                if not appointment:
                    self.logger.error(f"Appointment with ID '{appointment_id}' does not exist.")
                    return False
                if appointment.status in ['completed', 'cancelled']:
                    self.logger.error(f"Cannot cancel appointment ID '{appointment_id}' as it is already '{appointment.status}'.")
                    return False
                appointment.status = 'cancelled'
                appointment.notes = reason
                self.session.commit()
                self.logger.info(f"Appointment ID '{appointment_id}' cancelled successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error cancelling appointment ID '{appointment_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def complete_appointment(self, appointment_id: str, notes: Optional[str] = None, score: Optional[float] = None) -> bool:
        """
        Marks an appointment as completed and records notes and score.

        Args:
            appointment_id (str): The unique identifier of the appointment.
            notes (Optional[str], optional): Notes from the session. Defaults to None.
            score (Optional[float], optional): User's satisfaction score (1.0 to 5.0). Defaults to None.

        Returns:
            bool: True if the appointment is marked as completed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Completing appointment ID '{appointment_id}' with notes: {notes} and score: {score}.")
            if score is not None and not (1.0 <= score <= 5.0):
                self.logger.error("Score must be between 1.0 and 5.0.")
                return False

            with self.lock:
                appointment = self.session.query(Appointment).filter(Appointment.id == appointment_id, Appointment.status == 'scheduled').first()
                if not appointment:
                    self.logger.error(f"Appointment with ID '{appointment_id}' does not exist or is not scheduled.")
                    return False

                appointment.status = 'completed'
                appointment.notes = notes
                self.session.commit()

                if score is not None:
                    # Update therapist's rating
                    therapist = self.session.query(Therapist).filter(Therapist.id == appointment.therapist_id).first()
                    if therapist:
                        total_appointments = self.session.query(Appointment).filter(Appointment.therapist_id == therapist.id, Appointment.status == 'completed').count()
                        therapist.rating = ((therapist.rating * (total_appointments - 1)) + score) / total_appointments
                        self.session.commit()
                        self.logger.info(f"Therapist ID '{therapist.id}' rating updated to {therapist.rating} based on new score {score}.")

                self.logger.info(f"Appointment ID '{appointment_id}' marked as completed successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error completing appointment ID '{appointment_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def list_therapists(self, specialization: Optional[str] = None, available: Optional[bool] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of therapists, optionally filtering by specialization and availability.

        Args:
            specialization (Optional[str], optional): The specialization to filter therapists. Defaults to None.
            available (Optional[bool], optional): Whether to filter by availability. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of therapists if successful, else None.
        """
        try:
            self.logger.debug(f"Listing therapists with specialization='{specialization}' and available='{available}'.")
            with self.lock:
                query = self.session.query(Therapist)
                if specialization:
                    query = query.filter(Therapist.specialization.ilike(f"%{specialization}%"))
                if available is not None:
                    query = query.filter(Therapist.available == available)
                therapists = query.all()
                therapist_list = [
                    {
                        'id': therapist.id,
                        'name': therapist.name,
                        'specialization': therapist.specialization,
                        'email': therapist.email,
                        'phone': therapist.phone,
                        'rating': therapist.rating,
                        'available': therapist.available,
                        'created_at': therapist.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': therapist.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for therapist in therapists
                ]
                self.logger.info(f"Retrieved {len(therapist_list)} therapists based on filters.")
                return therapist_list
        except Exception as e:
            self.logger.error(f"Error listing therapists: {e}", exc_info=True)
            return None

    def get_user_appointments(self, user_id: str, status: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of appointments for a user, optionally filtering by status.

        Args:
            user_id (str): The unique identifier of the user.
            status (Optional[str], optional): The status to filter appointments. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of appointments if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving appointments for user ID '{user_id}' with status='{status}'.")
            with self.lock:
                query = self.session.query(Appointment).filter(Appointment.user_id == user_id)
                if status:
                    query = query.filter(Appointment.status == status)
                appointments = query.all()
                appointment_list = [
                    {
                        'id': appointment.id,
                        'therapist_id': appointment.therapist_id,
                        'appointment_time': appointment.appointment_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'status': appointment.status,
                        'notes': appointment.notes,
                        'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': appointment.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for appointment in appointments
                ]
                self.logger.info(f"Retrieved {len(appointment_list)} appointments for user ID '{user_id}'.")
                return appointment_list
        except Exception as e:
            self.logger.error(f"Error retrieving appointments for user ID '{user_id}': {e}", exc_info=True)
            return None

    def get_therapist_appointments(self, therapist_id: str, status: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of appointments for a therapist, optionally filtering by status.

        Args:
            therapist_id (str): The unique identifier of the therapist.
            status (Optional[str], optional): The status to filter appointments. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of appointments if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving appointments for therapist ID '{therapist_id}' with status='{status}'.")
            with self.lock:
                query = self.session.query(Appointment).filter(Appointment.therapist_id == therapist_id)
                if status:
                    query = query.filter(Appointment.status == status)
                appointments = query.all()
                appointment_list = [
                    {
                        'id': appointment.id,
                        'user_id': appointment.user_id,
                        'appointment_time': appointment.appointment_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'status': appointment.status,
                        'notes': appointment.notes,
                        'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': appointment.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for appointment in appointments
                ]
                self.logger.info(f"Retrieved {len(appointment_list)} appointments for therapist ID '{therapist_id}'.")
                return appointment_list
        except Exception as e:
            self.logger.error(f"Error retrieving appointments for therapist ID '{therapist_id}': {e}", exc_info=True)
            return None

    def update_therapist_availability(self, therapist_id: str, available: bool) -> bool:
        """
        Updates a therapist's availability status.

        Args:
            therapist_id (str): The unique identifier of the therapist.
            available (bool): The new availability status.

        Returns:
            bool: True if the availability is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Updating availability for therapist ID '{therapist_id}' to '{available}'.")
            with self.lock:
                therapist = self.session.query(Therapist).filter(Therapist.id == therapist_id).first()
                if not therapist:
                    self.logger.error(f"Therapist with ID '{therapist_id}' does not exist.")
                    return False
                therapist.available = available
                self.session.commit()
                self.logger.info(f"Therapist ID '{therapist_id}' availability updated to '{available}'.")
                return True
        except Exception as e:
            self.logger.error(f"Error updating availability for therapist ID '{therapist_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing MentalHealthService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("MentalHealthService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing MentalHealthService: {e}", exc_info=True)
            raise MentalHealthServiceError(f"Error closing MentalHealthService: {e}")
