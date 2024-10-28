# machine_learning_agent.py

import threading
import logging
from modules.machine_learning.ml_module import MachineLearningModule
from modules.data.data_module import DataModule
from modules.communication.communication_module import CommunicationModule
from modules.security.security_module import SecurityModule
from modules.utilities.logging_manager import setup_logging

class MachineLearningAgent:
    """
    Specializes in tasks requiring machine learning capabilities.
    """

    def __init__(self, agent_id, communication_module, data_module, security_module):
        self.agent_id = agent_id
        self.communication_module = communication_module
        self.data_module = data_module
        self.security_module = security_module
        self.ml_module = MachineLearningModule()
        self.logger = setup_logging(f'MachineLearningAgent_{agent_id}')
        self.lock = threading.Lock()
        self.current_model = None
        self.logger.info(f"MachineLearningAgent {self.agent_id} initialized successfully.")

    def perform_task(self, task_description):
        """
        Performs the given task, which may involve training or using a machine learning model.

        Args:
            task_description (str): Description of the task to perform.

        Returns:
            str: Result of the task execution.
        """
        try:
            self.logger.info(f"Agent {self.agent_id} performing task: {task_description}")
            task_type = self._determine_task_type(task_description)
            if task_type == 'train_model':
                result = self._train_model(task_description)
            elif task_type == 'make_prediction':
                result = self._make_prediction(task_description)
            else:
                result = "Unknown task type."
                self.logger.warning("Unknown task type determined from task description.")
            return result
        except Exception as e:
            self.logger.error(f"Error performing task: {e}", exc_info=True)
            return "An error occurred while performing the task."

    def _determine_task_type(self, task_description):
        """
        Determines the type of task based on the description.

        Args:
            task_description (str): The task description.

        Returns:
            str: The task type (e.g., 'train_model', 'make_prediction').
        """
        # Placeholder logic; in practice, use NLP to parse the task description
        if 'train' in task_description.lower():
            return 'train_model'
        elif 'predict' in task_description.lower():
            return 'make_prediction'
        else:
            return 'unknown'

    def _train_model(self, task_description):
        """
        Trains a machine learning model based on the task description.

        Args:
            task_description (str): The task description.

        Returns:
            str: Result of the training process.
        """
        try:
            self.logger.info("Starting model training.")
            dataset = self.data_module.load_data(task_description)
            self.logger.debug(f"Dataset loaded: {dataset}")
            preprocessed_data = self.data_module.preprocess_data(dataset)
            self.logger.debug("Data preprocessed successfully.")
            model = self.ml_module.train_model(preprocessed_data)
            self.current_model = model
            self.logger.info("Model trained successfully.")
            return "Model trained successfully."
        except Exception as e:
            self.logger.error(f"Error during model training: {e}", exc_info=True)
            return "An error occurred during model training."

    def _make_prediction(self, task_description):
        """
        Makes predictions using the current model.

        Args:
            task_description (str): The task description.

        Returns:
            str: The prediction results.
        """
        try:
            if not self.current_model:
                self.logger.warning("No trained model available for making predictions.")
                return "No trained model available."
            self.logger.info("Making predictions using the current model.")
            input_data = self.data_module.extract_input_data(task_description)
            self.logger.debug(f"Input data extracted: {input_data}")
            prediction = self.ml_module.make_prediction(self.current_model, input_data)
            self.logger.debug(f"Prediction result: {prediction}")
            return f"Prediction result: {prediction}"
        except Exception as e:
            self.logger.error(f"Error during prediction: {e}", exc_info=True)
            return "An error occurred during prediction."

    def update_model(self, new_data):
        """
        Updates the current model with new data for continuous learning.

        Args:
            new_data (dict): The new data to update the model with.

        Returns:
            str: Result of the model update process.
        """
        try:
            self.logger.info("Updating model with new data.")
            preprocessed_data = self.data_module.preprocess_data(new_data)
            self.ml_module.update_model(self.current_model, preprocessed_data)
            self.logger.info("Model updated successfully.")
            return "Model updated successfully."
        except Exception as e:
            self.logger.error(f"Error updating model: {e}", exc_info=True)
            return "An error occurred while updating the model."

    def share_model(self, agent_id):
        """
        Shares the current model with another agent.

        Args:
            agent_id (str): The ID of the agent to share the model with.

        Returns:
            bool: True if model shared successfully, False otherwise.
        """
        try:
            if not self.current_model:
                self.logger.warning("No trained model available to share.")
                return False
            self.logger.info(f"Sharing model with agent {agent_id}.")
            serialized_model = self.ml_module.serialize_model(self.current_model)
            encrypted_model = self.security_module.encrypt_data(serialized_model)
            message = {
                'sender_id': self.agent_id,
                'receiver_id': agent_id,
                'message_type': 'model_share',
                'content': encrypted_model
            }
            self.communication_module.send_message(message)
            self.logger.debug(f"Model sent to agent {agent_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error sharing model with agent {agent_id}: {e}", exc_info=True)
            return False

    def receive_message(self, message):
        """
        Processes incoming messages related to machine learning tasks.

        Args:
            message (dict): The message received.
        """
        try:
            self.logger.debug(f"Received message: {message}")
            message_type = message.get('message_type')
            sender_id = message.get('sender_id')
            content = message.get('content')

            if message_type == 'model_share':
                self._handle_model_share(sender_id, content)
            elif message_type == 'data_share':
                self._handle_data_share(sender_id, content)
            else:
                self.logger.warning(f"Unknown message type received: {message_type}")
        except Exception as e:
            self.logger.error(f"Error processing received message: {e}", exc_info=True)

    def _handle_model_share(self, sender_id, encrypted_content):
        """
        Handles receiving a shared model from another agent.

        Args:
            sender_id (str): ID of the agent sharing the model.
            encrypted_content (str): The encrypted serialized model.
        """
        try:
            self.logger.info(f"Receiving model from agent {sender_id}")
            serialized_model = self.security_module.decrypt_data(encrypted_content)
            model = self.ml_module.deserialize_model(serialized_model)
            self.current_model = model
            self.logger.info(f"Model received and loaded from agent {sender_id}")
        except Exception as e:
            self.logger.error(f"Error handling model share from agent {sender_id}: {e}", exc_info=True)

    def _handle_data_share(self, sender_id, encrypted_content):
        """
        Handles receiving shared data from another agent.

        Args:
            sender_id (str): ID of the agent sharing data.
            encrypted_content (str): The encrypted data.
        """
        try:
            self.logger.info(f"Receiving data from agent {sender_id}")
            data = self.security_module.decrypt_data(encrypted_content)
            # Process and incorporate the data
            self.update_model(data)
            self.logger.debug(f"Data from agent {sender_id} processed and model updated.")
        except Exception as e:
            self.logger.error(f"Error handling data share from agent {sender_id}: {e}", exc_info=True)
