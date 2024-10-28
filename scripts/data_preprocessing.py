# scripts/data_preprocessing.py

"""
Data Preprocessing Module

This module handles data loading, cleaning, feature engineering, and preprocessing
to prepare the dataset for model training.
"""

import os
import pandas as pd
import numpy as np
import logging
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from typing import Tuple, Dict, Any
import joblib

# Configure Logging
logging.basicConfig(
    filename='logs/data_preprocessing.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DataPreprocessor:
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the DataPreprocessor with configuration parameters.

        Args:
            config (Dict[str, Any]): Configuration dictionary containing paths and parameters.
        """
        self.config = config
        self.raw_data_path = config.get('raw_data_path')
        self.processed_data_path = config.get('processed_data_path')
        self.test_size = config.get('test_size', 0.2)
        self.random_state = config.get('random_state', 42)
        self.model_output_path = config.get('model_output_path')
        self.preprocessor_path = config.get('preprocessor_path')
        self.target_column = config.get('target_column')
        self.numerical_features = config.get('numerical_features')
        self.categorical_features = config.get('categorical_features')
        self.pipeline = None

    def load_data(self) -> pd.DataFrame:
        """
        Loads raw data from the specified CSV file.

        Returns:
            pd.DataFrame: Loaded dataset.

        Raises:
            FileNotFoundError: If the raw data file does not exist.
            pd.errors.ParserError: If the file cannot be parsed as CSV.
        """
        if not os.path.exists(self.raw_data_path):
            logger.error(f"Raw data file not found at {self.raw_data_path}")
            raise FileNotFoundError(f"Raw data file not found at {self.raw_data_path}")
        try:
            data = pd.read_csv(self.raw_data_path)
            logger.info(f"Loaded data with shape {data.shape} from {self.raw_data_path}")
            return data
        except pd.errors.ParserError as e:
            logger.error(f"Error parsing CSV file: {e}")
            raise

    def clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans the dataset by handling missing values and removing duplicates.

        Args:
            data (pd.DataFrame): The raw dataset.

        Returns:
            pd.DataFrame: Cleaned dataset.
        """
        initial_shape = data.shape
        data = data.drop_duplicates()
        logger.info(f"Dropped duplicates: {initial_shape[0] - data.shape[0]} rows removed")

        # Handle missing values
        # Numerical features: Impute with median
        # Categorical features: Impute with mode
        data[self.numerical_features] = data[self.numerical_features].fillna(
            data[self.numerical_features].median()
        )
        data[self.categorical_features] = data[self.categorical_features].fillna(
            data[self.categorical_features].mode().iloc[0]
        )
        logger.info("Handled missing values for numerical and categorical features")
        return data

    def feature_engineering(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Performs feature engineering such as encoding categorical variables and scaling numerical features.

        Args:
            data (pd.DataFrame): The cleaned dataset.

        Returns:
            pd.DataFrame: Dataset with engineered features.
        """
        # Define transformers for numerical and categorical features
        numerical_transformer = Pipeline(steps=[
            ('scaler', StandardScaler())
        ])

        categorical_transformer = Pipeline(steps=[
            ('onehot', OneHotEncoder(handle_unknown='ignore'))
        ])

        preprocessor = ColumnTransformer(
            transformers=[
                ('num', numerical_transformer, self.numerical_features),
                ('cat', categorical_transformer, self.categorical_features)
            ]
        )

        self.pipeline = Pipeline(steps=[
            ('preprocessor', preprocessor)
        ])

        # Fit the pipeline
        X = data.drop(columns=[self.target_column])
        y = data[self.target_column]
        self.pipeline.fit(X)
        logger.info("Fitted preprocessing pipeline")

        # Transform the data
        X_processed = self.pipeline.transform(X)
        logger.info(f"Transformed data with shape {X_processed.shape}")
        return pd.DataFrame(X_processed)

    def save_preprocessor(self):
        """
        Saves the preprocessing pipeline to the specified path.
        """
        if self.pipeline is not None:
            joblib.dump(self.pipeline, self.preprocessor_path)
            logger.info(f"Saved preprocessing pipeline to {self.preprocessor_path}")
        else:
            logger.error("Pipeline is not fitted and cannot be saved.")
            raise ValueError("Pipeline is not fitted and cannot be saved.")

    def split_data(self, data: pd.DataFrame, target: pd.Series) -> Tuple:
        """
        Splits the data into training and testing sets.

        Args:
            data (pd.DataFrame): The processed feature data.
            target (pd.Series): The target variable.

        Returns:
            Tuple: Contains X_train, X_test, y_train, y_test.
        """
        X_train, X_test, y_train, y_test = train_test_split(
            data, target,
            test_size=self.test_size,
            random_state=self.random_state,
            stratify=target
        )
        logger.info(f"Split data into train and test sets with test size {self.test_size}")
        return X_train, X_test, y_train, y_test

    def save_processed_data(self, X_train: pd.DataFrame, X_test: pd.DataFrame,
                           y_train: pd.Series, y_test: pd.Series):
        """
        Saves the processed training and testing data to CSV files.

        Args:
            X_train (pd.DataFrame): Training feature data.
            X_test (pd.DataFrame): Testing feature data.
            y_train (pd.Series): Training target data.
            y_test (pd.Series): Testing target data.
        """
        train = pd.concat([X_train, y_train.reset_index(drop=True)], axis=1)
        test = pd.concat([X_test, y_test.reset_index(drop=True)], axis=1)

        train.to_csv(os.path.join(self.processed_data_path, 'train.csv'), index=False)
        test.to_csv(os.path.join(self.processed_data_path, 'test.csv'), index=False)
        logger.info(f"Saved processed training data to {os.path.join(self.processed_data_path, 'train.csv')}")
        logger.info(f"Saved processed testing data to {os.path.join(self.processed_data_path, 'test.csv')}")

    def preprocess(self) -> None:
        """
        Executes the full preprocessing pipeline: load, clean, feature engineering, split, and save.
        """
        try:
            data = self.load_data()
            data = self.clean_data(data)
            processed_data = self.feature_engineering(data)
            X_train, X_test, y_train, y_test = self.split_data(processed_data, data[self.target_column])
            self.save_preprocessor()
            self.save_processed_data(X_train, X_test, y_train, y_test)
            logger.info("Data preprocessing completed successfully")
        except Exception as e:
            logger.exception(f"Data preprocessing failed: {e}")
            raise

def main():
    # Configuration Parameters
    config = {
        'raw_data_path': 'data/raw/data.csv',
        'processed_data_path': 'data/processed/',
        'test_size': 0.2,
        'random_state': 42,
        'model_output_path': 'models/',
        'preprocessor_path': 'models/preprocessor.joblib',
        'target_column': 'target',
        'numerical_features': ['feature1', 'feature2', 'feature3'],
        'categorical_features': ['feature4', 'feature5']
    }

    preprocessor = DataPreprocessor(config)
    preprocessor.preprocess()

if __name__ == "__main__":
    main()
