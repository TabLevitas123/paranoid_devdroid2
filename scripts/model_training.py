# scripts/model_training.py

"""
Model Training Module

This module handles the training of machine learning models, hyperparameter tuning,
evaluation, and saving the trained models.
"""

import os
import logging
import joblib
from typing import Dict, Any
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score, accuracy_score
import pandas as pd

# Configure Logging
logging.basicConfig(
    filename='logs/model_training.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ModelTrainer:
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the ModelTrainer with configuration parameters.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing paths and parameters.
        """
        self.config = config
        self.train_data_path = config.get('train_data_path')
        self.model_output_path = config.get('model_output_path')
        self.preprocessor_path = config.get('preprocessor_path')
        self.model_path = config.get('model_path')
        self.target_column = config.get('target_column')
        self.model_parameters = config.get('model_parameters', {})
        self.best_model = None
        self.pipeline = None

    def load_data(self) -> pd.DataFrame:
        """
        Loads processed training data from the specified CSV file.

        Returns:
            pd.DataFrame: Training dataset.

        Raises:
            FileNotFoundError: If the training data file does not exist.
            pd.errors.ParserError: If the file cannot be parsed as CSV.
        """
        if not os.path.exists(self.train_data_path):
            logger.error(f"Training data file not found at {self.train_data_path}")
            raise FileNotFoundError(f"Training data file not found at {self.train_data_path}")
        try:
            data = pd.read_csv(self.train_data_path)
            logger.info(f"Loaded training data with shape {data.shape} from {self.train_data_path}")
            return data
        except pd.errors.ParserError as e:
            logger.error(f"Error parsing CSV file: {e}")
            raise

    def load_preprocessor(self):
        """
        Loads the preprocessing pipeline from the specified path.
        """
        if not os.path.exists(self.preprocessor_path):
            logger.error(f"Preprocessing pipeline not found at {self.preprocessor_path}")
            raise FileNotFoundError(f"Preprocessing pipeline not found at {self.preprocessor_path}")
        try:
            self.pipeline = joblib.load(self.preprocessor_path)
            logger.info(f"Loaded preprocessing pipeline from {self.preprocessor_path}")
        except Exception as e:
            logger.error(f"Failed to load preprocessing pipeline: {e}")
            raise

    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Separates features and target variable from the dataset.

        Args:
            data (pd.DataFrame): The training dataset.

        Returns:
            pd.DataFrame: Feature matrix.
            pd.Series: Target vector.
        """
        X = data.drop(columns=[self.target_column])
        y = data[self.target_column]
        logger.info(f"Separated features and target variable '{self.target_column}'")
        return X, y

    def train_model(self, X: pd.DataFrame, y: pd.Series) -> Any:
        """
        Trains the machine learning model using GridSearchCV for hyperparameter tuning.

        Args:
            X (pd.DataFrame): Feature matrix.
            y (pd.Series): Target vector.

        Returns:
            Any: The best estimator found by GridSearchCV.
        """
        model = RandomForestClassifier(random_state=self.config.get('random_state', 42))
        grid_search = GridSearchCV(
            estimator=model,
            param_grid=self.model_parameters,
            cv=5,
            scoring='roc_auc',
            n_jobs=-1,
            verbose=2
        )
        logger.info("Starting model training with GridSearchCV")
        grid_search.fit(X, y)
        logger.info(f"Completed model training. Best parameters: {grid_search.best_params_}")
        self.best_model = grid_search.best_estimator_
        return self.best_model

    def evaluate_model(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, Any]:
        """
        Evaluates the trained model using various metrics.

        Args:
            X (pd.DataFrame): Feature matrix.
            y (pd.Series): Target vector.

        Returns:
            Dict[str, Any]: Dictionary containing evaluation metrics.
        """
        predictions = self.best_model.predict(X)
        probabilities = self.best_model.predict_proba(X)[:,1]

        metrics = {
            'accuracy': accuracy_score(y, predictions),
            'confusion_matrix': confusion_matrix(y, predictions).tolist(),
            'classification_report': classification_report(y, predictions, output_dict=True),
            'roc_auc': roc_auc_score(y, probabilities)
        }

        logger.info(f"Model Evaluation Metrics: {metrics}")
        return metrics

    def save_model(self):
        """
        Saves the trained model to the specified path.
        """
        os.makedirs(self.model_output_path, exist_ok=True)
        joblib.dump(self.best_model, self.model_path)
        logger.info(f"Saved trained model to {self.model_path}")

    def perform_cross_validation(self, X: pd.DataFrame, y: pd.Series) -> float:
        """
        Performs cross-validation and returns the average score.

        Args:
            X (pd.DataFrame): Feature matrix.
            y (pd.Series): Target vector.

        Returns:
            float: Average cross-validation score.
        """
        scores = cross_val_score(self.best_model, X, y, cv=5, scoring='roc_auc', n_jobs=-1)
        average_score = scores.mean()
        logger.info(f"Cross-validation ROC AUC scores: {scores}")
        logger.info(f"Average Cross-validation ROC AUC score: {average_score}")
        return average_score

    def train(self) -> Dict[str, Any]:
        """
        Executes the full model training pipeline: load data, preprocess, train, evaluate, and save.

        Returns:
            Dict[str, Any]: Evaluation metrics.
        """
        try:
            data = self.load_data()
            self.load_preprocessor()
            X, y = self.prepare_features(data)
            X_processed = self.pipeline.transform(X)
            logger.info(f"Transformed feature matrix with shape {X_processed.shape}")
            best_model = self.train_model(X_processed, y)
            metrics = self.evaluate_model(X_processed, y)
            cross_val_score_avg = self.perform_cross_validation(X_processed, y)
            self.save_model()
            logger.info("Model training pipeline completed successfully")
            return metrics
        except Exception as e:
            logger.exception(f"Model training failed: {e}")
            raise

def main():
    # Configuration Parameters
    config = {
        'train_data_path': 'data/processed/train.csv',
        'model_output_path': 'models/',
        'preprocessor_path': 'models/preprocessor.joblib',
        'model_path': 'models/random_forest.joblib',
        'target_column': 'target',
        'random_state': 42,
        'model_parameters': {
            'n_estimators': [100, 200],
            'max_depth': [None, 10, 20],
            'min_samples_split': [2, 5],
            'min_samples_leaf': [1, 2],
            'bootstrap': [True, False]
        }
    }

    trainer = ModelTrainer(config)
    metrics = trainer.train()
    # Optionally, save metrics to a file or database
    # For example:
    # with open('logs/training_metrics.json', 'w') as f:
    #     json.dump(metrics, f, indent=4)

if __name__ == "__main__":
    main()
