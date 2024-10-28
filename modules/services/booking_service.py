# services/booking_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    role = Column(Enum('customer', 'provider', name='user_roles'), default='customer', nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    bookings = relationship("Booking", back_populates="user")
    services = relationship("Service", back_populates="provider")

class Service(Base):
    __tablename__ = 'services'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    availability = Column(Enum('available', 'unavailable', name='availability_status'), default='available', nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    provider = relationship("User", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

class Booking(Base):
    __tablename__ = 'bookings'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    service_id = Column(String, ForeignKey('services.id'), nullable=False)
    booking_time = Column(DateTime, nullable=False)
    status = Column(Enum('pending', 'confirmed', 'completed', 'cancelled', name='booking_status'), default='pending', nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")

class BookingServiceError(Exception):
    """Custom exception for BookingService-related errors."""
    pass

class BookingService:
    """
    Provides booking management capabilities, including user registrations, service listings,
    booking creation, status updates, scheduling, and notifications. Utilizes SQLAlchemy for
    database interactions and integrates with third-party APIs for notifications (e.g., email,
    SMS). Ensures secure handling of user data and service credentials.
    """

    def __init__(self):
        """
        Initializes the BookingService with necessary configurations and authentication.
        """
        self.logger = setup_logging('BookingService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("BookingService initialized successfully.")

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
                raise BookingServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise BookingServiceError(f"Error initializing database: {e}")

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
            raise BookingServiceError(f"Unsupported database type '{db_type}'.")

    def register_user(self, name: str, email: str, phone: str, role: str = 'customer') -> Optional[str]:
        """
        Registers a new user as a customer or provider.

        Args:
            name (str): The user's name.
            email (str): The user's email address.
            phone (str): The user's phone number.
            role (str, optional): The role of the user ('customer' or 'provider'). Defaults to 'customer'.

        Returns:
            Optional[str]: The user ID if registration is successful, else None.
        """
        try:
            self.logger.debug(f"Registering user '{name}' with email '{email}' and phone '{phone}' as '{role}'.")
            with self.lock:
                existing_user = self.session.query(User).filter((User.email == email) | (User.phone == phone)).first()
                if existing_user:
                    self.logger.error("A user with the provided email or phone number already exists.")
                    return None

                if role not in ['customer', 'provider']:
                    self.logger.error("Invalid role specified. Must be 'customer' or 'provider'.")
                    return None

                user = User(
                    name=name,
                    email=email,
                    phone=phone,
                    role=role
                )
                self.session.add(user)
                self.session.commit()
                user_id = user.id
                self.logger.info(f"User '{name}' registered successfully with ID '{user_id}' as '{role}'.")
                return user_id
        except Exception as e:
            self.logger.error(f"Error registering user '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def list_services(self, provider_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of available services, optionally filtered by provider.

        Args:
            provider_id (Optional[str], optional): The unique identifier of the provider. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of services if successful, else None.
        """
        try:
            self.logger.debug(f"Listing services with provider ID filter: {provider_id}.")
            with self.lock:
                query = self.session.query(Service)
                if provider_id:
                    query = query.filter(Service.provider_id == provider_id)
                services = query.all()
                service_list = [
                    {
                        'id': service.id,
                        'provider_id': service.provider_id,
                        'name': service.name,
                        'description': service.description,
                        'price': service.price,
                        'availability': service.availability,
                        'created_at': service.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': service.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for service in services
                ]
                self.logger.info(f"Retrieved {len(service_list)} services.")
                return service_list
        except Exception as e:
            self.logger.error(f"Error listing services: {e}", exc_info=True)
            return None

    def add_service(self, provider_id: str, name: str, description: str, price: float) -> Optional[str]:
        """
        Adds a new service offered by a provider.

        Args:
            provider_id (str): The unique identifier of the provider.
            name (str): The name of the service.
            description (str): A description of the service.
            price (float): The price of the service.

        Returns:
            Optional[str]: The service ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding service '{name}' for provider ID '{provider_id}'.")
            with self.lock:
                provider = self.session.query(User).filter(User.id == provider_id, User.role == 'provider').first()
                if not provider:
                    self.logger.error(f"Provider with ID '{provider_id}' does not exist.")
                    return None

                service = Service(
                    provider_id=provider_id,
                    name=name,
                    description=description,
                    price=price,
                    availability='available'
                )
                self.session.add(service)
                self.session.commit()
                service_id = service.id
                self.logger.info(f"Service '{name}' added successfully with ID '{service_id}' for provider ID '{provider_id}'.")
                return service_id
        except Exception as e:
            self.logger.error(f"Error adding service '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def create_booking(self, user_id: str, service_id: str, booking_time: datetime) -> Optional[str]:
        """
        Creates a new booking for a service.

        Args:
            user_id (str): The unique identifier of the user making the booking.
            service_id (str): The unique identifier of the service to book.
            booking_time (datetime): The desired time for the booking.

        Returns:
            Optional[str]: The booking ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"User ID '{user_id}' creating booking for service ID '{service_id}' at '{booking_time}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id, User.role == 'customer').first()
                if not user:
                    self.logger.error(f"Customer with ID '{user_id}' does not exist.")
                    return None

                service = self.session.query(Service).filter(Service.id == service_id, Service.availability == 'available').first()
                if not service:
                    self.logger.error(f"Service with ID '{service_id}' does not exist or is unavailable.")
                    return None

                # Check for provider availability at the desired booking time
                conflicting_booking = self.session.query(Booking).filter(
                    Booking.service_id == service_id,
                    Booking.booking_time == booking_time,
                    Booking.status.in_(['confirmed', 'in_progress'])
                ).first()
                if conflicting_booking:
                    self.logger.error(f"Service ID '{service_id}' is already booked at '{booking_time}'.")
                    return None

                booking = Booking(
                    user_id=user_id,
                    service_id=service_id,
                    booking_time=booking_time,
                    status='confirmed'
                )
                self.session.add(booking)
                self.session.commit()
                booking_id = booking.id
                self.logger.info(f"Booking created successfully with ID '{booking_id}' for user ID '{user_id}'.")
                return booking_id
        except Exception as e:
            self.logger.error(f"Error creating booking for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_booking_status(self, booking_id: str, new_status: str) -> bool:
        """
        Updates the status of an existing booking.

        Args:
            booking_id (str): The unique identifier of the booking.
            new_status (str): The new status ('pending', 'confirmed', 'completed', 'cancelled').

        Returns:
            bool: True if the status is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Updating booking ID '{booking_id}' to status '{new_status}'.")
            if new_status not in ['pending', 'confirmed', 'completed', 'cancelled']:
                self.logger.error("Invalid status provided.")
                return False

            with self.lock:
                booking = self.session.query(Booking).filter(Booking.id == booking_id).first()
                if not booking:
                    self.logger.error(f"Booking with ID '{booking_id}' does not exist.")
                    return False

                booking.status = new_status
                booking.updated_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Booking ID '{booking_id}' updated to status '{new_status}' successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error updating booking ID '{booking_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def cancel_booking(self, booking_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancels an existing booking with an optional reason.

        Args:
            booking_id (str): The unique identifier of the booking.
            reason (Optional[str], optional): The reason for cancellation. Defaults to None.

        Returns:
            bool: True if the booking is cancelled successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Cancelling booking ID '{booking_id}' with reason: {reason}.")
            with self.lock:
                booking = self.session.query(Booking).filter(Booking.id == booking_id).first()
                if not booking:
                    self.logger.error(f"Booking with ID '{booking_id}' does not exist.")
                    return False
                if booking.status in ['completed', 'cancelled']:
                    self.logger.error(f"Cannot cancel booking ID '{booking_id}' as it is already '{booking.status}'.")
                    return False
                booking.status = 'cancelled'
                booking.updated_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Booking ID '{booking_id}' cancelled successfully.")
                # Optionally, notify the provider and user about the cancellation
                return True
        except Exception as e:
            self.logger.error(f"Error cancelling booking ID '{booking_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def list_bookings(self, user_id: Optional[str] = None, role: Optional[str] = None, status: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of bookings based on filters.

        Args:
            user_id (Optional[str], optional): The unique identifier of the user. Defaults to None.
            role (Optional[str], optional): The role of the user ('customer' or 'provider'). Defaults to None.
            status (Optional[str], optional): The status of the bookings to filter. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of bookings if successful, else None.
        """
        try:
            self.logger.debug(f"Listing bookings with filters - User ID: {user_id}, Role: {role}, Status: {status}.")
            with self.lock:
                query = self.session.query(Booking)
                if user_id and role:
                    if role == 'customer':
                        query = query.filter(Booking.user_id == user_id)
                    elif role == 'provider':
                        query = query.filter(Booking.service_id.in_(
                            self.session.query(Service.id).filter(Service.provider_id == user_id)
                        ))
                    else:
                        self.logger.error("Invalid role specified. Must be 'customer' or 'provider'.")
                        return None
                if status:
                    query = query.filter(Booking.status == status)
                bookings = query.all()
                booking_list = [
                    {
                        'id': booking.id,
                        'user_id': booking.user_id,
                        'service_id': booking.service_id,
                        'booking_time': booking.booking_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'status': booking.status,
                        'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': booking.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for booking in bookings
                ]
                self.logger.info(f"Retrieved {len(booking_list)} bookings based on filters.")
                return booking_list
        except Exception as e:
            self.logger.error(f"Error listing bookings: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing BookingService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("BookingService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing BookingService: {e}", exc_info=True)
            raise BookingServiceError(f"Error closing BookingService: {e}")
