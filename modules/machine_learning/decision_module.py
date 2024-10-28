# modules/machine_learning/decisions_module.py

"""
Decisions Module

This module provides advanced machine learning decision-making capabilities, encapsulated within the DecisionsModule class. It includes:

- Model loading and management
- Input data validation and preprocessing
- Prediction and decision-making
- Output postprocessing
- Error handling and logging
- Security measures to protect against malicious inputs
- Thread-safe operations for concurrent environments

Author: Your Name
Date: YYYY-MM-DD
"""

import os
import logging
import threading
from typing import Any, Dict, Optional
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.exceptions import NotFittedError
from jsonschema import validate, ValidationError

# Configure Logging
logger = logging.getLogger('decisions_module')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/decisions.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class DecisionsModuleError(Exception):
    """Base class for DecisionsModule exceptions."""
    pass

class ModelNotLoadedError(DecisionsModuleError):
    """Raised when a model is not loaded but an operation requires it."""
    pass

class InvalidInputError(DecisionsModuleError):
    """Raised when input data is invalid."""
    pass

class PredictionError(DecisionsModuleError):
    """Raised when prediction fails."""
    pass

class DecisionModule:
    """
    DecisionModule Class

    Provides methods for loading machine learning models, validating and preprocessing input data,
    making predictions, and handling outputs securely and efficiently.
    """

    def __init__(self, model_path: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any]):
        """
        Initializes the DecisionsModule.

        Args:
            model_path (str): Path to the serialized machine learning model.
            input_schema (Dict[str, Any]): JSON schema for input data validation.
            output_schema (Dict[str, Any]): JSON schema for output data validation.
        """
        self.model_path = model_path
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.model: Optional[BaseEstimator] = None
        self.model_lock = threading.Lock()
        self._load_model()

    def _load_model(self) -> None:
        """
        Loads the machine learning model from the specified path.

        Raises:
            ModelNotLoadedError: If the model fails to load.
        """
        if not os.path.exists(self.model_path):
            logger.error(f"Model file not found at {self.model_path}")
            raise ModelNotLoadedError(f"Model file not found at {self.model_path}")

        try:
            with self.model_lock:
                self.model = joblib.load(self.model_path)
                if not isinstance(self.model, BaseEstimator):
                    logger.error("Loaded object is not a valid sklearn estimator.")
                    raise TypeError("Loaded object is not a valid sklearn estimator.")
                logger.info(f"Model loaded successfully from {self.model_path}")
        except Exception as e:
            logger.exception(f"Failed to load model: {e}")
            raise ModelNotLoadedError(f"Failed to load model: {e}")

    def _validate_input(self, data: Dict[str, Any]) -> None:
        """
        Validates the input data against the predefined schema.

        Args:
            data (Dict[str, Any]): Input data to validate.

        Raises:
            InvalidInputError: If validation fails.
        """
        try:
            validate(instance=data, schema=self.input_schema)
            logger.debug("Input data validated successfully.")
        except ValidationError as e:
            logger.warning(f"Input validation error: {e.message}")
            raise InvalidInputError(e.message)

    def _preprocess_input(self, data: Dict[str, Any]) -> pd.DataFrame:
        """
        Preprocesses the input data for prediction.

        Args:
            data (Dict[str, Any]): Validated input data.

        Returns:
            pd.DataFrame: Preprocessed data ready for prediction.
        """
        try:
            df = pd.DataFrame([data])
            # Implement any necessary preprocessing steps here
            # Example: Encoding categorical variables, scaling, etc.
            logger.debug("Input data preprocessed successfully.")
            return df
        except Exception as e:
            logger.exception(f"Input preprocessing failed: {e}")
            raise InvalidInputError(f"Input preprocessing failed: {e}")

    def _validate_output(self, data: Dict[str, Any]) -> None:
        """
        Validates the output data against the predefined schema.

        Args:
            data (Dict[str, Any]): Output data to validate.

        Raises:
            PredictionError: If validation fails.
        """
        try:
            validate(instance=data, schema=self.output_schema)
            logger.debug("Output data validated successfully.")
        except ValidationError as e:
            logger.warning(f"Output validation error: {e.message}")
            raise PredictionError(e.message)

    def make_decision(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Makes a prediction based on the input data.

        Args:
            input_data (Dict[str, Any]): Raw input data.

        Returns:
            Dict[str, Any]: The prediction result.

        Raises:
            DecisionsModuleError: If any step in the decision-making process fails.
        """
        try:
            # Validate input data
            self._validate_input(input_data)

            # Preprocess input data
            preprocessed_data = self._preprocess_input(input_data)

            # Make prediction
            with self.model_lock:
                if self.model is None:
                    logger.error("Model is not loaded.")
                    raise ModelNotLoadedError("Model is not loaded.")
                try:
                    prediction = self.model.predict(preprocessed_data)
                    probability = self.model.predict_proba(preprocessed_data)
                    logger.info("Prediction made successfully.")
                except NotFittedError as e:
                    logger.error(f"Model is not fitted: {e}")
                    raise ModelNotLoadedError("Model is not fitted.") from e
                except Exception as e:
                    logger.exception(f"Prediction failed: {e}")
                    raise PredictionError(f"Prediction failed: {e}")

            # Prepare output data
            output_data = {
                "prediction": prediction[0],
                "probability": probability[0].tolist()
            }

            # Validate output data
            self._validate_output(output_data)

            logger.debug("Decision-making process completed successfully.")
            return output_data

        except DecisionsModuleError as e:
            logger.error(f"Decision-making error: {e}")
            raise
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise DecisionsModuleError(f"An unexpected error occurred: {e}")

    def update_model(self, new_model_path: str) -> None:
        """
        Updates the model by loading a new one from the specified path.

        Args:
            new_model_path (str): Path to the new model file.

        Raises:
            ModelNotLoadedError: If the new model fails to load.
        """
        self.model_path = new_model_path
        self._load_model()
        logger.info(f"Model updated successfully to {new_model_path}")

    def get_model_info(self) -> Dict[str, Any]:
        """
        Retrieves information about the loaded model.

        Returns:
            Dict[str, Any]: A dictionary containing model information.

        Raises:
            ModelNotLoadedError: If the model is not loaded.
        """
        if self.model is None:
            logger.error("Model is not loaded.")
            raise ModelNotLoadedError("Model is not loaded.")

        try:
            model_info = {
                "model_type": type(self.model).__name__,
                "model_params": self.model.get_params()
            }
            logger.debug("Model information retrieved successfully.")
            return model_info
        except Exception as e:
            logger.exception(f"Failed to retrieve model information: {e}")
            raise DecisionsModuleError(f"Failed to retrieve model information: {e}")

    # Additional methods can be added here for more functionalities
    # For example: methods for model evaluation, batch predictions, etc.

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    # Define input and output schemas
    input_schema_example = {
        "type": "object",
        "properties": {
            "feature1": {"type": "number"},
            "feature2": {"type": "number"},
            "feature3": {"type": "number"},
            "feature4": {"type": "string"}
        },
        "required": ["feature1", "feature2", "feature3", "feature4"]
    }

    output_schema_example = {
        "type": "object",
        "properties": {
            "prediction": {"type": "number"},
            "probability": {
                "type": "array",
                "items": {"type": "number"}
            }
        },
        "required": ["prediction", "probability"]
    }

    # Initialize DecisionsModule
    try:
        decisions_module = DecisionModule(
            model_path='models/random_forest.joblib',
            input_schema=input_schema_example,
            output_schema=output_schema_example
        )
    except DecisionsModuleError as e:
        print(f"Initialization error: {e}")
        exit(1)

    # Make a decision
    input_data_example = {
        "feature1": 5.1,
        "feature2": 3.5,
        "feature3": 1.4,
        "feature4": "category_a"
    }

    try:
        result = decisions_module.make_decision(input_data_example)
        print(f"Decision result: {result}")
    except DecisionsModuleError as e:
        print(f"Decision-making error: {e}")
