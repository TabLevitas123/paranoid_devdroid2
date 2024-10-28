# services/feedback_service.py

import base64
import io
import logging
import threading
from turtle import pd
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import uuid
import json
from matplotlib import pyplot as plt
import seaborn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import requests
from modules.services.performance_analytics_service import PerformanceReport
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class FeedbackEntry(Base):
    __tablename__ = 'feedback_entries'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    service_name = Column(String, nullable=False)  # e.g., ResourceMonitor, PerformanceAnalytics
    rating = Column(Float, nullable=False)  # 1.0 to 5.0
    comments = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    response = Column(Text, nullable=True)  # Response after processing
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", backref="feedback_entries")

class FeedbackServiceError(Exception):
    """Custom exception for FeedbackService-related errors."""
    pass

class FeedbackService:
    """
    Provides feedback management functionalities, including collecting user feedback on various services,
    analyzing feedback data, generating insights, and integrating with third-party survey and analytics tools.
    Utilizes SQLAlchemy for database interactions and ensures secure handling of feedback data and adherence
    to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the FeedbackService with necessary configurations and authentication.
        """
        self.logger = setup_logging('FeedbackService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.survey_api_url = self.config_loader.get('SURVEY_API_URL', 'https://api.surveyservice.com/feedback')
        self.survey_api_key_encrypted = self.config_loader.get('SURVEY_API_KEY')
        self.survey_api_key = self.encryption_manager.decrypt_data(self.survey_api_key_encrypted).decode('utf-8')
        self.analytics_api_url = self.config_loader.get('ANALYTICS_API_URL', 'https://api.analyticsservice.com/insights')
        self.analytics_api_key_encrypted = self.config_loader.get('ANALYTICS_API_KEY')
        self.analytics_api_key = self.encryption_manager.decrypt_data(self.analytics_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("FeedbackService initialized successfully.")

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
                raise FeedbackServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise FeedbackServiceError(f"Error initializing database: {e}")

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
            raise FeedbackServiceError(f"Unsupported database type '{db_type}'.")

    def collect_feedback(self, user_id: str, service_name: str, rating: float, comments: Optional[str] = None) -> Optional[str]:
        """
        Collects user feedback for a specific service.

        Args:
            user_id (str): The unique identifier of the user.
            service_name (str): The name of the service being reviewed.
            rating (float): The user's rating (1.0 to 5.0).
            comments (Optional[str], optional): Additional comments from the user. Defaults to None.

        Returns:
            Optional[str]: The feedback entry ID if collection is successful, else None.
        """
        try:
            self.logger.debug(f"Collecting feedback from user ID '{user_id}' for service '{service_name}' with rating '{rating}'.")
            if not (1.0 <= rating <= 5.0):
                self.logger.error("Rating must be between 1.0 and 5.0.")
                return None

            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                feedback = FeedbackEntry(
                    user_id=user_id,
                    service_name=service_name,
                    rating=rating,
                    comments=comments,
                    submitted_at=datetime.utcnow(),
                    processed=False,
                    response=None
                )
                self.session.add(feedback)
                self.session.commit()
                feedback_id = feedback.id
                self.logger.info(f"Feedback collected successfully with ID '{feedback_id}' from user ID '{user_id}' for service '{service_name}'.")

                # Optionally, send confirmation to user
                self._send_feedback_confirmation(user, feedback)

                return feedback_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while collecting feedback from user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while collecting feedback from user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _send_feedback_confirmation(self, user: 'User', feedback: 'FeedbackEntry'):
        """
        Sends a confirmation message to the user after feedback submission.

        Args:
            user (User): The User instance.
            feedback (FeedbackEntry): The FeedbackEntry instance.
        """
        try:
            self.logger.debug(f"Sending feedback confirmation to user '{user.email}'.")
            headers = {
                'Authorization': f"Bearer {self.survey_api_key}",
                'Content-Type': 'application/json'
            }
            payload = {
                'user_id': user.id,
                'email': user.email,
                'subject': "Thank you for your feedback!",
                'message': f"Dear {user.name},\n\nThank you for providing your feedback on {feedback.service_name}. We appreciate your input and are committed to improving our services.\n\nBest regards,\nSupport Team",
                'feedback_id': feedback.id,
                'submitted_at': feedback.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            response = self.session_requests.post(
                self.survey_api_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            if response.status_code != 200:
                self.logger.error(f"Failed to send feedback confirmation to '{user.email}'. Status Code: {response.status_code}, Response: {response.text}")
            else:
                self.logger.debug(f"Feedback confirmation sent successfully to '{user.email}'.")
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending feedback confirmation to '{user.email}': {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Unexpected error while sending feedback confirmation to '{user.email}': {e}", exc_info=True)

    def analyze_feedback(self, service_name: str, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Analyzes feedback data for a specific service within an optional date range.

        Args:
            service_name (str): The name of the service to analyze feedback for.
            start_date (Optional[datetime], optional): The start date for the analysis. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the analysis. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: The analysis results if successful, else None.
        """
        try:
            self.logger.debug(f"Analyzing feedback for service '{service_name}' from '{start_date}' to '{end_date}'.")
            with self.lock:
                query = self.session.query(FeedbackEntry).filter(FeedbackEntry.service_name == service_name)
                if start_date:
                    query = query.filter(FeedbackEntry.submitted_at >= start_date)
                if end_date:
                    query = query.filter(FeedbackEntry.submitted_at <= end_date)
                feedbacks = query.all()

                if not feedbacks:
                    self.logger.error(f"No feedback entries found for service '{service_name}' in the specified date range.")
                    return None

                # Convert feedback to DataFrame
                df = pd.DataFrame([{
                    'rating': feedback.rating,
                    'comments': feedback.comments
                } for feedback in feedbacks])

                # Calculate average rating
                average_rating = df['rating'].mean()

                # Sentiment analysis on comments (simple positive/negative based on keywords)
                def sentiment_analysis(comment: str) -> str:
                    positive_keywords = ['good', 'great', 'excellent', 'satisfied', 'happy', 'love']
                    negative_keywords = ['bad', 'poor', 'terrible', 'unsatisfied', 'sad', 'hate']
                    comment_lower = comment.lower() if comment else ''
                    pos = sum(word in comment_lower for word in positive_keywords)
                    neg = sum(word in comment_lower for word in negative_keywords)
                    if pos > neg:
                        return 'Positive'
                    elif neg > pos:
                        return 'Negative'
                    else:
                        return 'Neutral'

                df['sentiment'] = df['comments'].apply(sentiment_analysis)
                sentiment_counts = df['sentiment'].value_counts().to_dict()

                analysis_results = {
                    'service_name': service_name,
                    'average_rating': round(average_rating, 2),
                    'sentiment_distribution': sentiment_counts,
                    'total_feedbacks': len(feedbacks),
                    'start_date': start_date.strftime('%Y-%m-%d %H:%M:%S') if start_date else None,
                    'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S') if end_date else None
                }

                self.logger.info(f"Feedback analysis for service '{service_name}' completed successfully.")
                return analysis_results
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while analyzing feedback for service '{service_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while analyzing feedback for service '{service_name}': {e}", exc_info=True)
            return None

    def generate_feedback_report(self, service_name: str, start_date: Optional[datetime] = None,
                                 end_date: Optional[datetime] = None) -> Optional[str]:
        """
        Generates a detailed feedback report for a specific service.

        Args:
            service_name (str): The name of the service.
            start_date (Optional[datetime], optional): The start date for the report. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the report. Defaults to None.

        Returns:
            Optional[str]: The report ID if generation is successful, else None.
        """
        try:
            self.logger.debug(f"Generating feedback report for service '{service_name}' from '{start_date}' to '{end_date}'.")
            analysis = self.analyze_feedback(service_name, start_date, end_date)
            if not analysis:
                self.logger.error("Feedback analysis failed. Report generation aborted.")
                return None

            # Create a summary chart for sentiment distribution
            sentiments = analysis['sentiment_distribution']
            sentiments_labels = list(sentiments.keys())
            sentiments_values = list(sentiments.values())

            plt.figure(figsize=(8, 6))
            seaborn.barplot(x=sentiments_labels, y=sentiments_values, palette='viridis')
            plt.title(f"Sentiment Distribution for {service_name}")
            plt.xlabel("Sentiment")
            plt.ylabel("Number of Feedbacks")
            plt.tight_layout()

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png')
            plt.close()
            img_buffer.seek(0)
            chart_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

            # Compile report data
            report_data = {
                'service_name': service_name,
                'average_rating': analysis['average_rating'],
                'sentiment_distribution': analysis['sentiment_distribution'],
                'total_feedbacks': analysis['total_feedbacks'],
                'start_date': analysis['start_date'],
                'end_date': analysis['end_date']
            }

            # Save report to database
            report = PerformanceReport(
                report_name=f"Feedback Report for {service_name}",
                generated_at=datetime.utcnow(),
                report_data=json.dumps(report_data),
                chart_image=chart_base64
            )
            self.session.add(report)
            self.session.commit()
            report_id = report.id
            self.logger.info(f"Feedback report for service '{service_name}' generated successfully with ID '{report_id}'.")
            return report_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while generating feedback report for service '{service_name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while generating feedback report for service '{service_name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def send_report_via_email(self, report_id: str, user_email: str) -> bool:
        """
        Sends the feedback report to a user via email using an external analytics API.

        Args:
            report_id (str): The unique identifier of the feedback report.
            user_email (str): The email address of the user.

        Returns:
            bool: True if the report is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Sending feedback report ID '{report_id}' to user '{user_email}'.")
            with self.lock:
                report = self.session.query(PerformanceReport).filter(PerformanceReport.id == report_id).first()
                if not report:
                    self.logger.error(f"Feedback report with ID '{report_id}' does not exist.")
                    return False

                headers = {
                    'Authorization': f"Bearer {self.analytics_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'report_id': report.id,
                    'report_name': report.report_name,
                    'generated_at': report.generated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'report_data': json.loads(report.report_data),
                    'chart_image': report.chart_image,
                    'recipient_email': user_email
                }
                response = self.session_requests.post(
                    self.analytics_api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to send feedback report via email. Status Code: {response.status_code}, Response: {response.text}")
                    return False

                self.logger.info(f"Feedback report ID '{report_id}' sent successfully to '{user_email}'.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending feedback report ID '{report_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending feedback report ID '{report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while sending feedback report ID '{report_id}': {e}", exc_info=True)
            return False

    def get_user_feedback(self, user_id: str, service_name: Optional[str] = None,
                          start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves feedback entries submitted by a specific user with optional filters.

        Args:
            user_id (str): The unique identifier of the user.
            service_name (Optional[str], optional): The name of the service to filter feedback. Defaults to None.
            start_date (Optional[datetime], optional): The start date for filtering feedback. Defaults to None.
            end_date (Optional[datetime], optional): The end date for filtering feedback. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of feedback entries if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving feedback for user ID '{user_id}' with service '{service_name}', from '{start_date}' to '{end_date}'.")
            with self.lock:
                query = self.session.query(FeedbackEntry).filter(FeedbackEntry.user_id == user_id)
                if service_name:
                    query = query.filter(FeedbackEntry.service_name == service_name)
                if start_date:
                    query = query.filter(FeedbackEntry.submitted_at >= start_date)
                if end_date:
                    query = query.filter(FeedbackEntry.submitted_at <= end_date)
                feedbacks = query.order_by(FeedbackEntry.submitted_at.desc()).all()

                feedback_list = [
                    {
                        'feedback_id': feedback.id,
                        'service_name': feedback.service_name,
                        'rating': feedback.rating,
                        'comments': feedback.comments,
                        'submitted_at': feedback.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'processed': feedback.processed,
                        'response': feedback.response
                    } for feedback in feedbacks
                ]
                self.logger.info(f"Retrieved {len(feedback_list)} feedback entries for user ID '{user_id}'.")
                return feedback_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving feedback for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving feedback for user ID '{user_id}': {e}", exc_info=True)
            return None

    def analyze_feedback_data(self, service_name: Optional[str] = None,
                              start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Analyzes aggregated feedback data to generate insights.

        Args:
            service_name (Optional[str], optional): The name of the service to analyze feedback for. Defaults to None.
            start_date (Optional[datetime], optional): The start date for the analysis. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the analysis. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: The analysis insights if successful, else None.
        """
        try:
            self.logger.debug(f"Analyzing feedback data with service '{service_name}', from '{start_date}' to '{end_date}'.")
            with self.lock:
                query = self.session.query(FeedbackEntry)
                if service_name:
                    query = query.filter(FeedbackEntry.service_name == service_name)
                if start_date:
                    query = query.filter(FeedbackEntry.submitted_at >= start_date)
                if end_date:
                    query = query.filter(FeedbackEntry.submitted_at <= end_date)
                feedbacks = query.all()

                if not feedbacks:
                    self.logger.error("No feedback data available for analysis.")
                    return None

                # Convert feedback to DataFrame for analysis
                df = pd.DataFrame([{
                    'service_name': feedback.service_name,
                    'rating': feedback.rating,
                    'comments': feedback.comments
                } for feedback in feedbacks])

                # Calculate average ratings per service
                avg_ratings = df.groupby('service_name')['rating'].mean().to_dict()

                # Identify services with highest and lowest ratings
                highest_rated = max(avg_ratings.items(), key=lambda x: x[1])
                lowest_rated = min(avg_ratings.items(), key=lambda x: x[1])

                # Generate sentiment analysis (simple based on keywords)
                def sentiment_analysis(comment: str) -> str:
                    positive_keywords = ['good', 'great', 'excellent', 'satisfied', 'happy', 'love']
                    negative_keywords = ['bad', 'poor', 'terrible', 'unsatisfied', 'sad', 'hate']
                    comment_lower = comment.lower() if comment else ''
                    pos = sum(word in comment_lower for word in positive_keywords)
                    neg = sum(word in comment_lower for word in negative_keywords)
                    if pos > neg:
                        return 'Positive'
                    elif neg > pos:
                        return 'Negative'
                    else:
                        return 'Neutral'

                df['sentiment'] = df['comments'].apply(sentiment_analysis)
                sentiment_counts = df['sentiment'].value_counts().to_dict()

                analysis_insights = {
                    'average_ratings': {service: round(rating, 2) for service, rating in avg_ratings.items()},
                    'highest_rated_service': {'service_name': highest_rated[0], 'average_rating': round(highest_rated[1], 2)},
                    'lowest_rated_service': {'service_name': lowest_rated[0], 'average_rating': round(lowest_rated[1], 2)},
                    'sentiment_distribution': sentiment_counts,
                    'total_feedbacks': len(feedbacks),
                    'start_date': start_date.strftime('%Y-%m-%d %H:%M:%S') if start_date else None,
                    'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S') if end_date else None
                }

                self.logger.info("Feedback data analysis completed successfully.")
                return analysis_insights
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while analyzing feedback data: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while analyzing feedback data: {e}", exc_info=True)
            return None

    def generate_insights_report(self, service_name: Optional[str] = None,
                                 start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[str]:
        """
        Generates a detailed insights report based on feedback data analysis.

        Args:
            service_name (Optional[str], optional): The name of the service to generate insights for. Defaults to None.
            start_date (Optional[datetime], optional): The start date for the report data. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the report data. Defaults to None.

        Returns:
            Optional[str]: The report ID if generation is successful, else None.
        """
        try:
            self.logger.debug(f"Generating insights report for service '{service_name}' from '{start_date}' to '{end_date}'.")
            analysis = self.analyze_feedback_data(service_name, start_date, end_date)
            if not analysis:
                self.logger.error("Feedback data analysis failed. Insights report generation aborted.")
                return None

            # Create a summary chart for average ratings
            services = list(analysis['average_ratings'].keys())
            ratings = list(analysis['average_ratings'].values())

            plt.figure(figsize=(10, 6))
            seaborn.barplot(x=services, y=ratings, palette='coolwarm')
            plt.title("Average Ratings per Service")
            plt.xlabel("Service")
            plt.ylabel("Average Rating")
            plt.ylim(0, 5)
            plt.tight_layout()

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png')
            plt.close()
            img_buffer.seek(0)
            chart_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

            # Compile report data
            report_data = {
                'service_name': service_name,
                'average_ratings': analysis['average_ratings'],
                'highest_rated_service': analysis['highest_rated_service'],
                'lowest_rated_service': analysis['lowest_rated_service'],
                'sentiment_distribution': analysis['sentiment_distribution'],
                'total_feedbacks': analysis['total_feedbacks'],
                'start_date': analysis['start_date'],
                'end_date': analysis['end_date']
            }

            # Save report to database
            report = PerformanceReport(
                report_name=f"Insights Report{' for ' + service_name if service_name else ''}",
                generated_at=datetime.utcnow(),
                report_data=json.dumps(report_data),
                chart_image=chart_base64
            )
            self.session.add(report)
            self.session.commit()
            report_id = report.id
            self.logger.info(f"Insights report generated successfully with ID '{report_id}'.")
            return report_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while generating insights report: {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while generating insights report: {e}", exc_info=True)
            self.session.rollback()
            return None

    def send_insights_report_via_email(self, report_id: str, user_email: str) -> bool:
        """
        Sends the insights report to a user via email using an external analytics API.

        Args:
            report_id (str): The unique identifier of the insights report.
            user_email (str): The email address of the user.

        Returns:
            bool: True if the report is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Sending insights report ID '{report_id}' to user '{user_email}'.")
            with self.lock:
                report = self.session.query(PerformanceReport).filter(PerformanceReport.id == report_id).first()
                if not report:
                    self.logger.error(f"Insights report with ID '{report_id}' does not exist.")
                    return False

                headers = {
                    'Authorization': f"Bearer {self.analytics_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'report_id': report.id,
                    'report_name': report.report_name,
                    'generated_at': report.generated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'report_data': json.loads(report.report_data),
                    'chart_image': report.chart_image,
                    'recipient_email': user_email
                }
                response = self.session_requests.post(
                    self.analytics_api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to send insights report via email. Status Code: {response.status_code}, Response: {response.text}")
                    return False

                self.logger.info(f"Insights report ID '{report_id}' sent successfully to '{user_email}'.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending insights report ID '{report_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending insights report ID '{report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while sending insights report ID '{report_id}': {e}", exc_info=True)
            return False

    def process_feedback_entries(self):
        """
        Processes unprocessed feedback entries by analyzing and responding to them.
        """
        try:
            self.logger.debug("Processing unprocessed feedback entries.")
            with self.lock:
                feedbacks = self.session.query(FeedbackEntry).filter(FeedbackEntry.processed == False).all()
                for feedback in feedbacks:
                    # Example processing: Send acknowledgment or take action based on feedback
                    self.logger.debug(f"Processing feedback ID '{feedback.id}' from user ID '{feedback.user_id}'.")
                    response_message = f"Thank you for your feedback on {feedback.service_name}!"
                    feedback.response = response_message
                    feedback.processed = True
                    self.session.commit()
                    self.logger.info(f"Feedback ID '{feedback.id}' processed successfully.")
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while processing feedback entries: {e}", exc_info=True)
            self.session.rollback()
        except Exception as e:
            self.logger.error(f"Unexpected error while processing feedback entries: {e}", exc_info=True)
            self.session.rollback()

    def retrieve_feedback_statistics(self, service_name: Optional[str] = None,
                                    start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves aggregated feedback statistics for a specific service within an optional date range.

        Args:
            service_name (Optional[str], optional): The name of the service to retrieve statistics for. Defaults to None.
            start_date (Optional[datetime], optional): The start date for the statistics. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the statistics. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: The aggregated statistics if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving feedback statistics for service '{service_name}' from '{start_date}' to '{end_date}'.")
            with self.lock:
                query = self.session.query(FeedbackEntry)
                if service_name:
                    query = query.filter(FeedbackEntry.service_name == service_name)
                if start_date:
                    query = query.filter(FeedbackEntry.submitted_at >= start_date)
                if end_date:
                    query = query.filter(FeedbackEntry.submitted_at <= end_date)

                total_feedbacks = query.count()
                if total_feedbacks == 0:
                    self.logger.error("No feedback data available for the specified parameters.")
                    return None

                average_rating = query.with_entities(func.avg(FeedbackEntry.rating)).scalar()
                rating_distribution = dict(query.with_entities(FeedbackEntry.rating, func.count(FeedbackEntry.rating)).group_by(FeedbackEntry.rating).all())

                statistics = {
                    'service_name': service_name,
                    'total_feedbacks': total_feedbacks,
                    'average_rating': round(average_rating, 2) if average_rating else None,
                    'rating_distribution': rating_distribution,
                    'start_date': start_date.strftime('%Y-%m-%d %H:%M:%S') if start_date else None,
                    'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S') if end_date else None
                }

                self.logger.info(f"Feedback statistics for service '{service_name}' retrieved successfully.")
                return statistics
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving feedback statistics: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving feedback statistics: {e}", exc_info=True)
            return None

    def generate_statistics_report(self, service_name: Optional[str] = None,
                                   start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Optional[str]:
        """
        Generates a detailed statistics report based on feedback data.

        Args:
            service_name (Optional[str], optional): The name of the service to generate the report for. Defaults to None.
            start_date (Optional[datetime], optional): The start date for the report data. Defaults to None.
            end_date (Optional[datetime], optional): The end date for the report data. Defaults to None.

        Returns:
            Optional[str]: The report ID if generation is successful, else None.
        """
        try:
            self.logger.debug(f"Generating statistics report for service '{service_name}' from '{start_date}' to '{end_date}'.")
            statistics = self.retrieve_feedback_statistics(service_name, start_date, end_date)
            if not statistics:
                self.logger.error("Feedback statistics retrieval failed. Report generation aborted.")
                return None

            # Create a pie chart for rating distribution
            ratings = list(statistics['rating_distribution'].keys())
            counts = list(statistics['rating_distribution'].values())

            plt.figure(figsize=(8, 8))
            plt.pie(counts, labels=ratings, autopct='%1.1f%%', startangle=140, colors=seaborn.color_palette('pastel'))
            plt.title(f"Rating Distribution for {service_name}" if service_name else "Rating Distribution for All Services")
            plt.tight_layout()

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png')
            plt.close()
            img_buffer.seek(0)
            chart_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

            # Compile report data
            report_data = {
                'service_name': service_name,
                'total_feedbacks': statistics['total_feedbacks'],
                'average_rating': statistics['average_rating'],
                'rating_distribution': statistics['rating_distribution'],
                'start_date': statistics['start_date'],
                'end_date': statistics['end_date']
            }

            # Save report to database
            report = PerformanceReport(
                report_name=f"Statistics Report{' for ' + service_name if service_name else ''}",
                generated_at=datetime.utcnow(),
                report_data=json.dumps(report_data),
                chart_image=chart_base64
            )
            self.session.add(report)
            self.session.commit()
            report_id = report.id
            self.logger.info(f"Statistics report generated successfully with ID '{report_id}'.")
            return report_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while generating statistics report: {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while generating statistics report: {e}", exc_info=True)
            self.session.rollback()
            return None

    def send_statistics_report_via_email(self, report_id: str, user_email: str) -> bool:
        """
        Sends the statistics report to a user via email using an external analytics API.

        Args:
            report_id (str): The unique identifier of the statistics report.
            user_email (str): The email address of the user.

        Returns:
            bool: True if the report is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Sending statistics report ID '{report_id}' to user '{user_email}'.")
            with self.lock:
                report = self.session.query(PerformanceReport).filter(PerformanceReport.id == report_id).first()
                if not report:
                    self.logger.error(f"Statistics report with ID '{report_id}' does not exist.")
                    return False

                headers = {
                    'Authorization': f"Bearer {self.analytics_api_key}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'report_id': report.id,
                    'report_name': report.report_name,
                    'generated_at': report.generated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'report_data': json.loads(report.report_data),
                    'chart_image': report.chart_image,
                    'recipient_email': user_email
                }
                response = self.session_requests.post(
                    self.analytics_api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code != 200:
                    self.logger.error(f"Failed to send statistics report via email. Status Code: {response.status_code}, Response: {response.text}")
                    return False

                self.logger.info(f"Statistics report ID '{report_id}' sent successfully to '{user_email}'.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while sending statistics report ID '{report_id}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except requests.RequestException as e:
            self.logger.error(f"Request exception while sending statistics report ID '{report_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while sending statistics report ID '{report_id}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing FeedbackService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("FeedbackService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing FeedbackService: {e}", exc_info=True)
            raise FeedbackServiceError(f"Error closing FeedbackService: {e}")
