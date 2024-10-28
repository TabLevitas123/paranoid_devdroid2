# supervised_unsupervised_module.py

import logging
import threading
import pickle
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
from sklearn.ensemble import RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager
from modules.data.data_module import DataModule
from modules.memory.shared_memory import SharedMemory

class SupervisedUnsupervisedModule:
    """
    Combines supervised and unsupervised learning methods for comprehensive data analysis.
    """

    def __init__(self, agent_id):
        self.logger = setup_logging('SupervisedUnsupervisedModule')
        self.encryption_manager = EncryptionManager()
        self.data_module = DataModule()
        self.shared_memory = SharedMemory()
        self.agent_id = agent_id
        self.lock = threading.Lock()
        self.supervised_model = None
        self.unsupervised_model = None
        self.scaler = StandardScaler()
        self.logger.info(f"SupervisedUnsupervisedModule initialized for agent {agent_id}.")

    def train_supervised_model(self, X, y, model_type='RandomForest'):
        """
        Trains a supervised learning model.

        Args:
            X (array-like): Feature data.
            y (array-like): Target labels.
            model_type (str): Type of model to train ('RandomForest', 'SVM').

        Returns:
            model: Trained machine learning model.
        """
        try:
            self.logger.info(f"Training supervised model of type {model_type}.")
            if model_type == 'RandomForest':
                model = RandomForestClassifier()
            elif model_type == 'SVM':
                from sklearn.svm import SVC
                model = SVC(probability=True)
            else:
                self.logger.error(f"Unsupported model type: {model_type}")
                raise ValueError(f"Unsupported model type: {model_type}")

            X_scaled = self.scaler.fit_transform(X)
            model.fit(X_scaled, y)
            self.supervised_model = model
            self.logger.info("Supervised model trained successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error training supervised model: {e}", exc_info=True)
            raise

    def evaluate_supervised_model(self, X_test, y_test):
        """
        Evaluates the supervised learning model.

        Args:
            X_test (array-like): Test feature data.
            y_test (array-like): Test target labels.

        Returns:
            dict: Evaluation metrics including accuracy and classification report.
        """
        try:
            if not self.supervised_model:
                self.logger.error("Supervised model is not trained.")
                raise ValueError("Supervised model is not trained.")
            self.logger.info("Evaluating supervised model.")
            X_test_scaled = self.scaler.transform(X_test)
            y_pred = self.supervised_model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            report = classification_report(y_test, y_pred, output_dict=True)
            self.logger.info(f"Model evaluation completed with accuracy: {accuracy}")
            return {'accuracy': accuracy, 'report': report}
        except Exception as e:
            self.logger.error(f"Error evaluating supervised model: {e}", exc_info=True)
            raise

    def train_unsupervised_model(self, X, model_type='KMeans', **kwargs):
        """
        Trains an unsupervised learning model.

        Args:
            X (array-like): Feature data.
            model_type (str): Type of model to train ('KMeans', 'PCA').
            **kwargs: Additional keyword arguments for model initialization.

        Returns:
            model: Trained unsupervised learning model.
        """
        try:
            self.logger.info(f"Training unsupervised model of type {model_type}.")
            if model_type == 'KMeans':
                n_clusters = kwargs.get('n_clusters', 8)
                model = KMeans(n_clusters=n_clusters)
            elif model_type == 'PCA':
                n_components = kwargs.get('n_components', 2)
                model = PCA(n_components=n_components)
            else:
                self.logger.error(f"Unsupported model type: {model_type}")
                raise ValueError(f"Unsupported model type: {model_type}")

            X_scaled = self.scaler.fit_transform(X)
            model.fit(X_scaled)
            self.unsupervised_model = model
            self.logger.info("Unsupervised model trained successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error training unsupervised model: {e}", exc_info=True)
            raise

    def predict_unsupervised_model(self, X_new):
        """
        Generates predictions using the unsupervised learning model.

        Args:
            X_new (array-like): New feature data.

        Returns:
            array: Predicted clusters or transformed data.
        """
        try:
            if not self.unsupervised_model:
                self.logger.error("Unsupervised model is not trained.")
                raise ValueError("Unsupervised model is not trained.")
            self.logger.info("Generating predictions with unsupervised model.")
            X_new_scaled = self.scaler.transform(X_new)
            if hasattr(self.unsupervised_model, 'predict'):
                predictions = self.unsupervised_model.predict(X_new_scaled)
            elif hasattr(self.unsupervised_model, 'transform'):
                predictions = self.unsupervised_model.transform(X_new_scaled)
            else:
                self.logger.error("Unsupervised model does not support predict or transform.")
                raise AttributeError("Unsupervised model does not support predict or transform.")
            self.logger.info("Predictions generated successfully.")
            return predictions
        except Exception as e:
            self.logger.error(f"Error predicting with unsupervised model: {e}", exc_info=True)
            raise

    def integrate_models(self, X_new):
        """
        Integrates the supervised and unsupervised models to provide enhanced insights.

        Args:
            X_new (array-like): New feature data.

        Returns:
            dict: Combined insights from both models.
        """
        try:
            self.logger.info("Integrating models for enhanced insights.")
            supervised_preds = self.supervised_model.predict(self.scaler.transform(X_new))
            unsupervised_preds = self.predict_unsupervised_model(X_new)
            combined_results = {
                'supervised_predictions': supervised_preds,
                'unsupervised_predictions': unsupervised_preds
            }
            self.logger.info("Models integrated successfully.")
            return combined_results
        except Exception as e:
            self.logger.error(f"Error integrating models: {e}", exc_info=True)
            raise

    def serialize_models(self):
        """
        Serializes the supervised and unsupervised models for storage or transmission.

        Returns:
            bytes: The serialized models.
        """
        try:
            self.logger.info("Serializing models.")
            with self.lock:
                model_data = {
                    'supervised_model': self.supervised_model,
                    'unsupervised_model': self.unsupervised_model,
                    'scaler': self.scaler
                }
                serialized_models = pickle.dumps(model_data)
                encrypted_models = self.encryption_manager.encrypt_data(serialized_models)
            self.logger.info("Models serialized and encrypted successfully.")
            return encrypted_models
        except Exception as e:
            self.logger.error(f"Error serializing models: {e}", exc_info=True)
            raise

    def deserialize_models(self, encrypted_models):
        """
        Deserializes the supervised and unsupervised models from bytes.

        Args:
            encrypted_models (bytes): The encrypted serialized models.

        Returns:
            None
        """
        try:
            self.logger.info("Deserializing models.")
            decrypted_data = self.encryption_manager.decrypt_data(encrypted_models)
            with self.lock:
                model_data = pickle.loads(decrypted_data)
                self.supervised_model = model_data.get('supervised_model')
                self.unsupervised_model = model_data.get('unsupervised_model')
                self.scaler = model_data.get('scaler')
            self.logger.info("Models deserialized and decrypted successfully.")
        except Exception as e:
            self.logger.error(f"Error deserializing models: {e}", exc_info=True)
            raise

    def save_models(self):
        """
        Saves the models to shared memory securely.
        """
        try:
            models_bytes = self.serialize_models()
            key = f"models_{self.agent_id}"
            self.shared_memory.write_data(key, models_bytes, self.agent_id)
            self.logger.info(f"Models saved to shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error saving models: {e}", exc_info=True)
            raise

    def load_models(self):
        """
        Loads the models from shared memory securely.
        """
        try:
            key = f"models_{self.agent_id}"
            models_bytes = self.shared_memory.read_data(key, self.agent_id)
            if models_bytes:
                self.deserialize_models(models_bytes)
                self.logger.info(f"Models loaded from shared memory with key {key}.")
            else:
                self.logger.warning(f"No models found in shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error loading models: {e}", exc_info=True)
            raise

    def share_models(self, recipient_agent_id):
        """
        Shares the models with another agent securely.

        Args:
            recipient_agent_id (str): The ID of the agent to share models with.

        Returns:
            bool: True if sharing is successful, False otherwise.
        """
        try:
            self.logger.info(f"Sharing models with agent {recipient_agent_id}.")
            models_bytes = self.serialize_models()
            # Assuming a communication module exists to send data to other agents
            from modules.communication.communication_module import CommunicationModule
            communication_module = CommunicationModule()
            message = {
                'sender_id': self.agent_id,
                'receiver_id': recipient_agent_id,
                'message_type': 'model_share',
                'content': models_bytes
            }
            communication_module.send_message(
                sender_id=self.agent_id,
                receiver_id=recipient_agent_id,
                message_type='model_share',
                content=models_bytes
            )
            self.logger.info(f"Models shared successfully with agent {recipient_agent_id}.")
            return True
        except Exception as e:
            self.logger.error(f"Error sharing models with agent {recipient_agent_id}: {e}", exc_info=True)
            return False

    def receive_shared_models(self, message):
        """
        Processes incoming messages related to model sharing.

        Args:
            message (dict): The message received.
        """
        try:
            self.logger.info("Processing received model sharing message.")
            sender_id = message.get('sender_id')
            content = message.get('content')
            self.deserialize_models(content)
            self.logger.info(f"Models received and loaded from agent {sender_id}.")
        except Exception as e:
            self.logger.error(f"Error receiving shared models: {e}", exc_info=True)
            raise
