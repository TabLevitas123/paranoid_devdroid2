# models/user_behavior_model.py

import logging
from typing import Any, Dict, Optional
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score

from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from databases.vector_db import VectorDatabase, VectorDatabaseError
from shared_memory.shared_data_structures import SharedMemoryManager
from databases.time_series_db import TimeSeriesDatabase


class UserBehaviorModelError(Exception):
    """Custom exception for UserBehaviorModel-related errors."""
    pass


class UserBehaviorModel:
    """
    Manages the user behavior predictive model.
    Integrates with VectorDatabase and SharedMemoryManager to support RAG in near-real-time.
    """

    def __init__(self):
        """
        Initializes the UserBehaviorModel with necessary configurations, authentication, and integrations.
        """
        # Setup logging
        self.logger = setup_logging('UserBehaviorModel')

        # Load configurations
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()

        # Initialize integrations
        try:
            self.vector_db = VectorDatabase()
            self.shared_memory = SharedMemoryManager(name='llm_shared_memory', size=1024*1024*200)  # 200 MB
            self.time_series_db = TimeSeriesDatabase()
            self.logger.info("Integrated with VectorDatabase, SharedMemoryManager, and TimeSeriesDatabase successfully.")
        except Exception as e:
            self.logger.error(f"Failed to integrate with other systems: {e}", exc_info=True)
            raise UserBehaviorModelError(f"Failed to integrate with other systems: {e}")

        # Initialize model attributes
        self.model = RandomForestClassifier()
        self.model_path = self.config_loader.get('USER_BEHAVIOR_MODEL_PATH', 'models/user_behavior_model.pkl')
        self.logger.info("Initialized UserBehaviorModel.")

    def train(self, data: pd.DataFrame, target_column: str) -> bool:
        """
        Trains the user behavior model on the provided dataset.

        Args:
            data (pd.DataFrame): The dataset containing user behavior data.
            target_column (str): The name of the target column for prediction.

        Returns:
            bool: True if training is successful, False otherwise.
        """
        try:
            self.logger.info("Starting training of UserBehaviorModel.")

            if target_column not in data.columns:
                self.logger.error(f"Target column '{target_column}' not found in data.")
                return False

            X = data.drop(columns=[target_column])
            y = data[target_column]

            # Handle missing values
            X.fillna(method='ffill', inplace=True)
            y.fillna(method='ffill', inplace=True)

            # Encode categorical variables if any
            X = pd.get_dummies(X)

            # Split the data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
            self.logger.debug("Data split into training and testing sets.")

            # Train the model
            self.model.fit(X_train, y_train)
            self.logger.info("Model training completed.")

            # Evaluate the model
            predictions = self.model.predict(X_test)
            accuracy = accuracy_score(y_test, predictions)
            report = classification_report(y_test, predictions)
            self.logger.info(f"Model Accuracy: {accuracy:.4f}")
            self.logger.debug(f"Classification Report:\n{report}")

            # Log evaluation metrics
            self.time_series_db.log_event(
                event_type='user_behavior_model_evaluation',
                details={'accuracy': accuracy, 'classification_report': report}
            )

            # Save the trained model
            self.save_model()

            return True
        except Exception as e:
            self.logger.error(f"Failed to train UserBehaviorModel: {e}", exc_info=True)
            return False

    def predict(self, user_data: pd.DataFrame) -> Optional[np.ndarray]:
        """
        Predicts user behavior based on the provided user data.

        Args:
            user_data (pd.DataFrame): The user data for prediction.

        Returns:
            Optional[np.ndarray]: The prediction results if successful, else None.
        """
        try:
            self.logger.info("Starting prediction with UserBehaviorModel.")

            # Check if model is trained
            if not os.path.exists(self.model_path):
                self.logger.warning("Model file not found. Attempting to load the model.")
                if not self.load_model():
                    self.logger.error("Model not found and failed to load.")
                    return None

            # Preprocess the input data
            user_data.fillna(method='ffill', inplace=True)
            user_data = pd.get_dummies(user_data)

            # Align the input data with training data
            # Assuming the model was trained on specific features
            # Here, fetch feature names from the trained model
            expected_features = self.model.feature_names_in_
            missing_features = set(expected_features) - set(user_data.columns)
            for feature in missing_features:
                user_data[feature] = 0
            user_data = user_data[expected_features]
            self.logger.debug("Input data preprocessed and aligned with model features.")

            # Make predictions
            predictions = self.model.predict(user_data)
            self.logger.info("Prediction completed.")

            # Log the prediction event
            self.time_series_db.log_event(
                event_type='user_behavior_prediction',
                details={'input_data': user_data.to_dict(), 'predictions': predictions.tolist()}
            )

            # Cache the predictions in shared memory
            cache_key = f"user_behavior_predictions:{pd.util.hash_pandas_object(user_data).sum()}"
            self.shared_memory.cache_data(key=cache_key, value=predictions.tolist())
            self.logger.debug(f"Cached predictions in SharedMemoryManager with key '{cache_key}'.")

            return predictions
        except Exception as e:
            self.logger.error(f"Failed to make predictions with UserBehaviorModel: {e}", exc_info=True)
            return None

    def evaluate(self, data: pd.DataFrame, target_column: str) -> bool:
        """
        Evaluates the user behavior model on the provided dataset.

        Args:
            data (pd.DataFrame): The dataset containing user behavior data.
            target_column (str): The name of the target column for prediction.

        Returns:
            bool: True if evaluation is successful, False otherwise.
        """
        try:
            self.logger.info("Starting evaluation of UserBehaviorModel.")

            if target_column not in data.columns:
                self.logger.error(f"Target column '{target_column}' not found in data.")
                return False

            X = data.drop(columns=[target_column])
            y = data[target_column]

            # Handle missing values
            X.fillna(method='ffill', inplace=True)
            y.fillna(method='ffill', inplace=True)

            # Encode categorical variables if any
            X = pd.get_dummies(X)

            # Check if model is trained
            if not os.path.exists(self.model_path):
                self.logger.warning("Model file not found. Attempting to load the model.")
                if not self.load_model():
                    self.logger.error("Model not found and failed to load.")
                    return False

            # Ensure the input features match the model's expected features
            expected_features = self.model.feature_names_in_
            missing_features = set(expected_features) - set(X.columns)
            for feature in missing_features:
                X[feature] = 0
            X = X[expected_features]
            self.logger.debug("Input data preprocessed and aligned with model features.")

            # Make predictions
            predictions = self.model.predict(X)
            accuracy = accuracy_score(y, predictions)
            report = classification_report(y, predictions)
            self.logger.info(f"Model Accuracy: {accuracy:.4f}")
            self.logger.debug(f"Classification Report:\n{report}")

            # Log evaluation metrics
            self.time_series_db.log_event(
                event_type='user_behavior_model_evaluation',
                details={'accuracy': accuracy, 'classification_report': report}
            )

            return True
        except Exception as e:
            self.logger.error(f"Failed to evaluate UserBehaviorModel: {e}", exc_info=True)
            return False

    def save_model(self) -> bool:
        """
        Saves the trained model to disk.

        Returns:
            bool: True if saving is successful, False otherwise.
        """
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            self.logger.info(f"Model saved successfully at '{self.model_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save UserBehaviorModel: {e}", exc_info=True)
            return False

    def load_model(self) -> bool:
        """
        Loads the trained model from disk.

        Returns:
            bool: True if loading is successful, False otherwise.
        """
        try:
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
            self.logger.info(f"Model loaded successfully from '{self.model_path}'.")
            return True
        except FileNotFoundError:
            self.logger.error(f"Model file '{self.model_path}' not found.")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load UserBehaviorModel: {e}", exc_info=True)
            return False
