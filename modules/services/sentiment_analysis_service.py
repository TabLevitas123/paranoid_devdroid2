# services/sentiment_analysis_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager
from transformers import pipeline, Pipeline
from transformers.pipelines.pt_utils import KeyDataset
import torch

class SentimentAnalysisError(Exception):
    """Custom exception for SentimentAnalysisService-related errors."""
    pass

class SentimentAnalysisService:
    """
    Provides sentiment analysis capabilities using pre-trained models.
    Handles text processing, model loading, prediction, and ensures secure and efficient operations.
    """

    def __init__(self):
        """
        Initializes the SentimentAnalysisService with necessary configurations and model setup.
        """
        self.logger = setup_logging('SentimentAnalysisService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.model_name = self.config_loader.get('SENTIMENT_MODEL_NAME', 'distilbert-base-uncased-finetuned-sst-2-english')
        self.device = self._determine_device()
        self.sentiment_pipeline = self._initialize_pipeline()
        self.lock = threading.Lock()
        self.logger.info("SentimentAnalysisService initialized successfully.")

    def _determine_device(self) -> int:
        """
        Determines the appropriate device (CPU or GPU) for model inference.
        
        Returns:
            int: The device identifier for PyTorch ('cuda' as 0 if GPU is available, else 'cpu').
        """
        try:
            self.logger.debug("Determining computation device for sentiment analysis.")
            if torch.cuda.is_available():
                device = 0  # GPU
                self.logger.debug("GPU detected. Using GPU for sentiment analysis.")
            else:
                device = -1  # CPU
                self.logger.debug("GPU not detected. Using CPU for sentiment analysis.")
            return device
        except Exception as e:
            self.logger.error(f"Error determining computation device: {e}", exc_info=True)
            return -1  # Default to CPU

    def _initialize_pipeline(self) -> Pipeline:
        """
        Initializes the sentiment analysis pipeline using the specified model.
        
        Returns:
            Pipeline: The initialized sentiment analysis pipeline.
        
        Raises:
            SentimentAnalysisError: If the model fails to load.
        """
        try:
            self.logger.debug(f"Loading sentiment analysis model '{self.model_name}'.")
            sentiment_pipeline = pipeline('sentiment-analysis', model=self.model_name, device=self.device)
            self.logger.debug("Sentiment analysis pipeline initialized successfully.")
            return sentiment_pipeline
        except Exception as e:
            self.logger.error(f"Error initializing sentiment analysis pipeline: {e}", exc_info=True)
            raise SentimentAnalysisError(f"Error initializing sentiment analysis pipeline: {e}")

    def analyze_sentiment(self, texts: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Analyzes the sentiment of a list of texts.
        
        Args:
            texts (List[str]): A list of text strings to analyze.
        
        Returns:
            Optional[List[Dict[str, Any]]]: A list of sentiment analysis results, or None if failed.
        """
        try:
            self.logger.debug(f"Analyzing sentiment for {len(texts)} texts.")
            with self.lock:
                results = self.sentiment_pipeline(texts)
            self.logger.info("Sentiment analysis completed successfully.")
            return results
        except Exception as e:
            self.logger.error(f"Error during sentiment analysis: {e}", exc_info=True)
            return None

    def analyze_sentiment_async(self, texts: List[str], callback: Optional[Any] = None) -> threading.Thread:
        """
        Analyzes sentiment asynchronously and optionally executes a callback with the results.
        
        Args:
            texts (List[str]): A list of text strings to analyze.
            callback (Optional[Any], optional): A callback function to execute with the results. Defaults to None.
        
        Returns:
            threading.Thread: The thread handling the asynchronous sentiment analysis.
        """
        def analyze():
            try:
                self.logger.debug("Starting asynchronous sentiment analysis.")
                results = self.analyze_sentiment(texts)
                if callback and callable(callback):
                    callback(results)
                self.logger.debug("Asynchronous sentiment analysis completed.")
            except Exception as e:
                self.logger.error(f"Error in asynchronous sentiment analysis: {e}", exc_info=True)

        thread = threading.Thread(target=analyze, daemon=True)
        thread.start()
        self.logger.info("Scheduled asynchronous sentiment analysis.")
        return thread

    def get_model_summary(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves a summary of the sentiment analysis model, including its architecture and parameters.
        
        Returns:
            Optional[Dict[str, Any]]: A dictionary containing model summary details, or None if failed.
        """
        try:
            self.logger.debug("Retrieving sentiment analysis model summary.")
            model = self.sentiment_pipeline.model
            summary = {
                'model_name': self.model_name,
                'architecture': str(model.__class__.__name__),
                'number_of_parameters': sum(p.numel() for p in model.parameters() if p.requires_grad),
                'device': 'GPU' if self.device >=0 else 'CPU'
            }
            self.logger.info("Sentiment analysis model summary retrieved successfully.")
            return summary
        except Exception as e:
            self.logger.error(f"Error retrieving model summary: {e}", exc_info=True)
            return None

    def update_model(self, new_model_name: str) -> bool:
        """
        Updates the sentiment analysis model to a new specified model.
        
        Args:
            new_model_name (str): The name of the new model to load.
        
        Returns:
            bool: True if the model is updated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Updating sentiment analysis model to '{new_model_name}'.")
            self.model_name = new_model_name
            self.sentiment_pipeline = self._initialize_pipeline()
            self.logger.info(f"Sentiment analysis model updated to '{new_model_name}' successfully.")
            return True
        except SentimentAnalysisError as e:
            self.logger.error(f"Error updating model: {e}", exc_info=True)
            return False

    def save_model(self, save_directory: str) -> bool:
        """
        Saves the current sentiment analysis model to the specified directory.
        
        Args:
            save_directory (str): The local directory where the model will be saved.
        
        Returns:
            bool: True if the model is saved successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Saving sentiment analysis model to '{save_directory}'.")
            self.sentiment_pipeline.model.save_pretrained(save_directory)
            self.sentiment_pipeline.tokenizer.save_pretrained(save_directory)
            self.logger.info(f"Sentiment analysis model saved to '{save_directory}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error saving sentiment analysis model: {e}", exc_info=True)
            return False

    def load_saved_model(self, load_directory: str) -> bool:
        """
        Loads a previously saved sentiment analysis model from the specified directory.
        
        Args:
            load_directory (str): The local directory from where the model will be loaded.
        
        Returns:
            bool: True if the model is loaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Loading saved sentiment analysis model from '{load_directory}'.")
            self.sentiment_pipeline = pipeline('sentiment-analysis', model=load_directory, device=self.device)
            self.logger.info(f"Sentiment analysis model loaded from '{load_directory}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error loading saved sentiment analysis model: {e}", exc_info=True)
            return False

    def classify_texts(self, texts: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Classifies a list of texts into their respective sentiments.
        
        Args:
            texts (List[str]): A list of text strings to classify.
        
        Returns:
            Optional[List[Dict[str, Any]]]: A list of classification results, or None if failed.
        """
        try:
            self.logger.debug(f"Classifying {len(texts)} texts.")
            results = self.analyze_sentiment(texts)
            self.logger.info("Text classification completed successfully.")
            return results
        except Exception as e:
            self.logger.error(f"Error classifying texts: {e}", exc_info=True)
            return None

    def get_confidence_scores(self, texts: List[str]) -> Optional[List[float]]:
        """
        Retrieves the confidence scores for each sentiment classification.
        
        Args:
            texts (List[str]): A list of text strings to analyze.
        
        Returns:
            Optional[List[float]]: A list of confidence scores, or None if failed.
        """
        try:
            self.logger.debug(f"Retrieving confidence scores for {len(texts)} texts.")
            results = self.analyze_sentiment(texts)
            if results is None:
                return None
            confidence_scores = [result.get('score', 0.0) for result in results]
            self.logger.info("Confidence scores retrieved successfully.")
            return confidence_scores
        except Exception as e:
            self.logger.error(f"Error retrieving confidence scores: {e}", exc_info=True)
            return None
