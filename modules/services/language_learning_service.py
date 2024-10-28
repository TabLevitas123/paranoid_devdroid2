# services/language_learning_service.py

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

class UserLanguageProfile(Base):
    __tablename__ = 'user_language_profiles'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    native_language = Column(String, nullable=False)
    target_language = Column(String, nullable=False)
    proficiency_level = Column(String, default='Beginner')  # Beginner, Intermediate, Advanced
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="language_profiles")
    lessons = relationship("LessonProgress", back_populates="language_profile")

class Lesson(Base):
    __tablename__ = 'lessons'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    language = Column(String, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    difficulty = Column(String, default='Beginner')  # Beginner, Intermediate, Advanced
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    progress = relationship("LessonProgress", back_populates="lesson")

class LessonProgress(Base):
    __tablename__ = 'lesson_progress'

    id = Column(Integer, primary_key=True)
    language_profile_id = Column(String, ForeignKey('user_language_profiles.id'), nullable=False)
    lesson_id = Column(String, ForeignKey('lessons.id'), nullable=False)
    completed = Column(Boolean, default=False)
    score = Column(Float, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    language_profile = relationship("UserLanguageProfile", back_populates="lessons")
    lesson = relationship("Lesson", back_populates="progress")

class LanguageLearningServiceError(Exception):
    """Custom exception for LanguageLearningService-related errors."""
    pass

class LanguageLearningService:
    """
    Provides language learning functionalities, including course creation, lesson management,
    user progress tracking, assessments, and analytics. Utilizes SQLAlchemy for database
    interactions and integrates with third-party APIs for content delivery and analytics.
    Ensures secure handling of user data and educational content.
    """

    def __init__(self):
        """
        Initializes the LanguageLearningService with necessary configurations and authentication.
        """
        self.logger = setup_logging('LanguageLearningService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("LanguageLearningService initialized successfully.")

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
                raise LanguageLearningServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise LanguageLearningServiceError(f"Error initializing database: {e}")

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
            raise LanguageLearningServiceError(f"Unsupported database type '{db_type}'.")

    def create_language_profile(self, user_id: str, native_language: str, target_language: str, proficiency_level: str = 'Beginner') -> Optional[str]:
        """
        Creates a language learning profile for a user.

        Args:
            user_id (str): The unique identifier of the user.
            native_language (str): The user's native language.
            target_language (str): The language the user wants to learn.
            proficiency_level (str, optional): The starting proficiency level. Defaults to 'Beginner'.

        Returns:
            Optional[str]: The profile ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"Creating language profile for user ID '{user_id}'.")
            if proficiency_level not in ['Beginner', 'Intermediate', 'Advanced']:
                self.logger.error("Invalid proficiency level. Must be 'Beginner', 'Intermediate', or 'Advanced'.")
                return None

            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                existing_profile = self.session.query(UserLanguageProfile).filter(UserLanguageProfile.user_id == user_id, UserLanguageProfile.target_language == target_language).first()
                if existing_profile:
                    self.logger.error(f"Language profile for target language '{target_language}' already exists for user ID '{user_id}'.")
                    return None

                profile = UserLanguageProfile(
                    user_id=user_id,
                    native_language=native_language,
                    target_language=target_language,
                    proficiency_level=proficiency_level
                )
                self.session.add(profile)
                self.session.commit()
                profile_id = profile.id
                self.logger.info(f"Language profile created successfully with ID '{profile_id}' for user ID '{user_id}'.")
                return profile_id
        except Exception as e:
            self.logger.error(f"Error creating language profile for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def add_lesson(self, language: str, title: str, content: str, difficulty: str = 'Beginner') -> Optional[str]:
        """
        Adds a new lesson to the curriculum.

        Args:
            language (str): The language of the lesson.
            title (str): The title of the lesson.
            content (str): The content of the lesson.
            difficulty (str, optional): The difficulty level ('Beginner', 'Intermediate', 'Advanced'). Defaults to 'Beginner'.

        Returns:
            Optional[str]: The lesson ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding lesson '{title}' for language '{language}' with difficulty '{difficulty}'.")
            if difficulty not in ['Beginner', 'Intermediate', 'Advanced']:
                self.logger.error("Invalid difficulty level. Must be 'Beginner', 'Intermediate', or 'Advanced'.")
                return None

            with self.lock:
                lesson = Lesson(
                    language=language,
                    title=title,
                    content=content,
                    difficulty=difficulty
                )
                self.session.add(lesson)
                self.session.commit()
                lesson_id = lesson.id
                self.logger.info(f"Lesson '{title}' added successfully with ID '{lesson_id}'.")
                return lesson_id
        except Exception as e:
            self.logger.error(f"Error adding lesson '{title}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def assign_lesson_to_profile(self, profile_id: str, lesson_id: str) -> bool:
        """
        Assigns a lesson to a user's language learning profile.

        Args:
            profile_id (str): The unique identifier of the language profile.
            lesson_id (str): The unique identifier of the lesson.

        Returns:
            bool: True if assignment is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Assigning lesson ID '{lesson_id}' to language profile ID '{profile_id}'.")
            with self.lock:
                profile = self.session.query(UserLanguageProfile).filter(UserLanguageProfile.id == profile_id).first()
                if not profile:
                    self.logger.error(f"Language profile with ID '{profile_id}' does not exist.")
                    return False

                lesson = self.session.query(Lesson).filter(Lesson.id == lesson_id).first()
                if not lesson:
                    self.logger.error(f"Lesson with ID '{lesson_id}' does not exist.")
                    return False

                existing_progress = self.session.query(LessonProgress).filter(LessonProgress.language_profile_id == profile_id, LessonProgress.lesson_id == lesson_id).first()
                if existing_progress:
                    self.logger.error(f"Lesson ID '{lesson_id}' is already assigned to profile ID '{profile_id}'.")
                    return False

                lesson_progress = LessonProgress(
                    language_profile_id=profile_id,
                    lesson_id=lesson_id,
                    completed=False,
                    score=None
                )
                self.session.add(lesson_progress)
                self.session.commit()
                self.logger.info(f"Lesson ID '{lesson_id}' assigned to language profile ID '{profile_id}' successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error assigning lesson ID '{lesson_id}' to profile ID '{profile_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def track_progress(self, profile_id: str, lesson_id: str, score: Optional[float] = None) -> bool:
        """
        Updates the progress of a user on a specific lesson.

        Args:
            profile_id (str): The unique identifier of the language profile.
            lesson_id (str): The unique identifier of the lesson.
            score (Optional[float], optional): The score achieved in the lesson. Defaults to None.

        Returns:
            bool: True if progress is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Tracking progress for profile ID '{profile_id}' on lesson ID '{lesson_id}' with score '{score}'.")
            with self.lock:
                lesson_progress = self.session.query(LessonProgress).filter(
                    LessonProgress.language_profile_id == profile_id,
                    LessonProgress.lesson_id == lesson_id
                ).first()
                if not lesson_progress:
                    self.logger.error(f"Lesson ID '{lesson_id}' is not assigned to profile ID '{profile_id}'.")
                    return False

                lesson_progress.completed = True
                lesson_progress.score = score
                lesson_progress.completed_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Progress updated for profile ID '{profile_id}' on lesson ID '{lesson_id}'.")
                return True
        except Exception as e:
            self.logger.error(f"Error tracking progress for profile ID '{profile_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_user_progress(self, profile_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the progress of a user across all lessons in their language profile.

        Args:
            profile_id (str): The unique identifier of the language profile.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of lesson progress details if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving progress for language profile ID '{profile_id}'.")
            with self.lock:
                progresses = self.session.query(LessonProgress).filter(LessonProgress.language_profile_id == profile_id).all()
                progress_list = [
                    {
                        'lesson_id': progress.lesson_id,
                        'lesson_title': progress.lesson.title,
                        'completed': progress.completed,
                        'score': progress.score,
                        'started_at': progress.started_at.strftime('%Y-%m-%d %H:%M:%S') if progress.started_at else None,
                        'completed_at': progress.completed_at.strftime('%Y-%m-%d %H:%M:%S') if progress.completed_at else None
                    } for progress in progresses
                ]
                self.logger.info(f"Retrieved progress for language profile ID '{profile_id}'.")
                return progress_list
        except Exception as e:
            self.logger.error(f"Error retrieving progress for profile ID '{profile_id}': {e}", exc_info=True)
            return None

    def generate_analytics(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """
        Generates analytics based on a user's learning progress.

        Args:
            profile_id (str): The unique identifier of the language profile.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing analytics data if successful, else None.
        """
        try:
            self.logger.debug(f"Generating analytics for language profile ID '{profile_id}'.")
            with self.lock:
                progresses = self.session.query(LessonProgress).filter(LessonProgress.language_profile_id == profile_id).all()
                total_lessons = len(progresses)
                completed_lessons = sum(1 for p in progresses if p.completed)
                average_score = sum(p.score for p in progresses if p.score is not None) / completed_lessons if completed_lessons > 0 else 0.0
                analytics = {
                    'total_lessons': total_lessons,
                    'completed_lessons': completed_lessons,
                    'completion_rate': (completed_lessons / total_lessons) * 100 if total_lessons > 0 else 0.0,
                    'average_score': round(average_score, 2)
                }
                self.logger.info(f"Analytics generated for language profile ID '{profile_id}': {analytics}.")
                return analytics
        except Exception as e:
            self.logger.error(f"Error generating analytics for profile ID '{profile_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing LanguageLearningService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("LanguageLearningService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing LanguageLearningService: {e}", exc_info=True)
            raise LanguageLearningServiceError(f"Error closing LanguageLearningService: {e}")
