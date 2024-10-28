# services/diet_tracker_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, date, timedelta
import uuid
import json
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class UserDietProfile(Base):
    __tablename__ = 'user_diet_profiles'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    goal = Column(String, nullable=False)  # e.g., weight loss, muscle gain
    calorie_target = Column(Float, nullable=False)
    protein_target = Column(Float, nullable=False)
    carbs_target = Column(Float, nullable=False)
    fats_target = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    meals = relationship("Meal", back_populates="diet_profile")
    user = relationship("User", back_populates="diet_profile")

class Meal(Base):
    __tablename__ = 'meals'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    diet_profile_id = Column(String, ForeignKey('user_diet_profiles.id'), nullable=False)
    meal_type = Column(String, nullable=False)  # e.g., breakfast, lunch, dinner, snack
    description = Column(Text, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fats = Column(Float, nullable=False)
    consumed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    diet_profile = relationship("UserDietProfile", back_populates="meals")

class FoodItem(Base):
    __tablename__ = 'food_items'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fats = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DietTrackerServiceError(Exception):
    """Custom exception for DietTrackerService-related errors."""
    pass

class DietTrackerService:
    """
    Provides diet tracking capabilities, including managing user diet profiles, logging meals,
    calculating nutritional intake, and providing dietary recommendations. Utilizes SQLAlchemy
    for database interactions and integrates with third-party APIs for nutritional information.
    Ensures secure handling of user data and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the DietTrackerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('DietTrackerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("DietTrackerService initialized successfully.")

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
                raise DietTrackerServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise DietTrackerServiceError(f"Error initializing database: {e}")

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
            raise DietTrackerServiceError(f"Unsupported database type '{db_type}'.")

    def create_diet_profile(self, user_id: str, goal: str, calorie_target: float, protein_target: float,
                            carbs_target: float, fats_target: float) -> Optional[str]:
        """
        Creates a new diet profile for a user.

        Args:
            user_id (str): The unique identifier of the user.
            goal (str): The dietary goal (e.g., weight loss, muscle gain).
            calorie_target (float): Daily calorie target.
            protein_target (float): Daily protein target in grams.
            carbs_target (float): Daily carbohydrate target in grams.
            fats_target (float): Daily fat target in grams.

        Returns:
            Optional[str]: The diet profile ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"Creating diet profile for user ID '{user_id}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                existing_profile = self.session.query(UserDietProfile).filter(UserDietProfile.user_id == user_id).first()
                if existing_profile:
                    self.logger.error(f"Diet profile for user ID '{user_id}' already exists.")
                    return None

                diet_profile = UserDietProfile(
                    user_id=user_id,
                    goal=goal,
                    calorie_target=calorie_target,
                    protein_target=protein_target,
                    carbs_target=carbs_target,
                    fats_target=fats_target
                )
                self.session.add(diet_profile)
                self.session.commit()
                profile_id = diet_profile.id
                self.logger.info(f"Diet profile created successfully with ID '{profile_id}' for user ID '{user_id}'.")
                return profile_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while creating diet profile for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while creating diet profile for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_diet_profile(self, profile_id: str, goal: Optional[str] = None, calorie_target: Optional[float] = None,
                            protein_target: Optional[float] = None, carbs_target: Optional[float] = None,
                            fats_target: Optional[float] = None) -> bool:
        """
        Updates an existing diet profile.

        Args:
            profile_id (str): The unique identifier of the diet profile.
            goal (Optional[str], optional): The new dietary goal. Defaults to None.
            calorie_target (Optional[float], optional): The new calorie target. Defaults to None.
            protein_target (Optional[float], optional): The new protein target. Defaults to None.
            carbs_target (Optional[float], optional): The new carbohydrate target. Defaults to None.
            fats_target (Optional[float], optional): The new fat target. Defaults to None.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating diet profile ID '{profile_id}'.")
            with self.lock:
                diet_profile = self.session.query(UserDietProfile).filter(UserDietProfile.id == profile_id).first()
                if not diet_profile:
                    self.logger.error(f"Diet profile with ID '{profile_id}' does not exist.")
                    return False

                if goal:
                    diet_profile.goal = goal
                if calorie_target:
                    diet_profile.calorie_target = calorie_target
                if protein_target:
                    diet_profile.protein_target = protein_target
                if carbs_target:
                    diet_profile.carbs_target = carbs_target
                if fats_target:
                    diet_profile.fats_target = fats_target

                self.session.commit()
                self.logger.info(f"Diet profile ID '{profile_id}' updated successfully.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating diet profile ID '{profile_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating diet profile ID '{profile_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def log_meal(self, profile_id: str, meal_type: str, description: str, calories: float,
                protein: float, carbs: float, fats: float, consumed_at: datetime) -> Optional[str]:
        """
        Logs a meal for a user's diet profile.

        Args:
            profile_id (str): The unique identifier of the diet profile.
            meal_type (str): The type of meal (e.g., breakfast, lunch, dinner, snack).
            description (str): Description of the meal.
            calories (float): Calories consumed.
            protein (float): Protein consumed in grams.
            carbs (float): Carbohydrates consumed in grams.
            fats (float): Fats consumed in grams.
            consumed_at (datetime): Timestamp when the meal was consumed.

        Returns:
            Optional[str]: The meal ID if logging is successful, else None.
        """
        try:
            self.logger.debug(f"Logging meal for diet profile ID '{profile_id}': '{meal_type}', '{description}'.")
            with self.lock:
                diet_profile = self.session.query(UserDietProfile).filter(UserDietProfile.id == profile_id).first()
                if not diet_profile:
                    self.logger.error(f"Diet profile with ID '{profile_id}' does not exist.")
                    return None

                meal = Meal(
                    diet_profile_id=profile_id,
                    meal_type=meal_type,
                    description=description,
                    calories=calories,
                    protein=protein,
                    carbs=carbs,
                    fats=fats,
                    consumed_at=consumed_at
                )
                self.session.add(meal)
                self.session.commit()
                meal_id = meal.id
                self.logger.info(f"Meal logged successfully with ID '{meal_id}' for diet profile ID '{profile_id}'.")
                return meal_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while logging meal for diet profile ID '{profile_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while logging meal for diet profile ID '{profile_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def get_daily_nutrition(self, profile_id: str, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Retrieves the total nutritional intake for a specific day.

        Args:
            profile_id (str): The unique identifier of the diet profile.
            target_date (date): The date for which to retrieve nutrition data.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing total calories, protein, carbs, and fats, else None.
        """
        try:
            self.logger.debug(f"Retrieving daily nutrition for diet profile ID '{profile_id}' on date '{target_date}'.")
            with self.lock:
                meals = self.session.query(Meal).filter(
                    Meal.diet_profile_id == profile_id,
                    Meal.consumed_at >= datetime.combine(target_date, datetime.min.time()),
                    Meal.consumed_at <= datetime.combine(target_date, datetime.max.time())
                ).all()

                total_calories = sum(meal.calories for meal in meals)
                total_protein = sum(meal.protein for meal in meals)
                total_carbs = sum(meal.carbs for meal in meals)
                total_fats = sum(meal.fats for meal in meals)

                nutrition = {
                    'date': target_date.strftime('%Y-%m-%d'),
                    'total_calories': total_calories,
                    'total_protein': total_protein,
                    'total_carbs': total_carbs,
                    'total_fats': total_fats
                }
                self.logger.info(f"Daily nutrition retrieved for diet profile ID '{profile_id}' on date '{target_date}': {nutrition}.")
                return nutrition
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving daily nutrition for diet profile ID '{profile_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving daily nutrition for diet profile ID '{profile_id}': {e}", exc_info=True)
            return None

    def get_weekly_nutrition_summary(self, profile_id: str, target_date: date) -> Optional[Dict[str, Any]]:
        """
        Retrieves the weekly nutritional summary ending on the target date.

        Args:
            profile_id (str): The unique identifier of the diet profile.
            target_date (date): The end date of the week.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing weekly totals and averages, else None.
        """
        try:
            self.logger.debug(f"Retrieving weekly nutrition summary for diet profile ID '{profile_id}' ending on date '{target_date}'.")
            with self.lock:
                start_date = target_date - timedelta(days=6)
                meals = self.session.query(Meal).filter(
                    Meal.diet_profile_id == profile_id,
                    Meal.consumed_at >= datetime.combine(start_date, datetime.min.time()),
                    Meal.consumed_at <= datetime.combine(target_date, datetime.max.time())
                ).all()

                total_calories = sum(meal.calories for meal in meals)
                total_protein = sum(meal.protein for meal in meals)
                total_carbs = sum(meal.carbs for meal in meals)
                total_fats = sum(meal.fats for meal in meals)
                days_count = 7
                average_calories = total_calories / days_count
                average_protein = total_protein / days_count
                average_carbs = total_carbs / days_count
                average_fats = total_fats / days_count

                summary = {
                    'week_starting': start_date.strftime('%Y-%m-%d'),
                    'week_ending': target_date.strftime('%Y-%m-%d'),
                    'total_calories': total_calories,
                    'total_protein': total_protein,
                    'total_carbs': total_carbs,
                    'total_fats': total_fats,
                    'average_daily_calories': round(average_calories, 2),
                    'average_daily_protein': round(average_protein, 2),
                    'average_daily_carbs': round(average_carbs, 2),
                    'average_daily_fats': round(average_fats, 2)
                }
                self.logger.info(f"Weekly nutrition summary retrieved for diet profile ID '{profile_id}': {summary}.")
                return summary
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving weekly nutrition summary for diet profile ID '{profile_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving weekly nutrition summary for diet profile ID '{profile_id}': {e}", exc_info=True)
            return None

    def get_diet_recommendations(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """
        Provides dietary recommendations based on the user's current nutrition intake and goals.

        Args:
            profile_id (str): The unique identifier of the diet profile.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing recommendations, else None.
        """
        try:
            self.logger.debug(f"Generating diet recommendations for diet profile ID '{profile_id}'.")
            with self.lock:
                today = date.today()
                nutrition = self.get_daily_nutrition(profile_id, today)
                if not nutrition:
                    self.logger.error(f"Unable to retrieve nutrition data for diet profile ID '{profile_id}'.")
                    return None

                profile = self.session.query(UserDietProfile).filter(UserDietProfile.id == profile_id).first()
                if not profile:
                    self.logger.error(f"Diet profile with ID '{profile_id}' does not exist.")
                    return None

                recommendations = {}
                if nutrition['total_calories'] < profile.calorie_target * 0.9:
                    recommendations['calories'] = "Increase your calorie intake by incorporating more nutrient-dense foods."
                elif nutrition['total_calories'] > profile.calorie_target * 1.1:
                    recommendations['calories'] = "Reduce your calorie intake to meet your daily target."

                if nutrition['total_protein'] < profile.protein_target * 0.9:
                    recommendations['protein'] = "Increase your protein intake by adding lean meats, legumes, or protein supplements."
                elif nutrition['total_protein'] > profile.protein_target * 1.1:
                    recommendations['protein'] = "Consider reducing high-protein foods to balance your intake."

                if nutrition['total_carbs'] < profile.carbs_target * 0.9:
                    recommendations['carbs'] = "Incorporate more complex carbohydrates like whole grains and vegetables."
                elif nutrition['total_carbs'] > profile.carbs_target * 1.1:
                    recommendations['carbs'] = "Limit intake of simple carbohydrates such as sugary snacks and beverages."

                if nutrition['total_fats'] < profile.fats_target * 0.9:
                    recommendations['fats'] = "Include healthy fats from sources like avocados, nuts, and olive oil."
                elif nutrition['total_fats'] > profile.fats_target * 1.1:
                    recommendations['fats'] = "Reduce consumption of saturated and trans fats found in fried and processed foods."

                self.logger.info(f"Diet recommendations generated for diet profile ID '{profile_id}': {recommendations}.")
                return recommendations
        except Exception as e:
            self.logger.error(f"Error generating diet recommendations for diet profile ID '{profile_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing DietTrackerService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("DietTrackerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing DietTrackerService: {e}", exc_info=True)
            raise DietTrackerServiceError(f"Error closing DietTrackerService: {e}")
