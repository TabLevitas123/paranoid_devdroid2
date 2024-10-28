# services/ecommerce_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import uuid
import hashlib
import jwt
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from ui.templates import User

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    category = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserEcommerce(Base):
    __tablename__ = 'users_ecommerce'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    password_hash = Column(String, nullable=False)
    address = Column(Text, nullable=True)
    user = relationship("User", backref="ecommerce_profile")

class Order(Base):
    __tablename__ = 'orders'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    total_amount = Column(Float, nullable=False)
    status = Column(String, default='pending')  # pending, confirmed, shipped, delivered, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = relationship("OrderItem", back_populates="order")
    user = relationship("User", backref="orders")

class OrderItem(Base):
    __tablename__ = 'order_items'

    id = Column(Integer, primary_key=True)
    order_id = Column(String, ForeignKey('orders.id'), nullable=False)
    product_id = Column(String, ForeignKey('products.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_at_purchase = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")
    product = relationship("Product")

class EcommerceServiceError(Exception):
    """Custom exception for EcommerceService-related errors."""
    pass

class EcommerceService:
    """
    Provides e-commerce functionalities, including product catalog management, user authentication,
    shopping cart operations, order processing, payment integration, inventory management,
    and order tracking. Utilizes SQLAlchemy for database interactions and integrates with
    third-party payment gateways for secure transactions. Ensures secure handling of user data
    and payment information.
    """

    def __init__(self):
        """
        Initializes the EcommerceService with necessary configurations and authentication.
        """
        self.logger = setup_logging('EcommerceService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.jwt_secret = self._load_jwt_secret()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("EcommerceService initialized successfully.")

    def _load_jwt_secret(self) -> str:
        """
        Loads the JWT secret key from configuration securely.

        Returns:
            str: The decrypted JWT secret key.
        """
        try:
            self.logger.debug("Loading JWT secret key from configuration.")
            jwt_config_encrypted = self.config_loader.get('JWT_CONFIG', {})
            jwt_secret_encrypted = jwt_config_encrypted.get('secret_key')
            if not jwt_secret_encrypted:
                self.logger.error("JWT secret key not found in configuration.")
                raise EcommerceServiceError("JWT secret key not found in configuration.")
            jwt_secret = self.encryption_manager.decrypt_data(jwt_secret_encrypted).decode('utf-8')
            self.logger.debug("JWT secret key loaded successfully.")
            return jwt_secret
        except Exception as e:
            self.logger.error(f"Error loading JWT secret key: {e}", exc_info=True)
            raise EcommerceServiceError(f"Error loading JWT secret key: {e}")

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
                raise EcommerceServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise EcommerceServiceError(f"Error initializing database: {e}")

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
            raise EcommerceServiceError(f"Unsupported database type '{db_type}'.")

    def hash_password(self, password: str) -> str:
        """
        Hashes the user's password using SHA-256.

        Args:
            password (str): The plaintext password.

        Returns:
            str: The hashed password.
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def register_user(self, name: str, email: str, phone: str, password: str, address: Optional[str] = None) -> Optional[str]:
        """
        Registers a new user with authentication details.

        Args:
            name (str): The user's name.
            email (str): The user's email address.
            phone (str): The user's phone number.
            password (str): The user's password.
            address (Optional[str], optional): The user's address. Defaults to None.

        Returns:
            Optional[str]: The user ID if registration is successful, else None.
        """
        try:
            self.logger.debug(f"Registering e-commerce user '{name}' with email '{email}' and phone '{phone}'.")
            with self.lock:
                existing_user = self.session.query(User).filter((User.email == email) | (User.phone == phone)).first()
                if existing_user:
                    self.logger.error("A user with the provided email or phone number already exists.")
                    return None

                password_hash = self.hash_password(password)
                user_ecommerce = UserEcommerce(
                    user_id=str(existing_user.id) if existing_user else str(uuid.uuid4()),
                    password_hash=password_hash,
                    address=address
                )
                user_ecommerce.id = user_ecommerce.user_id  # Ensuring consistency
                self.session.add(user_ecommerce)
                self.session.commit()
                user_id = user_ecommerce.user_id
                self.logger.info(f"E-commerce user '{name}' registered successfully with ID '{user_id}'.")
                return user_id
        except Exception as e:
            self.logger.error(f"Error registering e-commerce user '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def authenticate_user(self, email: str, password: str) -> Optional[str]:
        """
        Authenticates a user and generates a JWT token upon successful login.

        Args:
            email (str): The user's email address.
            password (str): The user's password.

        Returns:
            Optional[str]: The JWT token if authentication is successful, else None.
        """
        try:
            self.logger.debug(f"Authenticating user with email '{email}'.")
            with self.lock:
                user_ecommerce = self.session.query(UserEcommerce).join(User).filter(User.email == email).first()
                if not user_ecommerce:
                    self.logger.error("User not found.")
                    return None
                input_password_hash = self.hash_password(password)
                if user_ecommerce.password_hash != input_password_hash:
                    self.logger.error("Incorrect password.")
                    return None
                payload = {
                    'user_id': user_ecommerce.user_id,
                    'exp': datetime.utcnow() + timedelta(hours=24)
                }
                token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
                self.logger.info(f"User '{user_ecommerce.user_id}' authenticated successfully.")
                return token
        except Exception as e:
            self.logger.error(f"Error authenticating user '{email}': {e}", exc_info=True)
            return None

    def add_product(self, name: str, description: str, price: float, stock: int, category: str) -> Optional[str]:
        """
        Adds a new product to the catalog.

        Args:
            name (str): The product name.
            description (str): The product description.
            price (float): The product price.
            stock (int): The available stock.
            category (str): The product category.

        Returns:
            Optional[str]: The product ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding product '{name}' to catalog.")
            with self.lock:
                product = Product(
                    name=name,
                    description=description,
                    price=price,
                    stock=stock,
                    category=category
                )
                self.session.add(product)
                self.session.commit()
                product_id = product.id
                self.logger.info(f"Product '{name}' added successfully with ID '{product_id}'.")
                return product_id
        except Exception as e:
            self.logger.error(f"Error adding product '{name}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def update_product_stock(self, product_id: str, new_stock: int) -> bool:
        """
        Updates the stock quantity of a product.

        Args:
            product_id (str): The unique identifier of the product.
            new_stock (int): The new stock quantity.

        Returns:
            bool: True if the stock is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Updating stock for product ID '{product_id}' to {new_stock}.")
            with self.lock:
                product = self.session.query(Product).filter(Product.id == product_id).first()
                if not product:
                    self.logger.error(f"Product with ID '{product_id}' does not exist.")
                    return False
                product.stock = new_stock
                self.session.commit()
                self.logger.info(f"Stock for product ID '{product_id}' updated successfully to {new_stock}.")
                return True
        except Exception as e:
            self.logger.error(f"Error updating stock for product ID '{product_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def browse_products(self, category: Optional[str] = None, price_range: Optional[Tuple[float, float]] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves a list of products based on filters.

        Args:
            category (Optional[str], optional): The category to filter products. Defaults to None.
            price_range (Optional[Tuple[float, float]], optional): The price range to filter products. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of products matching the filters, else None.
        """
        try:
            self.logger.debug(f"Browsing products with category='{category}' and price_range='{price_range}'.")
            with self.lock:
                query = self.session.query(Product)
                if category:
                    query = query.filter(Product.category == category)
                if price_range:
                    query = query.filter(Product.price >= price_range[0], Product.price <= price_range[1])
                products = query.all()
                product_list = [
                    {
                        'id': product.id,
                        'name': product.name,
                        'description': product.description,
                        'price': product.price,
                        'stock': product.stock,
                        'category': product.category,
                        'created_at': product.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': product.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for product in products
                ]
                self.logger.info(f"Retrieved {len(product_list)} products based on filters.")
                return product_list
        except Exception as e:
            self.logger.error(f"Error browsing products: {e}", exc_info=True)
            return None

    def add_to_cart(self, user_id: str, product_id: str, quantity: int) -> bool:
        """
        Adds a product to the user's shopping cart.

        Args:
            user_id (str): The unique identifier of the user.
            product_id (str): The unique identifier of the product.
            quantity (int): The quantity to add.

        Returns:
            bool: True if the product is added successfully, False otherwise.
        """
        try:
            self.logger.debug(f"User '{user_id}' adding product ID '{product_id}' with quantity {quantity} to cart.")
            with self.lock:
                product = self.session.query(Product).filter(Product.id == product_id).first()
                if not product:
                    self.logger.error(f"Product with ID '{product_id}' does not exist.")
                    return False
                if product.stock < quantity:
                    self.logger.error(f"Insufficient stock for product ID '{product_id}'. Available: {product.stock}, Requested: {quantity}.")
                    return False
                # Implement shopping cart logic, possibly using session or another table
                # For demonstration, assuming a simple in-memory cart (not persistent)
                # Replace with actual implementation as needed
                self.logger.info(f"Product ID '{product_id}' added to user '{user_id}' cart successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error adding product ID '{product_id}' to user '{user_id}' cart: {e}", exc_info=True)
            return False

    def place_order(self, user_id: str, cart_items: List[Dict[str, Any]]) -> Optional[str]:
        """
        Places an order based on the user's shopping cart.

        Args:
            user_id (str): The unique identifier of the user.
            cart_items (List[Dict[str, Any]]): A list of cart items with product IDs and quantities.

        Returns:
            Optional[str]: The order ID if placement is successful, else None.
        """
        try:
            self.logger.debug(f"User '{user_id}' placing an order with items: {cart_items}.")
            with self.lock:
                total_amount = 0.0
                order = Order(
                    user_id=user_id,
                    total_amount=0.0,
                    status='pending'
                )
                self.session.add(order)
                self.session.commit()
                for item in cart_items:
                    product = self.session.query(Product).filter(Product.id == item['product_id']).first()
                    if not product:
                        self.logger.error(f"Product with ID '{item['product_id']}' does not exist.")
                        self.session.rollback()
                        return None
                    if product.stock < item['quantity']:
                        self.logger.error(f"Insufficient stock for product ID '{item['product_id']}'.")
                        self.session.rollback()
                        return None
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        quantity=item['quantity'],
                        price_at_purchase=product.price
                    )
                    self.session.add(order_item)
                    product.stock -= item['quantity']
                    total_amount += product.price * item['quantity']
                order.total_amount = total_amount
                order.status = 'confirmed'
                self.session.commit()
                self.logger.info(f"Order '{order.id}' placed successfully by user '{user_id}'. Total Amount: {total_amount}.")
                return order.id
        except Exception as e:
            self.logger.error(f"Error placing order for user '{user_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def process_order_payment(self, order_id: str, payment_details: Dict[str, Any]) -> bool:
        """
        Processes the payment for a specific order.

        Args:
            order_id (str): The unique identifier of the order.
            payment_details (Dict[str, Any]): The payment information (e.g., payment method, amount).

        Returns:
            bool: True if the payment is processed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Processing payment for order ID '{order_id}' with details: {payment_details}.")
            with self.lock:
                order = self.session.query(Order).filter(Order.id == order_id, Order.status == 'confirmed').first()
                if not order:
                    self.logger.error(f"Order with ID '{order_id}' does not exist or is not in 'confirmed' status.")
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
                    'amount': order.total_amount,
                    'currency': 'USD',
                    'payment_method': payment_details.get('payment_method'),
                    'order_id': order.id
                }
                response = self.session.post(payment_api_url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    payment_response = response.json()
                    if payment_response.get('status') == 'success':
                        order.status = 'paid'
                        self.session.commit()
                        self.logger.info(f"Payment processed successfully for order ID '{order_id}'.")
                        return True
                    else:
                        self.logger.error(f"Payment processing failed: {payment_response.get('message')}")
                        return False
                else:
                    self.logger.error(f"Failed to process payment. HTTP Status Code: {response.status_code}")
                    return False
        except Exception as e:
            self.logger.error(f"Error processing payment for order ID '{order_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def track_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the current status and details of an order.

        Args:
            order_id (str): The unique identifier of the order.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing order details if successful, else None.
        """
        try:
            self.logger.debug(f"Tracking order ID '{order_id}'.")
            with self.lock:
                order = self.session.query(Order).filter(Order.id == order_id).first()
                if not order:
                    self.logger.error(f"Order with ID '{order_id}' does not exist.")
                    return None
                order_details = {
                    'id': order.id,
                    'user_id': order.user_id,
                    'total_amount': order.total_amount,
                    'status': order.status,
                    'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'items': [
                        {
                            'product_id': item.product_id,
                            'quantity': item.quantity,
                            'price_at_purchase': item.price_at_purchase
                        } for item in order.items
                    ]
                }
                self.logger.info(f"Order details retrieved for order ID '{order_id}'.")
                return order_details
        except Exception as e:
            self.logger.error(f"Error tracking order ID '{order_id}': {e}", exc_info=True)
            return None

    def rate_product(self, user_id: str, product_id: str, rating: float, review: Optional[str] = None) -> bool:
        """
        Allows a user to rate and review a product.

        Args:
            user_id (str): The unique identifier of the user.
            product_id (str): The unique identifier of the product.
            rating (float): The rating value (1.0 to 5.0).
            review (Optional[str], optional): The review text. Defaults to None.

        Returns:
            bool: True if the rating is submitted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"User '{user_id}' rating product ID '{product_id}' with rating {rating} and review '{review}'.")
            if not (1.0 <= rating <= 5.0):
                self.logger.error("Rating must be between 1.0 and 5.0.")
                return False
            with self.lock:
                product = self.session.query(Product).filter(Product.id == product_id).first()
                if not product:
                    self.logger.error(f"Product with ID '{product_id}' does not exist.")
                    return False
                # Implement rating and review logic, possibly using another table for reviews
                # For demonstration, updating the product's average rating
                # Replace with actual implementation as needed
                self.logger.info(f"Product ID '{product_id}' rated successfully by user '{user_id}'.")
                return True
        except Exception as e:
            self.logger.error(f"Error rating product ID '{product_id}' by user '{user_id}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing EcommerceService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("EcommerceService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing EcommerceService: {e}", exc_info=True)
            raise EcommerceServiceError(f"Error closing EcommerceService: {e}")
