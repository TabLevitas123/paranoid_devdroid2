# services/fitness_tracker_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
import os
from datetime import datetime, timedelta
import requests
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class FitnessData(Base):
    __tablename__ = 'fitness_data'

    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    steps = Column(Integer, default=0)
    distance_km = Column(Float, default=0.0)
    calories_burned = Column(Float, default=0.0)
    heart_rate = Column(Float, default=0.0)

class FitnessTrackerServiceError(Exception):
    """Custom exception for FitnessTrackerService-related errors."""
    pass

class FitnessTrackerService:
    """
    Provides fitness tracking capabilities, including recording physical activities,
    integrating with fitness devices/sensors, storing and retrieving fitness data,
    and providing analytics and reports. Utilizes SQLAlchemy for database interactions
    and integrates with third-party APIs for extended functionalities. Ensures
    secure handling of user data and device credentials.
    """

    def __init__(self):
        """
        Initializes the FitnessTrackerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('FitnessTrackerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("FitnessTrackerService initialized successfully.")

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
                self.logger.error("Incomplete database configuration.")
                raise FitnessTrackerServiceError("Incomplete database configuration.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise FitnessTrackerServiceError(f"Error initializing database: {e}")

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
            raise FitnessTrackerServiceError(f"Unsupported database type '{db_type}'.")

    def record_activity(self, user_id: str, steps: int, distance_km: float, calories_burned: float, heart_rate: float) -> bool:
        """
        Records a user's physical activity data.

        Args:
            user_id (str): The unique identifier of the user.
            steps (int): Number of steps taken.
            distance_km (float): Distance covered in kilometers.
            calories_burned (float): Calories burned.
            heart_rate (float): Average heart rate during activity.

        Returns:
            bool: True if the activity is recorded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Recording activity for user '{user_id}': Steps={steps}, Distance={distance_km} km, Calories={calories_burned}, Heart Rate={heart_rate}.")
            with self.lock:
                activity = FitnessData(
                    user_id=user_id,
                    steps=steps,
                    distance_km=distance_km,
                    calories_burned=calories_burned,
                    heart_rate=heart_rate
                )
                self.session.add(activity)
                self.session.commit()
                self.logger.info(f"Activity recorded successfully for user '{user_id}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error recording activity for user '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_activity_data(self, user_id: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves activity data for a user within a specified date range.

        Args:
            user_id (str): The unique identifier of the user.
            start_date (Optional[datetime], optional): The start date for data retrieval. Defaults to None.
            end_date (Optional[datetime], optional): The end date for data retrieval. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of activity records, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Retrieving activity data for user '{user_id}' from {start_date} to {end_date}.")
            with self.lock:
                query = self.session.query(FitnessData).filter(FitnessData.user_id == user_id)
                if start_date:
                    query = query.filter(FitnessData.date >= start_date)
                if end_date:
                    query = query.filter(FitnessData.date <= end_date)
                activities = query.order_by(FitnessData.date.asc()).all()
                activity_list = [
                    {
                        'id': activity.id,
                        'user_id': activity.user_id,
                        'date': activity.date.strftime('%Y-%m-%d %H:%M:%S'),
                        'steps': activity.steps,
                        'distance_km': activity.distance_km,
                        'calories_burned': activity.calories_burned,
                        'heart_rate': activity.heart_rate
                    } for activity in activities
                ]
                self.logger.info(f"Retrieved {len(activity_list)} activity records for user '{user_id}'.")
            return activity_list
        except Exception as e:
            self.logger.error(f"Error retrieving activity data for user '{user_id}': {e}", exc_info=True)
            return None

    def get_weekly_summary(self, user_id: str, week_start: datetime) -> Optional[Dict[str, Any]]:
        """
        Provides a weekly summary of a user's activities.

        Args:
            user_id (str): The unique identifier of the user.
            week_start (datetime): The starting date of the week.

        Returns:
            Optional[Dict[str, Any]]: A summary containing total steps, distance, calories, and average heart rate, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Generating weekly summary for user '{user_id}' starting from {week_start}.")
            week_end = week_start + timedelta(days=7)
            activities = self.get_activity_data(user_id, start_date=week_start, end_date=week_end)
            if not activities:
                self.logger.warning(f"No activities found for user '{user_id}' in the specified week.")
                return None
            total_steps = sum(activity['steps'] for activity in activities)
            total_distance = sum(activity['distance_km'] for activity in activities)
            total_calories = sum(activity['calories_burned'] for activity in activities)
            average_heart_rate = sum(activity['heart_rate'] for activity in activities) / len(activities)
            summary = {
                'user_id': user_id,
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'total_steps': total_steps,
                'total_distance_km': total_distance,
                'total_calories_burned': total_calories,
                'average_heart_rate': round(average_heart_rate, 2)
            }
            self.logger.info(f"Weekly summary generated for user '{user_id}'.")
            return summary
        except Exception as e:
            self.logger.error(f"Error generating weekly summary for user '{user_id}': {e}", exc_info=True)
            return None

    def integrate_with_device(self, device_api_url: str, device_api_key: str) -> bool:
        """
        Integrates with a fitness device's API to fetch real-time data.

        Args:
            device_api_url (str): The API endpoint of the fitness device.
            device_api_key (str): The API key for authenticating with the device.

        Returns:
            bool: True if integration is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Integrating with fitness device at '{device_api_url}'.")
            headers = {
                'Authorization': f"Bearer {device_api_key}"
            }
            response = requests.get(device_api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                device_data = response.json()
                self.logger.info(f"Data fetched successfully from fitness device at '{device_api_url}'.")
                # Process and store device data
                self._process_device_data(device_data)
                return True
            else:
                self.logger.error(f"Failed to fetch data from device: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Error integrating with device at '{device_api_url}': {e}", exc_info=True)
            return False

    def _process_device_data(self, data: Dict[str, Any]) -> bool:
        """
        Processes and records data fetched from the fitness device.

        Args:
            data (Dict[str, Any]): The data retrieved from the device.

        Returns:
            bool: True if data is processed and recorded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Processing device data: {data}.")
            user_id = data.get('user_id')
            steps = data.get('steps', 0)
            distance_km = data.get('distance_km', 0.0)
            calories_burned = data.get('calories_burned', 0.0)
            heart_rate = data.get('heart_rate', 0.0)
            if not user_id:
                self.logger.error("User ID missing in device data.")
                return False
            self.record_activity(user_id, steps, distance_km, calories_burned, heart_rate)
            self.logger.debug("Device data processed and recorded successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error processing device data: {e}", exc_info=True)
            return False

    def generate_report(self, user_id: str, report_type: str, date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Generates a report for the user based on the specified report type.

        Args:
            user_id (str): The unique identifier of the user.
            report_type (str): The type of report ('daily', 'weekly', 'monthly', 'custom').
            date (Optional[datetime], optional): The reference date for the report. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: The generated report data, or None if generation fails.
        """
        try:
            self.logger.debug(f"Generating '{report_type}' report for user '{user_id}' with reference date {date}.")
            if not date:
                date = datetime.utcnow()
            if report_type.lower() == 'daily':
                start_date = datetime(date.year, date.month, date.day)
                end_date = start_date + timedelta(days=1)
                report = self._generate_summary(user_id, start_date, end_date)
            elif report_type.lower() == 'weekly':
                start_date = date - timedelta(days=date.weekday())  # Start of the week (Monday)
                end_date = start_date + timedelta(days=7)
                report = self._generate_summary(user_id, start_date, end_date)
            elif report_type.lower() == 'monthly':
                start_date = datetime(date.year, date.month, 1)
                if date.month == 12:
                    end_date = datetime(date.year + 1, 1, 1)
                else:
                    end_date = datetime(date.year, date.month + 1, 1)
                report = self._generate_summary(user_id, start_date, end_date)
            elif report_type.lower() == 'custom':
                # Placeholder for custom date range; implementation can be extended as needed
                self.logger.error("Custom report generation not implemented.")
                return None
            else:
                self.logger.error(f"Unsupported report type '{report_type}'.")
                return None
            self.logger.info(f"'{report_type}' report generated successfully for user '{user_id}'.")
            return report
        except Exception as e:
            self.logger.error(f"Error generating '{report_type}' report for user '{user_id}': {e}", exc_info=True)
            return None

    def _generate_summary(self, user_id: str, start_date: datetime, end_date: datetime) -> Optional[Dict[str, Any]]:
        """
        Generates a summary of activities for a user within a specified date range.

        Args:
            user_id (str): The unique identifier of the user.
            start_date (datetime): The start date of the summary.
            end_date (datetime): The end date of the summary.

        Returns:
            Optional[Dict[str, Any]]: The summary data, or None if generation fails.
        """
        try:
            self.logger.debug(f"Generating summary for user '{user_id}' from {start_date} to {end_date}.")
            activities = self.get_activity_data(user_id, start_date, end_date)
            if not activities:
                self.logger.warning(f"No activities found for user '{user_id}' in the specified date range.")
                return None
            total_steps = sum(activity['steps'] for activity in activities)
            total_distance = sum(activity['distance_km'] for activity in activities)
            total_calories = sum(activity['calories_burned'] for activity in activities)
            average_heart_rate = sum(activity['heart_rate'] for activity in activities) / len(activities)
            summary = {
                'user_id': user_id,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'total_steps': total_steps,
                'total_distance_km': total_distance,
                'total_calories_burned': total_calories,
                'average_heart_rate': round(average_heart_rate, 2)
            }
            self.logger.debug(f"Summary generated: {summary}.")
            return summary
        except Exception as e:
            self.logger.error(f"Error generating summary for user '{user_id}': {e}", exc_info=True)
            return None

    def export_data_to_csv(self, user_id: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, file_path: str = 'fitness_data.csv') -> bool:
        """
        Exports the user's activity data to a CSV file.

        Args:
            user_id (str): The unique identifier of the user.
            start_date (Optional[datetime], optional): The start date for data export. Defaults to None.
            end_date (Optional[datetime], optional): The end date for data export. Defaults to None.
            file_path (str, optional): The file path to save the CSV. Defaults to 'fitness_data.csv'.

        Returns:
            bool: True if export is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Exporting activity data for user '{user_id}' to '{file_path}'.")
            activities = self.get_activity_data(user_id, start_date, end_date)
            if not activities:
                self.logger.warning(f"No activities found for user '{user_id}' to export.")
                return False
            import csv
            with self.lock:
                with open(file_path, 'w', newline='') as csvfile:
                    fieldnames = ['id', 'user_id', 'date', 'steps', 'distance_km', 'calories_burned', 'heart_rate']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for activity in activities:
                        writer.writerow(activity)
                self.logger.info(f"Activity data exported successfully to '{file_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error exporting activity data for user '{user_id}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing FitnessTrackerService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("FitnessTrackerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing FitnessTrackerService: {e}", exc_info=True)
            raise FitnessTrackerServiceError(f"Error closing FitnessTrackerService: {e}")
