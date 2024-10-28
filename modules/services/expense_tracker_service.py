# services/expense_tracker_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, date, timedelta
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class ExpenseCategory(Base):
    __tablename__ = 'expense_categories'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expenses = relationship("Expense", back_populates="category")

class Expense(Base):
    __tablename__ = 'expenses'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    category_id = Column(String, ForeignKey('expense_categories.id'), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    expense_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category = relationship("ExpenseCategory", back_populates="expenses")
    user = relationship("User", back_populates="expenses")

class Budget(Base):
    __tablename__ = 'budgets'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    category_id = Column(String, ForeignKey('expense_categories.id'), nullable=True)  # Null for overall budget
    amount = Column(Float, nullable=False)
    period = Column(String, default='monthly')  # monthly, weekly, yearly
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category = relationship("ExpenseCategory")
    user = relationship("User", back_populates="budgets")

class ExpenseTrackerServiceError(Exception):
    """Custom exception for ExpenseTrackerService-related errors."""
    pass

class ExpenseTrackerService:
    """
    Provides expense tracking capabilities, including managing expense categories, logging expenses,
    setting budgets, generating reports, and analyzing spending patterns. Utilizes SQLAlchemy for
    database interactions and integrates with third-party APIs for currency conversion and financial
    analytics. Ensures secure handling of user data and adherence to privacy regulations.
    """

    def __init__(self):
        """
        Initializes the ExpenseTrackerService with necessary configurations and authentication.
        """
        self.logger = setup_logging('ExpenseTrackerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("ExpenseTrackerService initialized successfully.")

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
                raise ExpenseTrackerServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise ExpenseTrackerServiceError(f"Error initializing database: {e}")

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
            raise ExpenseTrackerServiceError(f"Unsupported database type '{db_type}'.")

    def create_expense_category(self, name: str) -> Optional[str]:
        """
        Creates a new expense category.

        Args:
            name (str): The name of the expense category.

        Returns:
            Optional[str]: The category ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"Creating expense category '{name}'.")
            with self.lock:
                existing_category = self.session.query(ExpenseCategory).filter(ExpenseCategory.name.ilike(name)).first()
                if existing_category:
                    self.logger.error(f"Expense category '{name}' already exists.")
                    return None

                category = ExpenseCategory(
                    name=name
                )
                self.session.add(category)
                self.session.commit()
                category_id = category.id
                self.logger.info(f"Expense category '{name}' created successfully with ID '{category_id}'.")
                return category_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while creating expense category '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while creating expense category '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def log_expense(self, user_id: str, category_id: str, amount: float, description: Optional[str] = None,
                   expense_date: Optional[datetime] = None) -> Optional[str]:
        """
        Logs a new expense for a user.

        Args:
            user_id (str): The unique identifier of the user.
            category_id (str): The unique identifier of the expense category.
            amount (float): The amount of the expense.
            description (Optional[str], optional): Description of the expense. Defaults to None.
            expense_date (Optional[datetime], optional): Date of the expense. Defaults to current datetime.

        Returns:
            Optional[str]: The expense ID if logging is successful, else None.
        """
        try:
            self.logger.debug(f"Logging expense for user ID '{user_id}' in category ID '{category_id}' amounting to '{amount}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                category = self.session.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
                if not category:
                    self.logger.error(f"Expense category with ID '{category_id}' does not exist.")
                    return None

                expense = Expense(
                    user_id=user_id,
                    category_id=category_id,
                    amount=amount,
                    description=description,
                    expense_date=expense_date or datetime.utcnow()
                )
                self.session.add(expense)
                self.session.commit()
                expense_id = expense.id
                self.logger.info(f"Expense logged successfully with ID '{expense_id}' for user ID '{user_id}'.")
                return expense_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while logging expense for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while logging expense for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def set_budget(self, user_id: str, amount: float, period: str = 'monthly', category_id: Optional[str] = None) -> Optional[str]:
        """
        Sets a budget for a user, either overall or for a specific category.

        Args:
            user_id (str): The unique identifier of the user.
            amount (float): The budget amount.
            period (str, optional): The budget period ('monthly', 'weekly', 'yearly'). Defaults to 'monthly'.
            category_id (Optional[str], optional): The unique identifier of the expense category. Defaults to None.

        Returns:
            Optional[str]: The budget ID if setting is successful, else None.
        """
        try:
            self.logger.debug(f"Setting budget for user ID '{user_id}' amount '{amount}' period '{period}' category ID '{category_id}'.")
            if period not in ['monthly', 'weekly', 'yearly']:
                self.logger.error("Invalid budget period. Must be 'monthly', 'weekly', or 'yearly'.")
                return None

            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                if category_id:
                    category = self.session.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
                    if not category:
                        self.logger.error(f"Expense category with ID '{category_id}' does not exist.")
                        return None
                else:
                    category = None

                existing_budget = self.session.query(Budget).filter(
                    Budget.user_id == user_id,
                    Budget.category_id == category_id,
                    Budget.period == period
                ).first()
                if existing_budget:
                    self.logger.error("Budget for the specified parameters already exists.")
                    return None

                budget = Budget(
                    user_id=user_id,
                    category_id=category_id,
                    amount=amount,
                    period=period
                )
                self.session.add(budget)
                self.session.commit()
                budget_id = budget.id
                self.logger.info(f"Budget set successfully with ID '{budget_id}' for user ID '{user_id}'.")
                return budget_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while setting budget for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while setting budget for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def get_expenses(self, user_id: str, start_date: Optional[date] = None, end_date: Optional[date] = None,
                    category_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of expenses for a user based on optional filters.

        Args:
            user_id (str): The unique identifier of the user.
            start_date (Optional[date], optional): The start date for filtering expenses. Defaults to None.
            end_date (Optional[date], optional): The end date for filtering expenses. Defaults to None.
            category_id (Optional[str], optional): The unique identifier of the expense category. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of expenses if retrieval is successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving expenses for user ID '{user_id}' with filters start_date='{start_date}', end_date='{end_date}', category_id='{category_id}'.")
            with self.lock:
                query = self.session.query(Expense).filter(Expense.user_id == user_id)
                if start_date:
                    query = query.filter(Expense.expense_date >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                    query = query.filter(Expense.expense_date <= datetime.combine(end_date, datetime.max.time()))
                if category_id:
                    query = query.filter(Expense.category_id == category_id)

                expenses = query.all()
                expense_list = [
                    {
                        'id': expense.id,
                        'category': expense.category.name,
                        'amount': expense.amount,
                        'description': expense.description,
                        'expense_date': expense.expense_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'created_at': expense.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': expense.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for expense in expenses
                ]
                self.logger.info(f"Retrieved {len(expense_list)} expenses for user ID '{user_id}'.")
                return expense_list
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while retrieving expenses for user ID '{user_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while retrieving expenses for user ID '{user_id}': {e}", exc_info=True)
            return None

    def generate_expense_report(self, user_id: str, start_date: date, end_date: date) -> Optional[Dict[str, Any]]:
        """
        Generates an expense report for a user within a specified date range.

        Args:
            user_id (str): The unique identifier of the user.
            start_date (date): The start date of the report.
            end_date (date): The end date of the report.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing report data if successful, else None.
        """
        try:
            self.logger.debug(f"Generating expense report for user ID '{user_id}' from '{start_date}' to '{end_date}'.")
            with self.lock:
                expenses = self.get_expenses(user_id, start_date, end_date)
                if expenses is None:
                    self.logger.error(f"Unable to retrieve expenses for user ID '{user_id}' for the specified date range.")
                    return None

                total_spent = sum(expense['amount'] for expense in expenses)
                category_spending = {}
                for expense in expenses:
                    category = expense['category']
                    category_spending[category] = category_spending.get(category, 0.0) + expense['amount']

                report = {
                    'user_id': user_id,
                    'report_period': f"{start_date} to {end_date}",
                    'total_spent': total_spent,
                    'category_spending': category_spending,
                    'number_of_expenses': len(expenses)
                }
                self.logger.info(f"Expense report generated for user ID '{user_id}': {report}.")
                return report
        except Exception as e:
            self.logger.error(f"Error generating expense report for user ID '{user_id}': {e}", exc_info=True)
            return None

    def analyze_spending_patterns(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Analyzes spending patterns for a user and provides insights.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing spending insights if successful, else None.
        """
        try:
            self.logger.debug(f"Analyzing spending patterns for user ID '{user_id}'.")
            with self.lock:
                today = date.today()
                start_date = today - timedelta(days=30)
                expenses = self.get_expenses(user_id, start_date, today)
                if expenses is None:
                    self.logger.error(f"Unable to retrieve expenses for user ID '{user_id}' for analysis.")
                    return None

                total_spent = sum(expense['amount'] for expense in expenses)
                average_daily_spent = total_spent / 30
                highest_spending_category = max(
                    (expense['category'] for expense in expenses),
                    key=lambda cat: sum(e['amount'] for e in expenses if e['category'] == cat),
                    default=None
                )
                lowest_spending_category = min(
                    (expense['category'] for expense in expenses),
                    key=lambda cat: sum(e['amount'] for e in expenses if e['category'] == cat),
                    default=None
                )

                insights = {
                    'total_spent_last_30_days': total_spent,
                    'average_daily_spent': round(average_daily_spent, 2),
                    'highest_spending_category': highest_spending_category,
                    'lowest_spending_category': lowest_spending_category
                }
                self.logger.info(f"Spending patterns analyzed for user ID '{user_id}': {insights}.")
                return insights
        except Exception as e:
            self.logger.error(f"Error analyzing spending patterns for user ID '{user_id}': {e}", exc_info=True)
            return None

    def get_budget_status(self, user_id: str, period: str = 'monthly') -> Optional[Dict[str, Any]]:
        """
        Retrieves the budget status for a user for a specified period.

        Args:
            user_id (str): The unique identifier of the user.
            period (str, optional): The budget period ('monthly', 'weekly', 'yearly'). Defaults to 'monthly'.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing budget status if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving budget status for user ID '{user_id}' for period '{period}'.")
            if period not in ['monthly', 'weekly', 'yearly']:
                self.logger.error("Invalid period specified. Must be 'monthly', 'weekly', or 'yearly'.")
                return None

            with self.lock:
                today = date.today()
                if period == 'monthly':
                    start_date = today.replace(day=1)
                elif period == 'weekly':
                    start_date = today - timedelta(days=today.weekday())
                elif period == 'yearly':
                    start_date = today.replace(month=1, day=1)

                budgets = self.session.query(Budget).filter(
                    Budget.user_id == user_id,
                    Budget.period == period
                ).all()

                budget_status = []
                for budget in budgets:
                    if budget.category_id:
                        category_name = budget.category.name
                    else:
                        category_name = 'Overall'

                    expenses = self.session.query(Expense).filter(
                        Expense.user_id == user_id,
                        Expense.expense_date >= datetime.combine(start_date, datetime.min.time()),
                        Expense.expense_date <= datetime.combine(today, datetime.max.time()),
                        Expense.category_id == budget.category_id
                    ).all()
                    total_spent = sum(expense.amount for expense in expenses)

                    status = {
                        'budget_id': budget.id,
                        'category': category_name,
                        'budget_amount': budget.amount,
                        'period': budget.period,
                        'total_spent': total_spent,
                        'remaining_budget': budget.amount - total_spent
                    }
                    budget_status.append(status)

                self.logger.info(f"Budget status retrieved for user ID '{user_id}' for period '{period}': {budget_status}.")
                return {
                    'user_id': user_id,
                    'period': period,
                    'budgets': budget_status
                }
        except Exception as e:
            self.logger.error(f"Error retrieving budget status for user ID '{user_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing ExpenseTrackerService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("ExpenseTrackerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing ExpenseTrackerService: {e}", exc_info=True)
            raise ExpenseTrackerServiceError(f"Error closing ExpenseTrackerService: {e}")
