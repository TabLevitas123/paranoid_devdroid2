# services/ride_sharing_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import uuid
import requests
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
    rating = Column(Float, default=5.0)
    is_driver = Column(Integer, default=0)  # 0: Rider, 1: Driver
    driver_profile = relationship("DriverProfile", uselist=False, back_populates="user")

class DriverProfile(Base):
    __tablename__ = 'driver_profiles'

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), unique=True)
    vehicle_details = Column(String, nullable=False)
    license_number = Column(String, unique=True, nullable=False)
    rating = Column(Float, default=5.0)
    user = relationship("User", back_populates="driver_profile")

class Ride(Base):
    __tablename__ = 'rides'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rider_id = Column(String, ForeignKey('users.id'), nullable=False)
    driver_id = Column(String, ForeignKey('users.id'), nullable=True)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    status = Column(Enum('requested', 'accepted', 'in_progress', 'completed', 'cancelled', name='ride_status'), default='requested')
    fare = Column(Float, nullable=True)
    requested_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    rider = relationship("User", foreign_keys=[rider_id], backref="requested_rides")
    driver = relationship("User", foreign_keys=[driver_id], backref="assigned_rides")

class RideSharingServiceError(Exception):
    """Custom exception for RideSharingService-related errors."""
    pass

class RideSharingService:
    """
    Provides ride-sharing capabilities, including user registration, ride requests, driver assignments,
    real-time ride tracking, fare calculation, payment processing, and rating systems. Utilizes SQLAlchemy
    for database interactions and integrates with third-party APIs for mapping and payment functionalities.
    Ensures secure handling of user data, payment information, and real-time communications.
    """

    def __init__(self):
        """
        Initializes the RideSharingService with necessary configurations and authentication.
        """
        self.logger = setup_logging('RideSharingService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("RideSharingService initialized successfully.")

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
                raise RideSharingServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise RideSharingServiceError(f"Error initializing database: {e}")

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
            raise RideSharingServiceError(f"Unsupported database type '{db_type}'.")

    def register_user(self, name: str, email: str, phone: str, is_driver: bool = False, vehicle_details: Optional[str] = None, license_number: Optional[str] = None) -> Optional[str]:
        """
        Registers a new user as a rider or driver.

        Args:
            name (str): The user's name.
            email (str): The user's email address.
            phone (str): The user's phone number.
            is_driver (bool, optional): Whether the user is a driver. Defaults to False.
            vehicle_details (Optional[str], optional): Vehicle details if user is a driver. Defaults to None.
            license_number (Optional[str], optional): Driver's license number if user is a driver. Defaults to None.

        Returns:
            Optional[str]: The user ID if registration is successful, else None.
        """
        try:
            self.logger.debug(f"Registering user '{name}' with email '{email}' and phone '{phone}'. Driver status: {is_driver}.")
            with self.lock:
                existing_user = self.session.query(User).filter((User.email == email) | (User.phone == phone)).first()
                if existing_user:
                    self.logger.error("A user with the provided email or phone number already exists.")
                    return None

                user = User(
                    name=name,
                    email=email,
                    phone=phone,
                    is_driver=1 if is_driver else 0
                )
                self.session.add(user)
                self.session.commit()
                user_id = user.id
                self.logger.info(f"User '{name}' registered successfully with ID '{user_id}'.")

                if is_driver:
                    if not all([vehicle_details, license_number]):
                        self.logger.error("Vehicle details and license number are required for driver registration.")
                        self.session.delete(user)
                        self.session.commit()
                        return None
                    driver_profile = DriverProfile(
                        user_id=user_id,
                        vehicle_details=vehicle_details,
                        license_number=license_number
                    )
                    self.session.add(driver_profile)
                    self.session.commit()
                    self.logger.info(f"Driver profile created for user ID '{user_id}'.")
                return user_id
        except Exception as e:
            self.logger.error(f"Error registering user '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def request_ride(self, rider_id: str, origin: str, destination: str) -> Optional[str]:
        """
        Allows a rider to request a ride.

        Args:
            rider_id (str): The unique identifier of the rider.
            origin (str): The starting location.
            destination (str): The destination location.

        Returns:
            Optional[str]: The ride ID if the request is successful, else None.
        """
        try:
            self.logger.debug(f"User '{rider_id}' requesting ride from '{origin}' to '{destination}'.")
            with self.lock:
                rider = self.session.query(User).filter(User.id == rider_id, User.is_driver == 0).first()
                if not rider:
                    self.logger.error(f"Rider with ID '{rider_id}' does not exist.")
                    return None

                ride = Ride(
                    rider_id=rider_id,
                    origin=origin,
                    destination=destination
                )
                self.session.add(ride)
                self.session.commit()
                ride_id = ride.id
                self.logger.info(f"Ride requested successfully with ID '{ride_id}'.")
                
                # Initiate driver assignment process
                self._assign_driver_to_ride(ride_id)
                return ride_id
        except Exception as e:
            self.logger.error(f"Error requesting ride for user '{rider_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _assign_driver_to_ride(self, ride_id: str) -> bool:
        """
        Assigns an available driver to the requested ride based on proximity and rating.

        Args:
            ride_id (str): The unique identifier of the ride.

        Returns:
            bool: True if a driver is assigned successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Assigning driver to ride ID '{ride_id}'.")
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status == 'requested').first()
                if not ride:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or not in 'requested' status.")
                    return False

                # Fetch available drivers (drivers not currently assigned to a ride)
                available_drivers = self.session.query(User).filter(User.is_driver == 1).all()
                if not available_drivers:
                    self.logger.warning("No drivers available at the moment.")
                    return False

                # Simple driver assignment based on highest rating
                available_drivers.sort(key=lambda x: x.driver_profile.rating, reverse=True)
                assigned_driver = available_drivers[0]
                ride.driver_id = assigned_driver.id
                ride.status = 'accepted'
                ride.fare = self._calculate_fare(ride.origin, ride.destination)
                self.session.commit()
                self.logger.info(f"Driver '{assigned_driver.id}' assigned to ride ID '{ride_id}'. Fare: {ride.fare}.")
                return True
        except Exception as e:
            self.logger.error(f"Error assigning driver to ride ID '{ride_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def _calculate_fare(self, origin: str, destination: str) -> float:
        """
        Calculates the fare for the ride based on distance and time.

        Args:
            origin (str): The starting location.
            destination (str): The destination location.

        Returns:
            float: The calculated fare.
        """
        try:
            self.logger.debug(f"Calculating fare from '{origin}' to '{destination}'.")
            # Placeholder for actual fare calculation logic, possibly integrating with mapping APIs
            # For demonstration, we'll use a fixed rate per kilometer
            distance_km = self._get_distance_between_locations(origin, destination)
            fare = distance_km * 1.5  # Example: $1.5 per kilometer
            self.logger.debug(f"Distance: {distance_km} km. Fare: {fare}.")
            return round(fare, 2)
        except Exception as e:
            self.logger.error(f"Error calculating fare from '{origin}' to '{destination}': {e}", exc_info=True)
            return 0.0

    def _get_distance_between_locations(self, origin: str, destination: str) -> float:
        """
        Retrieves the distance between two locations using a mapping API.

        Args:
            origin (str): The starting location.
            destination (str): The destination location.

        Returns:
            float: The distance in kilometers.
        """
        try:
            self.logger.debug(f"Retrieving distance between '{origin}' and '{destination}'.")
            with self.lock:
                params = {
                    'origins': origin,
                    'destinations': destination,
                    'key': self.config_loader.get('MAPPING_API_KEY')
                }
                response = self.session.get("https://maps.googleapis.com/maps/api/distancematrix/json", params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == 'OK':
                        distance_text = data['rows'][0]['elements'][0]['distance']['text']
                        distance_km = float(distance_text.replace(' km', '').replace(',', ''))
                        self.logger.debug(f"Distance between '{origin}' and '{destination}': {distance_km} km.")
                        return distance_km
                    else:
                        self.logger.error(f"Error retrieving distance: {data['status']} - {data.get('error_message', '')}")
                        return 0.0
                else:
                    self.logger.error(f"Failed to retrieve distance. HTTP Status Code: {response.status_code}")
                    return 0.0
        except Exception as e:
            self.logger.error(f"Error retrieving distance between '{origin}' and '{destination}': {e}", exc_info=True)
            return 0.0

    def accept_ride(self, driver_id: str, ride_id: str) -> bool:
        """
        Allows a driver to accept a ride request.

        Args:
            driver_id (str): The unique identifier of the driver.
            ride_id (str): The unique identifier of the ride.

        Returns:
            bool: True if the ride is accepted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Driver '{driver_id}' attempting to accept ride ID '{ride_id}'.")
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status == 'requested').first()
                driver = self.session.query(User).filter(User.id == driver_id, User.is_driver == 1).first()
                if not ride:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or not available for acceptance.")
                    return False
                if not driver:
                    self.logger.error(f"Driver with ID '{driver_id}' does not exist or is not a driver.")
                    return False
                ride.driver_id = driver_id
                ride.status = 'accepted'
                ride.fare = self._calculate_fare(ride.origin, ride.destination)
                self.session.commit()
                self.logger.info(f"Driver '{driver_id}' accepted ride ID '{ride_id}'. Fare: {ride.fare}.")
                return True
        except Exception as e:
            self.logger.error(f"Error accepting ride ID '{ride_id}' by driver '{driver_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def start_ride(self, ride_id: str) -> bool:
        """
        Marks the ride as in progress.

        Args:
            ride_id (str): The unique identifier of the ride.

        Returns:
            bool: True if the ride status is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Starting ride ID '{ride_id}'.")
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status == 'accepted').first()
                if not ride:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or not in 'accepted' status.")
                    return False
                ride.status = 'in_progress'
                ride.started_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Ride ID '{ride_id}' marked as 'in_progress'.")
                return True
        except Exception as e:
            self.logger.error(f"Error starting ride ID '{ride_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def complete_ride(self, ride_id: str) -> bool:
        """
        Marks the ride as completed and updates relevant details.

        Args:
            ride_id (str): The unique identifier of the ride.

        Returns:
            bool: True if the ride is completed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Completing ride ID '{ride_id}'.")
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status == 'in_progress').first()
                if not ride:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or not in 'in_progress' status.")
                    return False
                ride.status = 'completed'
                ride.completed_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Ride ID '{ride_id}' marked as 'completed'.")
                return True
        except Exception as e:
            self.logger.error(f"Error completing ride ID '{ride_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def cancel_ride(self, ride_id: str, reason: str = "No reason provided") -> bool:
        """
        Cancels a ride request with an optional reason.

        Args:
            ride_id (str): The unique identifier of the ride.
            reason (str, optional): The reason for cancellation. Defaults to "No reason provided".

        Returns:
            bool: True if the ride is cancelled successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Cancelling ride ID '{ride_id}' with reason: {reason}.")
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status.in_(['requested', 'accepted'])).first()
                if not ride:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or cannot be cancelled at this stage.")
                    return False
                ride.status = 'cancelled'
                self.session.commit()
                self.logger.info(f"Ride ID '{ride_id}' cancelled successfully. Reason: {reason}.")
                return True
        except Exception as e:
            self.logger.error(f"Error cancelling ride ID '{ride_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def rate_driver(self, ride_id: str, rating: float) -> bool:
        """
        Allows a rider to rate the driver after ride completion.

        Args:
            ride_id (str): The unique identifier of the ride.
            rating (float): The rating value (1.0 to 5.0).

        Returns:
            bool: True if the rating is submitted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Rider rating driver for ride ID '{ride_id}' with rating {rating}.")
            if not (1.0 <= rating <= 5.0):
                self.logger.error("Rating must be between 1.0 and 5.0.")
                return False
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status == 'completed').first()
                if not ride or not ride.driver_id:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or does not have an assigned driver.")
                    return False
                driver_profile = self.session.query(DriverProfile).filter(DriverProfile.user_id == ride.driver_id).first()
                if not driver_profile:
                    self.logger.error(f"Driver profile for user ID '{ride.driver_id}' not found.")
                    return False
                # Update driver's rating
                total_rides = self.session.query(Ride).filter(Ride.driver_id == ride.driver_id, Ride.status == 'completed').count()
                driver_profile.rating = ((driver_profile.rating * (total_rides - 1)) + rating) / total_rides
                self.session.commit()
                self.logger.info(f"Driver '{ride.driver_id}' rated successfully. New rating: {driver_profile.rating}.")
                return True
        except Exception as e:
            self.logger.error(f"Error rating driver for ride ID '{ride_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_user_rides(self, user_id: str, role: str = 'rider') -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of rides associated with a user.

        Args:
            user_id (str): The unique identifier of the user.
            role (str, optional): The role of the user ('rider' or 'driver'). Defaults to 'rider'.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of ride details if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving rides for user '{user_id}' with role '{role}'.")
            with self.lock:
                if role.lower() == 'rider':
                    rides = self.session.query(Ride).filter(Ride.rider_id == user_id).all()
                elif role.lower() == 'driver':
                    rides = self.session.query(Ride).filter(Ride.driver_id == user_id).all()
                else:
                    self.logger.error("Invalid role specified. Must be 'rider' or 'driver'.")
                    return None
                ride_list = [
                    {
                        'id': ride.id,
                        'rider_id': ride.rider_id,
                        'driver_id': ride.driver_id,
                        'origin': ride.origin,
                        'destination': ride.destination,
                        'status': ride.status,
                        'fare': ride.fare,
                        'requested_at': ride.requested_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'started_at': ride.started_at.strftime('%Y-%m-%d %H:%M:%S') if ride.started_at else None,
                        'completed_at': ride.completed_at.strftime('%Y-%m-%d %H:%M:%S') if ride.completed_at else None
                    } for ride in rides
                ]
                self.logger.info(f"Retrieved {len(ride_list)} rides for user '{user_id}'.")
                return ride_list
        except Exception as e:
            self.logger.error(f"Error retrieving rides for user '{user_id}': {e}", exc_info=True)
            return None

    def process_payment(self, ride_id: str, payment_details: Dict[str, Any]) -> bool:
        """
        Processes the payment for a completed ride.

        Args:
            ride_id (str): The unique identifier of the ride.
            payment_details (Dict[str, Any]): The payment information (e.g., payment method, amount).

        Returns:
            bool: True if the payment is processed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Processing payment for ride ID '{ride_id}' with details: {payment_details}.")
            with self.lock:
                ride = self.session.query(Ride).filter(Ride.id == ride_id, Ride.status == 'completed').first()
                if not ride:
                    self.logger.error(f"Ride with ID '{ride_id}' not found or not completed.")
                    return False
                if ride.fare is None:
                    self.logger.error("Fare not calculated for the ride.")
                    return False
                # Integrate with a payment gateway API (e.g., Stripe, PayPal)
                payment_api_config = self.config_loader.get('PAYMENT_API_CONFIG', {})
                payment_api_key_encrypted = payment_api_config.get('api_key')
                payment_api_url = payment_api_config.get('api_url')
                if not payment_api_key_encrypted or not payment_api_url:
                    self.logger.error("Payment API configuration is incomplete.")
                    return False
                payment_api_key = self.encryption_manager.decrypt_data(payment_api_key_encrypted).decode('utf-8')
                headers = {
                    'Authorization': f"Bearer {payment_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'amount': ride.fare,
                    'currency': 'USD',
                    'payment_method': payment_details.get('payment_method'),
                    'ride_id': ride.id
                }
                response = self.session.post(payment_api_url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    payment_response = response.json()
                    if payment_response.get('status') == 'success':
                        self.logger.info(f"Payment processed successfully for ride ID '{ride_id}'.")
                        return True
                    else:
                        self.logger.error(f"Payment processing failed: {payment_response.get('message')}")
                        return False
                else:
                    self.logger.error(f"Failed to process payment. HTTP Status Code: {response.status_code}")
                    return False
        except Exception as e:
            self.logger.error(f"Error processing payment for ride ID '{ride_id}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing RideSharingService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("RideSharingService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing RideSharingService: {e}", exc_info=True)
            raise RideSharingServiceError(f"Error closing RideSharingService: {e}")
