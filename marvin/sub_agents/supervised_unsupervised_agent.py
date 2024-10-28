# supervised_unsupervised_agent.py

import threading
import logging
from modules.machine_learning.ml_module import MachineLearningModule
from modules.data.data_module import DataModule
from modules.communication.communication_module import CommunicationModule
from modules.security.security_module import SecurityModule
from modules.utilities.logging_manager import setup_logging


class SupervisedUnsupervisedAgent:
    """
    Handles both supervised and unsupervised learning tasks.
    """

    def __init__(self, agent_id, communication_module, data_module, security_module):
        self.agent_id = agent_id
        self.communication_module = communication_module
        self.data_module = data_module
        self.security_module = security_module
        self.ml_module = MachineLearningModule()
        self.logger = setup_logging(f'SupervisedUnsupervisedAgent_{agent_id}')
        self.lock = threading.Lock()
        self.models = {}
        self.logger.info(f"SupervisedUnsupervisedAgent {self.agent_id} initialized successfully.")

    def perform_task(self, task_description):
        """
        Performs the given task using supervised or unsupervised learning.

        Args:
            task_description (str): Description of the task to perform.

        Returns:
            str: Result of the task execution.
        """
        try:
            self.logger.info(f"Agent {self.agent_id} performing task: {task_description}")
            task_type = self._determine_task_type(task_description)
            if task_type == 'supervised':
                result = self._perform_supervised_task(task_description)
            elif task_type == 'unsupervised':
                result = self._perform_unsupervised_task(task_description)
            else:
                result = "Unknown task type."
                self.logger.warning("Unknown task type determined from task description.")
            return result
        except Exception as e:
            self.logger.error(f"Error performing task: {e}", exc_info=True)
            return "An error occurred while performing the task."

    def _determine_task_type(self, task_description):
        """
        Determines whether the task is supervised or unsupervised based on the description.

        Args:
            task_description (str): The task description.

        Returns:
            str: The task type ('supervised' or 'unsupervised').
        """
        # Placeholder logic; in practice, use NLP to parse the task description
        if 'classify' in task_description.lower() or 'regress' in task_description.lower():
            return 'supervised'
        elif 'cluster' in task_description.lower() or 'group' in task_description.lower():
            return 'unsupervised'
        else:
            return 'unknown'

    def _perform_supervised_task(self, task_description):
        """
        Performs a supervised learning task.

        Args:
            task_description (str): The task description.

        Returns:
            str: Result of the supervised task.
        """
        try:
            self.logger.info("Performing supervised learning task.")
            dataset = self.data_module.load_data(task_description)
            self.logger.debug(f"Dataset loaded: {dataset}")
            X_train, X_test, y_train, y_test = self.data_module.split_data(dataset)
            self.logger.debug("Data split into training and testing sets.")

            # Train a supervised model
            model = self.ml_module.train_supervised_model(X_train, y_train)
            self.models['supervised'] = model
            self.logger.debug("Supervised model trained.")

            # Evaluate the model
            accuracy = self.ml_module.evaluate_supervised_model(model, X_test, y_test)
            self.logger.debug(f"Model evaluated with accuracy: {accuracy}")

            return f"Supervised learning task completed with accuracy: {accuracy:.2f}"
        except Exception as e:
            self.logger.error(f"Error during supervised learning task: {e}", exc_info=True)
            return "An error occurred during the supervised learning task."

    def _perform_unsupervised_task(self, task_description):
        """
        Performs an unsupervised learning task.

        Args:
            task_description (str): The task description.

        Returns:
            str: Result of the unsupervised task.
        """
        try:
            self.logger.info("Performing unsupervised learning task.")
            dataset = self.data_module.load_data(task_description)
            self.logger.debug(f"Dataset loaded: {dataset}")
            preprocessed_data = self.data_module.preprocess_data(dataset)
            self.logger.debug("Data preprocessed.")

            # Train an unsupervised model
            model = self.ml_module.train_unsupervised_model(preprocessed_data)
            self.models['unsupervised'] = model
            self.logger.debug("Unsupervised model trained.")

            # Generate clusters or groups
            clusters = self.ml_module.predict_unsupervised_model(model, preprocessed_data)
            self.logger.debug(f"Clusters generated: {clusters}")

            return f"Unsupervised learning task completed with clusters: {clusters}"
        except Exception as e:
            self.logger.error(f"Error during unsupervised learning task: {e}", exc_info=True)
            return "An error occurred during the unsupervised learning task."

    def share_model(self, agent_id, model_type):
        """
        Shares a trained model with another agent.

        Args:
            agent_id (str): The ID of the agent to share the model with.
            model_type (str): The type of model to share ('supervised' or 'unsupervised').

        Returns:
            bool: True if model shared successfully, False otherwise.
        """
        try:
            model = self.models.get(model_type)
            if not model:
                self.logger.warning(f"No {model_type} model available to share.")
                return False
            self.logger.info(f"Sharing {model_type} model with agent {agent_id}.")
            serialized_model = self.ml_module.serialize_model(model)
            encrypted_model = self.security_module.encrypt_data(serialized_model)
            message = {
                'sender_id': self.agent_id,
                'receiver_id': agent_id,
                'message_type': f'{model_type}_model_share',
                'content': encrypted_model
            }
            self.communication_module.send_message(message)
            self.logger.debug(f"{model_type.capitalize()} model sent to agent {agent_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error sharing {model_type} model with agent {agent_id}: {e}", exc_info=True)
            return False

    def receive_message(self, message):
        """
        Processes incoming messages related to supervised or unsupervised learning tasks.

        Args:
            message (dict): The message received.
        """
        try:
            self.logger.debug(f"Received message: {message}")
            message_type = message.get('message_type')
            sender_id = message.get('sender_id')
            content = message.get('content')

            if message_type in ['supervised_model_share', 'unsupervised_model_share']:
                self._handle_model_share(sender_id, content, message_type)
            else:
                self.logger.warning(f"Unknown message type received: {message_type}")
        except Exception as e:
            self.logger.error(f"Error processing received message: {e}", exc_info=True)

    def _handle_model_share(self, sender_id, encrypted_content, message_type):
        """
        Handles receiving a shared model from another agent.

        Args:
            sender_id (str): ID of the agent sharing the model.
            encrypted_content (str): The encrypted serialized model.
            message_type (str): Type of the model being shared.
        """
        try:
            model_type = 'supervised' if 'supervised' in message_type else 'unsupervised'
            self.logger.info(f"Receiving {model_type} model from agent {sender_id}")
            serialized_model = self.security_module.decrypt_data(encrypted_content)
            model = self.ml_module.deserialize_model(serialized_model)
            self.models[model_type] = model
            self.logger.info(f"{model_type.capitalize()} model received and stored from agent {sender_id}")
        except Exception as e:
            self.logger.error(f"Error handling {model_type} model share from agent {sender_id}: {e}", exc_info=True)
