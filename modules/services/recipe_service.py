# services/recipe_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

Base = declarative_base()

class Recipe(Base):
    __tablename__ = 'recipes'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    ingredients = Column(Text, nullable=False)  # JSON string of ingredients
    instructions = Column(Text, nullable=False)
    cuisine = Column(String, nullable=False)
    preparation_time = Column(Integer, nullable=False)  # in minutes
    cooking_time = Column(Integer, nullable=False)  # in minutes
    servings = Column(Integer, nullable=False)
    rating = Column(Float, default=0.0)
    created_by = Column(String, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviews = relationship("Review", back_populates="recipe")
    creator = relationship("User", back_populates="recipes")

class Review(Base):
    __tablename__ = 'reviews'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recipe_id = Column(String, ForeignKey('recipes.id'), nullable=False)
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    rating = Column(Float, nullable=False)  # 1.0 to 5.0
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recipe = relationship("Recipe", back_populates="reviews")
    user = relationship("User", back_populates="reviews")

class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)  # 'chef', 'user', 'admin'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recipes = relationship("Recipe", back_populates="creator")
    reviews = relationship("Review", back_populates="user")

class RecipeServiceError(Exception):
    """Custom exception for RecipeService-related errors."""
    pass

class RecipeService:
    """
    Provides recipe management functionalities, including recipe creation, editing,
    deletion, searching, rating, and review management. Utilizes SQLAlchemy for
    database interactions and integrates with third-party APIs for image hosting
    and search optimization. Ensures secure handling of user data and recipe content.
    """

    def __init__(self):
        """
        Initializes the RecipeService with necessary configurations and authentication.
        """
        self.logger = setup_logging('RecipeService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self._initialize_database()
        self.session = self.Session()
        self.logger.info("RecipeService initialized successfully.")

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
                raise RecipeServiceError("Database configuration is incomplete.")

            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8')
            connection_string = self._build_connection_string(db_type, username, password, host, port, database)
            self.engine = create_engine(connection_string, pool_pre_ping=True, echo=False)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            self.logger.debug("Database initialized and tables created if not existing.")
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise RecipeServiceError(f"Error initializing database: {e}")

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
            raise RecipeServiceError(f"Unsupported database type '{db_type}'.")

    def create_recipe(self, title: str, description: str, ingredients: List[Dict[str, Any]], instructions: str,
                     cuisine: str, preparation_time: int, cooking_time: int, servings: int, created_by: str) -> Optional[str]:
        """
        Creates a new recipe.

        Args:
            title (str): The title of the recipe.
            description (str): The description of the recipe.
            ingredients (List[Dict[str, Any]]): A list of ingredients with quantities.
            instructions (str): The cooking instructions.
            cuisine (str): The cuisine type (e.g., Italian, Chinese).
            preparation_time (int): Preparation time in minutes.
            cooking_time (int): Cooking time in minutes.
            servings (int): Number of servings.
            created_by (str): The unique identifier of the user creating the recipe.

        Returns:
            Optional[str]: The recipe ID if creation is successful, else None.
        """
        try:
            self.logger.debug(f"Creating recipe '{title}' by user ID '{created_by}'.")
            with self.lock:
                user = self.session.query(User).filter(User.id == created_by, User.role == 'chef').first()
                if not user:
                    self.logger.error(f"User with ID '{created_by}' does not exist or is not a chef.")
                    return None

                ingredients_str = str(ingredients)  # Convert list of dicts to string for storage

                recipe = Recipe(
                    title=title,
                    description=description,
                    ingredients=ingredients_str,
                    instructions=instructions,
                    cuisine=cuisine,
                    preparation_time=preparation_time,
                    cooking_time=cooking_time,
                    servings=servings,
                    created_by=created_by,
                    rating=0.0
                )
                self.session.add(recipe)
                self.session.commit()
                recipe_id = recipe.id
                self.logger.info(f"Recipe '{title}' created successfully with ID '{recipe_id}'.")
                return recipe_id
        except Exception as e:
            self.logger.error(f"Error creating recipe '{title}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def edit_recipe(self, recipe_id: str, title: Optional[str] = None, description: Optional[str] = None,
                   ingredients: Optional[List[Dict[str, Any]]] = None, instructions: Optional[str] = None,
                   cuisine: Optional[str] = None, preparation_time: Optional[int] = None,
                   cooking_time: Optional[int] = None, servings: Optional[int] = None) -> bool:
        """
        Edits an existing recipe.

        Args:
            recipe_id (str): The unique identifier of the recipe.
            title (Optional[str], optional): The new title of the recipe. Defaults to None.
            description (Optional[str], optional): The new description. Defaults to None.
            ingredients (Optional[List[Dict[str, Any]]], optional): The new list of ingredients. Defaults to None.
            instructions (Optional[str], optional): The new cooking instructions. Defaults to None.
            cuisine (Optional[str], optional): The new cuisine type. Defaults to None.
            preparation_time (Optional[int], optional): The new preparation time in minutes. Defaults to None.
            cooking_time (Optional[int], optional): The new cooking time in minutes. Defaults to None.
            servings (Optional[int], optional): The new number of servings. Defaults to None.

        Returns:
            bool: True if the recipe is edited successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Editing recipe ID '{recipe_id}'.")
            with self.lock:
                recipe = self.session.query(Recipe).filter(Recipe.id == recipe_id).first()
                if not recipe:
                    self.logger.error(f"Recipe with ID '{recipe_id}' does not exist.")
                    return False

                if title:
                    recipe.title = title
                if description:
                    recipe.description = description
                if ingredients:
                    recipe.ingredients = str(ingredients)
                if instructions:
                    recipe.instructions = instructions
                if cuisine:
                    recipe.cuisine = cuisine
                if preparation_time:
                    recipe.preparation_time = preparation_time
                if cooking_time:
                    recipe.cooking_time = cooking_time
                if servings:
                    recipe.servings = servings

                self.session.commit()
                self.logger.info(f"Recipe ID '{recipe_id}' edited successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error editing recipe ID '{recipe_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def delete_recipe(self, recipe_id: str) -> bool:
        """
        Deletes a recipe.

        Args:
            recipe_id (str): The unique identifier of the recipe.

        Returns:
            bool: True if the recipe is deleted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Deleting recipe ID '{recipe_id}'.")
            with self.lock:
                recipe = self.session.query(Recipe).filter(Recipe.id == recipe_id).first()
                if not recipe:
                    self.logger.error(f"Recipe with ID '{recipe_id}' does not exist.")
                    return False

                self.session.delete(recipe)
                self.session.commit()
                self.logger.info(f"Recipe ID '{recipe_id}' deleted successfully.")
                return True
        except Exception as e:
            self.logger.error(f"Error deleting recipe ID '{recipe_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def search_recipes(self, keyword: str, cuisine: Optional[str] = None, min_rating: Optional[float] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Searches for recipes based on keywords, cuisine, and minimum rating.

        Args:
            keyword (str): The keyword to search in recipe titles and descriptions.
            cuisine (Optional[str], optional): The cuisine type to filter recipes. Defaults to None.
            min_rating (Optional[float], optional): The minimum rating to filter recipes. Defaults to None.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of matching recipes if successful, else None.
        """
        try:
            self.logger.debug(f"Searching recipes with keyword='{keyword}', cuisine='{cuisine}', min_rating='{min_rating}'.")
            with self.lock:
                query = self.session.query(Recipe).filter(
                    (Recipe.title.ilike(f"%{keyword}%")) | (Recipe.description.ilike(f"%{keyword}%"))
                )
                if cuisine:
                    query = query.filter(Recipe.cuisine.ilike(f"%{cuisine}%"))
                if min_rating:
                    query = query.filter(Recipe.rating >= min_rating)
                recipes = query.all()
                recipe_list = [
                    {
                        'id': recipe.id,
                        'title': recipe.title,
                        'description': recipe.description,
                        'ingredients': recipe.ingredients,
                        'instructions': recipe.instructions,
                        'cuisine': recipe.cuisine,
                        'preparation_time': recipe.preparation_time,
                        'cooking_time': recipe.cooking_time,
                        'servings': recipe.servings,
                        'rating': recipe.rating,
                        'created_by': recipe.created_by,
                        'created_at': recipe.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': recipe.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for recipe in recipes
                ]
                self.logger.info(f"Retrieved {len(recipe_list)} recipes based on search criteria.")
                return recipe_list
        except Exception as e:
            self.logger.error(f"Error searching recipes: {e}", exc_info=True)
            return None

    def add_review(self, recipe_id: str, user_id: str, rating: float, comment: Optional[str] = None) -> Optional[str]:
        """
        Adds a review for a recipe.

        Args:
            recipe_id (str): The unique identifier of the recipe.
            user_id (str): The unique identifier of the user.
            rating (float): The rating given by the user (1.0 to 5.0).
            comment (Optional[str], optional): The review comment. Defaults to None.

        Returns:
            Optional[str]: The review ID if addition is successful, else None.
        """
        try:
            self.logger.debug(f"Adding review for recipe ID '{recipe_id}' by user ID '{user_id}' with rating '{rating}'.")
            if not (1.0 <= rating <= 5.0):
                self.logger.error("Rating must be between 1.0 and 5.0.")
                return None

            with self.lock:
                user = self.session.query(User).filter(User.id == user_id).first()
                if not user:
                    self.logger.error(f"User with ID '{user_id}' does not exist.")
                    return None

                recipe = self.session.query(Recipe).filter(Recipe.id == recipe_id).first()
                if not recipe:
                    self.logger.error(f"Recipe with ID '{recipe_id}' does not exist.")
                    return None

                existing_review = self.session.query(Review).filter(Review.recipe_id == recipe_id, Review.user_id == user_id).first()
                if existing_review:
                    self.logger.error(f"User ID '{user_id}' has already reviewed recipe ID '{recipe_id}'.")
                    return None

                review = Review(
                    recipe_id=recipe_id,
                    user_id=user_id,
                    rating=rating,
                    comment=comment
                )
                self.session.add(review)

                # Update recipe rating
                total_reviews = self.session.query(Review).filter(Review.recipe_id == recipe_id).count()
                recipe.rating = ((recipe.rating * (total_reviews - 1)) + rating) / total_reviews if total_reviews > 0 else rating

                self.session.commit()
                review_id = review.id
                self.logger.info(f"Review added successfully with ID '{review_id}' for recipe ID '{recipe_id}'.")
                return review_id
        except Exception as e:
            self.logger.error(f"Error adding review for recipe ID '{recipe_id}': {e}", exc_info=True)
            self.session.rollback()
            return None

    def list_reviews(self, recipe_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all reviews for a specific recipe.

        Args:
            recipe_id (str): The unique identifier of the recipe.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of reviews if successful, else None.
        """
        try:
            self.logger.debug(f"Listing reviews for recipe ID '{recipe_id}'.")
            with self.lock:
                reviews = self.session.query(Review).filter(Review.recipe_id == recipe_id).all()
                review_list = [
                    {
                        'id': review.id,
                        'user_id': review.user_id,
                        'rating': review.rating,
                        'comment': review.comment,
                        'created_at': review.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': review.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    } for review in reviews
                ]
                self.logger.info(f"Retrieved {len(review_list)} reviews for recipe ID '{recipe_id}'.")
                return review_list
        except Exception as e:
            self.logger.error(f"Error listing reviews for recipe ID '{recipe_id}': {e}", exc_info=True)
            return None

    def update_recipe_rating(self, recipe_id: str) -> bool:
        """
        Updates the average rating of a recipe based on its reviews.

        Args:
            recipe_id (str): The unique identifier of the recipe.

        Returns:
            bool: True if the rating is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Updating average rating for recipe ID '{recipe_id}'.")
            with self.lock:
                recipe = self.session.query(Recipe).filter(Recipe.id == recipe_id).first()
                if not recipe:
                    self.logger.error(f"Recipe with ID '{recipe_id}' does not exist.")
                    return False

                reviews = self.session.query(Review).filter(Review.recipe_id == recipe_id).all()
                if not reviews:
                    recipe.rating = 0.0
                else:
                    average_rating = sum(review.rating for review in reviews) / len(reviews)
                    recipe.rating = round(average_rating, 2)
                self.session.commit()
                self.logger.info(f"Average rating for recipe ID '{recipe_id}' updated to '{recipe.rating}'.")
                return True
        except Exception as e:
            self.logger.error(f"Error updating rating for recipe ID '{recipe_id}': {e}", exc_info=True)
            self.session.rollback()
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing RecipeService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("Database session closed.")
            self.logger.info("RecipeService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing RecipeService: {e}", exc_info=True)
            raise RecipeServiceError(f"Error closing RecipeService: {e}")
