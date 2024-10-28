# ml_module.py

import logging
import threading
import pickle
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.svm import SVC
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager
from modules.data.data_module import DataModule
from marvin.sub_agents.hallucination_monitor import HallucinationMonitor
from modules.machine_learning.decision_module import DecisionModule
from modules.user_interface.user_preferences import UserPreferences
from modules.communication.communication_module import CommunicationModule

class MachineLearningModule:
    """
    Provides general machine learning functionalities.
    """

    def __init__(self):
        self.logger = setup_logging('MachineLearningModule')
        self.encryption_manager = EncryptionManager()
        self.data_module = DataModule()
        self.user_preferences = UserPreferences()
        self.communication_module = CommunicationModule()
        self.lock = threading.Lock()
        self.logger.info("MachineLearningModule initialized successfully.")

    def train_supervised_model(self, X, y, model_type='RandomForest'):
        """
        Trains a supervised learning model.

        Args:
            X (array-like): Feature data.
            y (array-like): Target labels.
            model_type (str): Type of model to train ('RandomForest', 'SVM').

        Returns:
            model: Trained machine learning model.
            scaler: Fitted scaler for data preprocessing.
        """
        try:
            self.logger.info(f"Training supervised model of type {model_type}.")
            if model_type == 'RandomForest':
                model = RandomForestClassifier()
            elif model_type == 'SVM':
                model = SVC(probability=True)
            else:
                self.logger.error(f"Unsupported model type: {model_type}")
                raise ValueError(f"Unsupported model type: {model_type}")

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            model.fit(X_scaled, y)
            self.logger.info("Supervised model trained successfully.")
            return model, scaler
        except Exception as e:
            self.logger.error(f"Error training supervised model: {e}", exc_info=True)
            raise

    def evaluate_supervised_model(self, model, scaler, X_test, y_test):
        """
        Evaluates a supervised learning model.

        Args:
            model: Trained machine learning model.
            scaler: Scaler used for feature scaling.
            X_test (array-like): Test feature data.
            y_test (array-like): Test target labels.

        Returns:
            dict: Evaluation metrics including accuracy and classification report.
        """
        try:
            self.logger.info("Evaluating supervised model.")
            X_test_scaled = scaler.transform(X_test)
            y_pred = model.predict(X_test_scaled)
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
            scaler: Fitted scaler for data preprocessing.
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

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            model.fit(X_scaled)
            self.logger.info("Unsupervised model trained successfully.")
            return model, scaler
        except Exception as e:
            self.logger.error(f"Error training unsupervised model: {e}", exc_info=True)
            raise

    def predict_unsupervised_model(self, model, scaler, X_new):
        """
        Generates predictions using an unsupervised learning model.

        Args:
            model: Trained unsupervised learning model.
            scaler: Scaler used for feature scaling.
            X_new (array-like): New feature data.

        Returns:
            array: Predicted clusters or transformed data.
        """
        try:
            self.logger.info("Generating predictions with unsupervised model.")
            X_new_scaled = scaler.transform(X_new)
            if hasattr(model, 'predict'):
                predictions = model.predict(X_new_scaled)
            elif hasattr(model, 'transform'):
                predictions = model.transform(X_new_scaled)
            else:
                self.logger.error("Model does not support prediction or transformation.")
                raise AttributeError("Model does not support prediction or transformation.")
            self.logger.info("Predictions generated successfully.")
            return predictions
        except Exception as e:
            self.logger.error(f"Error predicting with unsupervised model: {e}", exc_info=True)
            raise

    def serialize_model(self, model, scaler=None):
        """
        Serializes a model and its scaler into bytes.

        Args:
            model: The machine learning model to serialize.
            scaler: The scaler used for feature scaling (optional).

        Returns:
            bytes: Serialized model and scaler.
        """
        try:
            self.logger.info("Serializing model.")
            with self.lock:
                model_data = {'model': model}
                if scaler is not None:
                    model_data['scaler'] = scaler
                serialized_model = pickle.dumps(model_data)
            self.logger.info("Model serialized successfully.")
            return serialized_model
        except Exception as e:
            self.logger.error(f"Error serializing model: {e}", exc_info=True)
            raise

    def deserialize_model(self, serialized_model):
        """
        Deserializes a model and its scaler from bytes.

        Args:
            serialized_model (bytes): Serialized model bytes.

        Returns:
            tuple: Deserialized model and scaler (if present).
        """
        try:
            self.logger.info("Deserializing model.")
            with self.lock:
                model_data = pickle.loads(serialized_model)
                model = model_data.get('model')
                scaler = model_data.get('scaler')
            self.logger.info("Model deserialized successfully.")
            return model, scaler
        except Exception as e:
            self.logger.error(f"Error deserializing model: {e}", exc_info=True)
            raise

    def verify_consistency(self, data):
        """
        Verifies the consistency of the data using machine learning techniques.

        Args:
            data (array-like): The data to verify.

        Returns:
            bool: True if data is consistent, False otherwise.
        """
        try:
            self.logger.info("Verifying data consistency.")
            from sklearn.ensemble import IsolationForest
            scaler = StandardScaler()
            data_scaled = scaler.fit_transform(data)
            clf = IsolationForest(contamination='auto')
            anomalies = clf.fit_predict(data_scaled)
            is_consistent = (anomalies == 1).all()
            self.logger.info(f"Data consistency result: {is_consistent}")
            return is_consistent
        except Exception as e:
            self.logger.error(f"Error verifying data consistency: {e}", exc_info=True)
            return False

    def detect_hallucination(self, text):
        """
        Detects hallucinations in generated text.

        Args:
            text (str): The text to analyze.

        Returns:
            bool: True if hallucination is detected, False otherwise.
        """
        try:
            self.logger.info("Detecting hallucination in text.")
            hallucination_detector = HallucinationMonitor()
            is_hallucination = hallucination_detector.detect(text)
            self.logger.info(f"Hallucination detection result: {is_hallucination}")
            return is_hallucination
        except Exception as e:
            self.logger.error(f"Error detecting hallucination: {e}", exc_info=True)
            return True

    def analyze_decision(self, decision):
        """
        Analyzes a decision and generates a critique.

        Args:
            decision (str): The decision to analyze.

        Returns:
            str: The critique of the decision.
        """
        try:
            self.logger.info("Analyzing decision for critique.")
            decision_analyzer = DecisionModule()
            critique = decision_analyzer.analyze(decision)
            self.logger.info("Decision analysis completed.")
            return critique
        except Exception as e:
            self.logger.error(f"Error analyzing decision: {e}", exc_info=True)
            return "An error occurred while generating the critique."

    def update_knowledge_base(self, knowledge_data):
        """
        Updates the knowledge base with new data.

        Args:
            knowledge_data (dict): The knowledge data to update.

        Returns:
            bool: True if the knowledge base is updated successfully, False otherwise.
        """
        try:
            self.logger.info("Updating knowledge base.")
            # Implement logic to update knowledge base, e.g., database operations
            # For demonstration, we assume the update is successful
            self.logger.info("Knowledge base updated successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error updating knowledge base: {e}", exc_info=True)
            return False

    def evaluate_team_invitation(self, sender_id, content):
        """
        Evaluates a team invitation and decides whether to accept.

        Args:
            sender_id (str): ID of the agent sending the invitation.
            content (str): The invitation content.

        Returns:
            bool: True to accept the invitation, False to decline.
        """
        try:
            self.logger.info(f"Evaluating team invitation from {sender_id} with content: {content}")

            # Retrieve user preferences and past collaborations
            user_prefs = self.user_preferences.get_preferences()
            past_collaborations = self.user_preferences.get_past_collaborations()

            # Analyze the sender's reputation
            sender_reputation = self.communication_module.get_agent_reputation(sender_id)
            self.logger.debug(f"Sender {sender_id} reputation: {sender_reputation}")

            # Evaluate the invitation content for compatibility
            compatibility_score = self.analyze_invitation_content(content, user_prefs)
            self.logger.debug(f"Compatibility score with sender {sender_id}: {compatibility_score}")

            # Decision logic based on reputation and compatibility
            accept_threshold = 0.7  # Threshold for acceptance
            accept_invitation = (sender_reputation >= accept_threshold) and (compatibility_score >= accept_threshold)

            self.logger.info(f"Team invitation from {sender_id} {'accepted' if accept_invitation else 'declined'}.")
            return accept_invitation
        except Exception as e:
            self.logger.error(f"Error evaluating team invitation: {e}", exc_info=True)
            return False

    def analyze_invitation_content(self, content, user_prefs):
        """
        Analyzes the invitation content against user preferences.

        Args:
            content (str): The invitation content.
            user_prefs (dict): The user's preferences.

        Returns:
            float: A compatibility score between 0 and 1.
        """
        try:
            self.logger.info("Analyzing invitation content for compatibility.")
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            # Prepare the data
            preferences_text = ' '.join(user_prefs.get('interests', []))
            documents = [preferences_text, content]

            # Vectorize the text
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform(documents)

            # Compute cosine similarity
            similarity_matrix = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
            compatibility_score = similarity_matrix[0][0]
            self.logger.debug(f"Computed compatibility score: {compatibility_score}")
            return compatibility_score
        except Exception as e:
            self.logger.error(f"Error analyzing invitation content: {e}", exc_info=True)
            return 0.0

    def get_agent_reputation(self, agent_id):
        """
        Retrieves the reputation score of an agent.

        Args:
            agent_id (str): The ID of the agent.

        Returns:
            float: The agent's reputation score between 0 and 1.
        """
        try:
            self.logger.info(f"Retrieving reputation for agent {agent_id}")
            # For demonstration, assume we have a method to get agent reputation
            # In practice, this could involve querying a reputation system
            reputation_score = 0.8  # Placeholder value
            self.logger.debug(f"Agent {agent_id} has reputation score: {reputation_score}")
            return reputation_score
        except Exception as e:
            self.logger.error(f"Error retrieving reputation for agent {agent_id}: {e}", exc_info=True)
            return 0.0
