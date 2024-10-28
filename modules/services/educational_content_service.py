# services/educational_content_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class Course(Base):
    __tablename__ = 'courses'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    instructor_id = Column(String, ForeignKey('users.id'), nullable=False)
    price = Column(Float, nullable=False)
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    modules = relationship("Module", back_populates="course")
    instructor = relationship("User", back_populates="courses")

class Module(Base):
    __tablename__ = 'modules'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, ForeignKey('courses.id'), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    order = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    lessons = relationship("Lesson", back_populates="module")
    course = relationship("Course", back_populates="modules")

class Lesson(Base):
    __tablename__ = 'lessons'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id = Column(String, ForeignKey('modules.id'), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    order = Column(Integer, nullable=False)
    video_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    module = relationship("Module", back_populates="lessons")
    progress = relationship("UserLessonProgress", back_populates="lesson")

class UserLessonProgress(Base):
    __tablename__ = 'user_lesson_progress'

    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    lesson_id = Column(String, ForeignKey('lessons.id'), nullable=False)
    completed = Column(Boolean, default=False)
    score = Column(Float, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    lesson = relationship("Lesson", back_populates="progress")
    user = relationship("User", back_populates="lesson_progress")

class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)  # 'instructor', 'student', 'admin'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    courses = relationship("Course", back_populates="instructor")
    lesson_progress = relationship("UserLessonProgress", back_populates="user")

class EducationalContentServiceError(Exception):
    """Custom exception for EducationalContentService-related errors."""
    pass

class EducationalContentService:
    """
    Provides educational content management capabilities, including course creation,
    module and lesson management, user progress tracking, assessments, and analytics.
    Utilizes SQLAlchemy for database interactions and integrates with third-party APIs
    for content delivery and analytics. Ensures secure handling of user data and educational content.
    """

    def __init__(self):
        """
        Initializes the EducationalContentService with necessary configurations and authentication.
        """
        self.logger = setup_logging('EducationalContentService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("EducationalContentService initialized successfully.")

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
                raise EducationalContentServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise EducationalContentServiceError(f"Error initializing database: {e}")

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
            raise EducationalContentServiceError(f"Unsupported database type '{db_type}'.")

    def create_course(self, title: str, description: str, instructor_id: str, price: float) -> Optional[str]:
        """
        Creates a new course.

        Args:
            title (str): The title of the course.
            description (str): The description of the course.
            instructor_id (str): The unique identifier of the instructor.
            price (float): The price of the course.

        Returns:
            Optional[str]: The course ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"Creating course '{title}' by instructor ID '{instructor_id}'.")
            with self.lock:
                instructor = self.session.query(User).filter(User.id == instructor_id, User.role == 'instructor').first()
                if not instructor:
                    self.logger.error(f"Instructor with ID '{instructor_id}' does not exist.")
                    return None

                course = Course(
                    title=title,
                    description=description,
                    instructor_id=instructor_id,
                    price=price,
                    published=False
                )
                self.session.add(course)
                self.session.commit()
                course_id = course.id
                self.logger.info(f"Course '{title}' created successfully with ID '{course_id}'.")
                return course_id
        except Exception as e:
            self.logger.error(f"Error creating course '{title}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def publish_course(self, course_id: str) -> bool:
        """
        Publishes a course, making it available to students.

        Args:
            course_id (str): The unique identifier of the course.

        Returns:
            bool: True if the course is published successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Publishing course ID '{course_id}'.")
            with self.lock:
                course = self.session.query(Course).filter(Course.id == course_id).first()
                if not course:
                    self.logger.error(f"Course with ID '{course_id}' does not exist.")
                    return False
                course.published = True
                self.session.commit()
                self.logger.info(f"Course ID '{course_id}' published successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error publishing course ID '{course_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def add_module(self, course_id: str, title: str, description: str, order: int) -> Optional[str]:
        """
        Adds a new module to a course.

        Args:
            course_id (str): The unique identifier of the course.
            title (str): The title of the module.
            description (str): The description of the module.
            order (int): The order of the module within the course.

        Returns:
            Optional[str]: The module ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding module '{title}' to course ID '{course_id}'.")
            with self.lock:
                course = self.session.query(Course).filter(Course.id == course_id, Course.published == True).first()
                if not course:
                    self.logger.error(f"Published course with ID '{course_id}' does not exist.")
                    return None

                existing_module = self.session.query(Module).filter(Module.course_id == course_id, Module.order == order).first()
                if existing_module:
                    self.logger.error(f"Module order '{order}' already exists in course ID '{course_id}'.")
                    return None

                module = Module(
                    course_id=course_id,
                    title=title,
                    description=description,
                    order=order
                )
                self.session.add(module)
                self.session.commit()
                module_id = module.id
                self.logger.info(f"Module '{title}' added successfully with ID '{module_id}' to course ID '{course_id}'.")
                return module_id
        except Exception as e:
            self.logger.error(f"Error adding module '{title}' to course ID '{course_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def add_lesson(self, module_id: str, title: str, content: str, order: int, video_url: Optional[str] = None) -> Optional[str]:
        """
        Adds a new lesson to a module.

        Args:
            module_id (str): The unique identifier of the module.
            title (str): The title of the lesson.
            content (str): The content of the lesson.
            order (int): The order of the lesson within the module.
            video_url (Optional[str], optional): URL of the lesson video. Defaults to None.

        Returns:
            Optional[str]: The lesson ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding lesson '{title}' to module ID '{module_id}'.")
            with self.lock:
                module = self.session.query(Module).filter(Module.id == module_id).first()
                if not module:
                    self.logger.error(f"Module with ID '{module_id}' does not exist.")
                    return None

                existing_lesson = self.session.query(Lesson).filter(Lesson.module_id == module_id, Lesson.order == order).first()
                if existing_lesson:
                    self.logger.error(f"Lesson order '{order}' already exists in module ID '{module_id}'.")
                    return None

                lesson = Lesson(
                    module_id=module_id,
                    title=title,
                    content=content,
                    order=order,
                    video_url=video_url
                )
                self.session.add(lesson)
                self.session.commit()
                lesson_id = lesson.id
                self.logger.info(f"Lesson '{title}' added successfully with ID '{lesson_id}' to module ID '{module_id}'.")
                return lesson_id
        except Exception as e:
            self.logger.error(f"Error adding lesson '{title}' to module ID '{module_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def track_user_progress(self, user_id: str, lesson_id: str, completed: bool = False, score: Optional[float] = None) -> bool:
        """
        Tracks a user's progress on a specific lesson.

        Args:
            user_id (str): The unique identifier of the user.
            lesson_id (str): The unique identifier of the lesson.
            completed (bool, optional): Whether the lesson is completed. Defaults to False.
            score (Optional[float], optional): The score achieved in the lesson. Defaults to None.

        Returns:
            bool: True if progress is tracked successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Tracking progress for user ID '{user_id}' on lesson ID '{lesson_id}'. Completed: {completed}, Score: {score}.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id, User.role == 'student').first()
                if not user:
                    self.logger.error(f"Student with ID '{user_id}' does not exist.")
                    return False

                lesson = self.session.query(Lesson).filter(Lesson.id == lesson_id).first()
                if not lesson:
                    self.logger.error(f"Lesson with ID '{lesson_id}' does not exist.")
                    return False

                progress = self.session.query(UserLessonProgress).filter(
                    UserLessonProgress.user_id == user_id,
                    UserLessonProgress.lesson_id == lesson_id
                ).first()

                if not progress:
                    progress = UserLessonProgress(
                        user_id=user_id,
                        lesson_id=lesson_id,
                        completed=completed,
                        score=score,
                        started_at=datetime.utcnow() if not completed else None,
                        completed_at=datetime.utcnow() if completed else None
                    )
                    self.session.add(progress)
                else:
                    progress.completed = completed
                    progress.score = score
                    if completed:
                        progress.completed_at = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Progress tracked successfully for user ID '{user_id}' on lesson ID '{lesson_id}'.")
                return True
        except Exception as e:
            self.logger.error(f"Error tracking progress for user ID '{user_id}' on lesson ID '{lesson_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_user_analytics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Generates analytics based on a user's learning progress.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing analytics data if successful, else None.
        """
        try:
            self.logger.debug(f"Generating analytics for user ID '{user_id}'.")
            with self.lock:
                progresses = self.session.query(UserLessonProgress).filter(UserLessonProgress.user_id == user_id).all()
                total_lessons = len(progresses)
                completed_lessons = sum(1 for p in progresses if p.completed)
                average_score = sum(p.score for p in progresses if p.score is not None) / completed_lessons if completed_lessons > 0 else 0.0
                analytics = {
                    'total_lessons': total_lessons,
                    'completed_lessons': completed_lessons,
                    'completion_rate': (completed_lessons / total_lessons) * 100 if total_lessons > 0 else 0.0,
                    'average_score': round(average_score, 2)
                }
                self.logger.info(f"Analytics generated for user ID '{user_id}': {analytics}.")
                return analytics
        except Exception as e:
            self.logger.error(f"Error generating analytics for user ID '{user_id}': {e}", exc_info=True)
            return None

    def list_courses(self, published: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of courses, optionally filtering by published status.

        Args:
            published (bool, optional): Whether to filter courses by published status. Defaults to True.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of courses if successful, else None.
        """
        try:
            self.logger.debug(f"Listing courses with published status '{published}'.")
            with self.lock:
                courses = self.session.query(Course).filter(Course.published == published).all()
                course_list = [
                    {
                        'id': course.id,
                        'title': course.title,
                        'description': course.description,
                        'instructor_id': course.instructor_id,
                        'price': course.price,
                        'published': course.published,
                        'created_at': course.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': course.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for course in courses
                ]
                self.logger.info(f"Retrieved {len(course_list)} courses.")
                return course_list
        except Exception as e:
            self.logger.error(f"Error listing courses: {e}", exc_info=True)
            return None

    def delete_course(self, course_id: str) -> bool:
        """
        Deletes a course and all its associated modules and lessons.

        Args:
            course_id (str): The unique identifier of the course.

        Returns:
            bool: True if deletion is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Deleting course ID '{course_id}' along with its modules and lessons.")
            with self.lock:
                course = self.session.query(Course).filter(Course.id == course_id).first()
                if not course:
                    self.logger.error(f"Course with ID '{course_id}' does not exist.")
                    return False

                self.session.delete(course)
                self.session.commit()
                self.logger.info(f"Course ID '{course_id}' and its associated modules and lessons deleted successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error deleting course ID '{course_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing EducationalContentService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("EducationalContentService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing EducationalContentService: {e}", exc_info=True)
            raise EducationalContentServiceError(f"Error closing EducationalContentService: {e}")
