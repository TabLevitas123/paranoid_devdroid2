# services/investment_advisor_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime, date
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

class InvestmentPortfolio(Base):
    __tablename__ = 'investment_portfolios'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    investments = relationship("Investment", back_populates="portfolio")
    user = relationship("User", back_populates="portfolios")

class Investment(Base):
    __tablename__ = 'investments'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(String, ForeignKey('investment_portfolios.id'), nullable=False)
    asset_type = Column(String, nullable=False)  # e.g., stocks, bonds, ETFs, cryptocurrencies
    asset_name = Column(String, nullable=False)
    quantity = Column(Float, nullable=False)
    purchase_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    investment_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    portfolio = relationship("InvestmentPortfolio", back_populates="investments")

class MarketData(Base):
    __tablename__ = 'market_data'

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_name = Column(String, unique=True, nullable=False)
    asset_type = Column(String, nullable=False)
    current_price = Column(Float, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserRiskProfile(Base):
    __tablename__ = 'user_risk_profiles'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    risk_level = Column(String, nullable=False)  # e.g., conservative, moderate, aggressive
    investment_goals = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="risk_profile")

class InvestmentAdvisorServiceError(Exception):
    """Custom exception for InvestmentAdvisorService-related errors."""
    pass

class InvestmentAdvisorService:
    """
    Provides investment advisory functionalities, including portfolio management, asset allocation,
    risk assessment, real-time market data integration, performance tracking, and personalized
    investment recommendations. Utilizes SQLAlchemy for database interactions and integrates
    with third-party financial APIs for market data and analytics. Ensures secure handling of
    user data and compliance with financial regulations.
    """

    def __init__(self):
        """
        Initializes the InvestmentAdvisorService with necessary configurations and authentication.
        """
        self.logger = setup_logging('InvestmentAdvisorService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.market_data_api_url = self.config_loader.get('MARKET_DATA_API_URL', 'https://api.marketdata.com')
        self.market_data_api_key_encrypted = self.config_loader.get('MARKET_DATA_API_KEY')
        self.market_data_api_key = self.encryption_manager.decrypt_data(self.market_data_api_key_encrypted).decode('utf-8')
        self.session_requests = requests.Session()
        self.logger.info("InvestmentAdvisorService initialized successfully.")

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
                raise InvestmentAdvisorServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise InvestmentAdvisorServiceError(f"Error initializing database: {e}")

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
            raise InvestmentAdvisorServiceError(f"Unsupported database type '{db_type}'.")

    def create_portfolio(self, user_id: str, name: str) -> Optional[str]:
        """
        Creates a new investment portfolio for a user.

        Args:
            user_id (str): The unique identifier of the user.
            name (str): The name of the portfolio.

        Returns:
            Optional[str]: The portfolio ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"Creating portfolio '{name}' for user ID '{user_id}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                portfolio = InvestmentPortfolio(
                    user_id=user_id,
                    name=name
                )
                self.session.add(portfolio)
                self.session.commit()
                portfolio_id = portfolio.id
                self.logger.info(f"Portfolio '{name}' created successfully with ID '{portfolio_id}' for user ID '{user_id}'.")
                return portfolio_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while creating portfolio '{name}' for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while creating portfolio '{name}' for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def add_investment(self, portfolio_id: str, asset_type: str, asset_name: str, quantity: float,
                      purchase_price: float, investment_date: Optional[datetime] = None) -> Optional[str]:
        """
        Adds a new investment to a portfolio.

        Args:
            portfolio_id (str): The unique identifier of the portfolio.
            asset_type (str): The type of asset (e.g., stocks, bonds, ETFs, cryptocurrencies).
            asset_name (str): The name of the asset.
            quantity (float): The quantity of the asset.
            purchase_price (float): The price at which the asset was purchased.
            investment_date (Optional[datetime], optional): The date of investment. Defaults to current datetime.

        Returns:
            Optional[str]: The investment ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding investment '{asset_name}' to portfolio ID '{portfolio_id}'.")
            with self.lock:
                portfolio = self.session.query(InvestmentPortfolio).filter(InvestmentPortfolio.id == portfolio_id).first()
                if not portfolio:
                    self.logger.error(f"Portfolio with ID '{portfolio_id}' does not exist.")
                    return None

                # Fetch current price from MarketData or external API
                market_data = self.session.query(MarketData).filter(MarketData.asset_name.ilike(asset_name)).first()
                if not market_data:
                    current_price = self._fetch_current_price(asset_type, asset_name)
                    if current_price is None:
                        self.logger.error(f"Unable to fetch current price for asset '{asset_name}'.")
                        return None
                    market_data = MarketData(
                        asset_name=asset_name,
                        asset_type=asset_type,
                        current_price=current_price
                    )
                    self.session.add(market_data)
                    self.session.commit()
                else:
                    current_price = market_data.current_price

                investment = Investment(
                    portfolio_id=portfolio_id,
                    asset_type=asset_type,
                    asset_name=asset_name,
                    quantity=quantity,
                    purchase_price=purchase_price,
                    current_price=current_price,
                    investment_date=investment_date or datetime.utcnow()
                )
                self.session.add(investment)
                self.session.commit()
                investment_id = investment.id
                self.logger.info(f"Investment '{asset_name}' added successfully with ID '{investment_id}' to portfolio ID '{portfolio_id}'.")
                return investment_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while adding investment '{asset_name}' to portfolio ID '{portfolio_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while adding investment '{asset_name}' to portfolio ID '{portfolio_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def _fetch_current_price(self, asset_type: str, asset_name: str) -> Optional[float]:
        """
        Fetches the current price of an asset from an external market data API.

        Args:
            asset_type (str): The type of asset.
            asset_name (str): The name of the asset.

        Returns:
            Optional[float]: The current price if successful, else None.
        """
        try:
            self.logger.debug(f"Fetching current price for asset '{asset_name}'.")
            headers = {
                'Authorization': f"Bearer {self.market_data_api_key}",
                'Content-Type': 'application/json'
            }
            params = {
                'asset_type': asset_type,
                'asset_name': asset_name
            }
            response = self.session_requests.get(f"{self.market_data_api_url}/price", headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                current_price = data.get('current_price')
                self.logger.debug(f"Current price for asset '{asset_name}' is '{current_price}'.")
                return current_price
            else:
                self.logger.error(f"Failed to fetch current price for asset '{asset_name}'. Status Code: {response.status_code}, Response: {response.text}")
                return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception while fetching current price for asset '{asset_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching current price for asset '{asset_name}': {e}", exc_info=True)
            return None

    def update_market_data(self, asset_name: str) -> bool:
        """
        Updates the market data for a specific asset.

        Args:
            asset_name (str): The name of the asset.

        Returns:
            bool: True if the update is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Updating market data for asset '{asset_name}'.")
            with self.lock:
                market_data = self.session.query(MarketData).filter(MarketData.asset_name.ilike(asset_name)).first()
                if not market_data:
                    self.logger.error(f"Market data for asset '{asset_name}' does not exist.")
                    return False

                current_price = self._fetch_current_price(market_data.asset_type, asset_name)
                if current_price is None:
                    self.logger.error(f"Unable to fetch current price for asset '{asset_name}'.")
                    return False

                market_data.current_price = current_price
                market_data.last_updated = datetime.utcnow()
                self.session.commit()
                self.logger.info(f"Market data for asset '{asset_name}' updated successfully to '{current_price}'.")
                return True
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while updating market data for asset '{asset_name}': {e}", exc_info=True)
            self.session.rollback()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error while updating market data for asset '{asset_name}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def get_portfolio_performance(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the performance metrics of a user's investment portfolio.

        Args:
            portfolio_id (str): The unique identifier of the portfolio.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing performance metrics if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving performance metrics for portfolio ID '{portfolio_id}'.")
            with self.lock:
                portfolio = self.session.query(InvestmentPortfolio).filter(InvestmentPortfolio.id == portfolio_id).first()
                if not portfolio:
                    self.logger.error(f"Portfolio with ID '{portfolio_id}' does not exist.")
                    return None

                total_invested = sum(inv.quantity * inv.purchase_price for inv in portfolio.investments)
                current_value = sum(inv.quantity * inv.current_price for inv in portfolio.investments)
                profit_loss = current_value - total_invested
                roi = (profit_loss / total_invested) * 100 if total_invested > 0 else 0.0

                performance = {
                    'portfolio_id': portfolio_id,
                    'total_invested': round(total_invested, 2),
                    'current_value': round(current_value, 2),
                    'profit_loss': round(profit_loss, 2),
                    'roi_percentage': round(roi, 2)
                }
                self.logger.info(f"Performance metrics retrieved for portfolio ID '{portfolio_id}': {performance}.")
                return performance
        except Exception as e:
            self.logger.error(f"Error retrieving performance metrics for portfolio ID '{portfolio_id}': {e}", exc_info=True)
            return None

    def assess_risk_profile(self, user_id: str, risk_level: str, investment_goals: Optional[str] = None) -> Optional[str]:
        """
        Assesses and sets the risk profile for a user.

        Args:
            user_id (str): The unique identifier of the user.
            risk_level (str): The risk level ('conservative', 'moderate', 'aggressive').
            investment_goals (Optional[str], optional): The user's investment goals. Defaults to None.

        Returns:
            Optional[str]: The risk profile ID if assessment is successful, else None.
        """
        try:
            self.logger.debug(f"Assessing risk profile for user ID '{user_id}' with risk level '{risk_level}'.")
            if risk_level not in ['conservative', 'moderate', 'aggressive']:
                self.logger.error("Invalid risk level. Must be 'conservative', 'moderate', or 'aggressive'.")
                return None

            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                existing_profile = self.session.query(UserRiskProfile).filter(UserRiskProfile.user_id == user_id).first()
                if existing_profile:
                    existing_profile.risk_level = risk_level
                    existing_profile.investment_goals = investment_goals
                    existing_profile.updated_at = datetime.utcnow()
                    self.session.commit()
                    self.logger.info(f"Risk profile updated successfully for user ID '{user_id}'.")
                    return existing_profile.id

                risk_profile = UserRiskProfile(
                    user_id=user_id,
                    risk_level=risk_level,
                    investment_goals=investment_goals
                )
                self.session.add(risk_profile)
                self.session.commit()
                risk_profile_id = risk_profile.id
                self.logger.info(f"Risk profile assessed and created successfully with ID '{risk_profile_id}' for user ID '{user_id}'.")
                return risk_profile_id
        except SQLAlchemyError as e:
            self.logger.error(f"Database error while assessing risk profile for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while assessing risk profile for user ID '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def provide_investment_recommendations(self, user_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Provides personalized investment recommendations based on the user's risk profile and market data.

        Args:
            user_id (str): The unique identifier of the user.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of investment recommendations if successful, else None.
        """
        try:
            self.logger.debug(f"Providing investment recommendations for user ID '{user_id}'.")
            with self.lock:
                risk_profile = self.session.query(UserRiskProfile).filter(UserRiskProfile.user_id == user_id).first()
                if not risk_profile:
                    self.logger.error(f"Risk profile for user ID '{user_id}' does not exist.")
                    return None

                # Define asset allocation based on risk level
                if risk_profile.risk_level == 'conservative':
                    allocation = {'bonds': 70, 'stocks': 25, 'cash': 5}
                elif risk_profile.risk_level == 'moderate':
                    allocation = {'stocks': 50, 'bonds': 40, 'cash': 10}
                elif risk_profile.risk_level == 'aggressive':
                    allocation = {'stocks': 80, 'bonds': 15, 'cash': 5}
                else:
                    self.logger.error(f"Unknown risk level '{risk_profile.risk_level}' for user ID '{user_id}'.")
                    return None

                recommendations = []
                for asset_type, percentage in allocation.items():
                    assets = self.session.query(MarketData).filter(MarketData.asset_type == asset_type).order_by(MarketData.current_price.desc()).limit(5).all()
                    for asset in assets:
                        recommendation = {
                            'asset_type': asset.asset_type,
                            'asset_name': asset.asset_name,
                            'recommended_allocation_percentage': percentage,
                            'current_price': asset.current_price
                        }
                        recommendations.append(recommendation)

                self.logger.info(f"Investment recommendations provided for user ID '{user_id}': {recommendations}.")
                return recommendations
        except Exception as e:
            self.logger.error(f"Error providing investment recommendations for user ID '{user_id}': {e}", exc_info=True)
            return None

    def track_investment_performance(self, investment_id: str) -> Optional[Dict[str, Any]]:
        """
        Tracks the performance of a specific investment.

        Args:
            investment_id (str): The unique identifier of the investment.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing performance metrics if successful, else None.
        """
        try:
            self.logger.debug(f"Tracking performance for investment ID '{investment_id}'.")
            with self.lock:
                investment = self.session.query(Investment).filter(Investment.id == investment_id).first()
                if not investment:
                    self.logger.error(f"Investment with ID '{investment_id}' does not exist.")
                    return None

                profit_loss = (investment.current_price - investment.purchase_price) * investment.quantity
                roi = ((investment.current_price - investment.purchase_price) / investment.purchase_price) * 100 if investment.purchase_price > 0 else 0.0

                performance = {
                    'investment_id': investment_id,
                    'asset_type': investment.asset_type,
                    'asset_name': investment.asset_name,
                    'quantity': investment.quantity,
                    'purchase_price': investment.purchase_price,
                    'current_price': investment.current_price,
                    'profit_loss': round(profit_loss, 2),
                    'roi_percentage': round(roi, 2)
                }
                self.logger.info(f"Performance tracked for investment ID '{investment_id}': {performance}.")
                return performance
        except Exception as e:
            self.logger.error(f"Error tracking performance for investment ID '{investment_id}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing InvestmentAdvisorService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            if self.session_requests:
                self.session_requests.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("InvestmentAdvisorService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing InvestmentAdvisorService: {e}", exc_info=True)
            raise InvestmentAdvisorServiceError(f"Error closing InvestmentAdvisorService: {e}")
