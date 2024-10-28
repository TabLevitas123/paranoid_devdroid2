# deep_learning_agent.py

import threading
import logging
from modules.machine_learning.deep_learning_module import DeepLearningModule
from modules.data.data_module import DataModule
from modules.communication.communication_module import CommunicationModule
from modules.security.security_module import SecurityModule
from modules.utilities.logging_manager import setup_logging

class DeepLearningAgent:
    """
    Specializes in tasks requiring deep learning techniques.
    """

    def __init__(self, agent_id, communication_module, data_module, security_module):
        self.agent_id = agent_id
        self.communication_module = communication_module
        self.data_module = data_module
        self.security_module = security_module
        self.dl_module = DeepLearningModule()
        self.logger = setup_logging(f'DeepLearningAgent_{agent_id}')
        self.lock = threading.Lock()
        self.current_model = None
        self.logger.info(f"DeepLearningAgent {self.agent_id} initialized successfully.")

    def perform_task(self, task_description):
        """
        Performs the given task, which may involve building or using deep learning models.

        Args:
            task_description (str): Description of the task to perform.

        Returns:
            str: Result of the task execution.
        """
        try:
            self.logger.info(f"Agent {self.agent_id} performing task: {task_description}")
            task_type = self._determine_task_type(task_description)
            if task_type == 'build_model':
                result = self._build_and_train_model(task_description)
            elif task_type == 'run_inference':
                result = self._run_inference(task_description)
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
            str: The task type (e.g., 'build_model', 'run_inference').
        """
        # Placeholder logic; in practice, use NLP to parse the task description
        if 'train' in task_description.lower():
            return 'build_model'
        elif 'infer' in task_description.lower() or 'recognize' in task_description.lower():
            return 'run_inference'
        else:
            return 'unknown'

    def _build_and_train_model(self, task_description):
        """
        Builds and trains a deep learning model based on the task description.

        Args:
            task_description (str): The task description.

        Returns:
            str: Result of the training process.
        """
        try:
            self.logger.info("Building and training deep learning model.")
            dataset = self.data_module.load_data(task_description)
            self.logger.debug(f"Dataset loaded: {dataset}")
            preprocessed_data = self.data_module.preprocess_data(dataset)
            self.logger.debug("Data preprocessed successfully.")

            # Define the neural network architecture
            model_architecture = self.dl_module.define_model_architecture(task_description)
            self.logger.debug(f"Model architecture defined: {model_architecture}")

            # Train the model
            model = self.dl_module.train_model(model_architecture, preprocessed_data)
            self.current_model = model
            self.logger.info("Deep learning model trained successfully.")
            return "Deep learning model trained successfully."
        except Exception as e:
            self.logger.error(f"Error during model training: {e}", exc_info=True)
            return "An error occurred during model training."

    def _run_inference(self, task_description):
        """
        Runs inference using the current deep learning model.

        Args:
            task_description (str): The task description.

        Returns:
            str: The inference results.
        """
        try:
            if not self.current_model:
                self.logger.warning("No trained model available for inference.")
                return "No trained model available."
            self.logger.info("Running inference using the current model.")
            input_data = self.data_module.extract_input_data(task_description)
            self.logger.debug(f"Input data extracted: {input_data}")
            inference_result = self.dl_module.run_inference(self.current_model, input_data)
            self.logger.debug(f"Inference result: {inference_result}")
            return f"Inference result: {inference_result}"
        except Exception as e:
            self.logger.error(f"Error during inference: {e}", exc_info=True)
            return "An error occurred during inference."

    def optimize_model(self):
        """
        Optimizes the current model for better performance.

        Returns:
            str: Result of the optimization process.
        """
        try:
            if not self.current_model:
                self.logger.warning("No model available to optimize.")
                return "No model available."
            self.logger.info("Optimizing the current model.")
            optimized_model = self.dl_module.optimize_model(self.current_model)
            self.current_model = optimized_model
            self.logger.info("Model optimized successfully.")
            return "Model optimized successfully."
        except Exception as e:
            self.logger.error(f"Error optimizing model: {e}", exc_info=True)
            return "An error occurred while optimizing the model."

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
            serialized_model = self.dl_module.serialize_model(self.current_model)
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
        Processes incoming messages related to deep learning tasks.

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
            elif message_type == 'dataset_share':
                self._handle_dataset_share(sender_id, content)
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
            model = self.dl_module.deserialize_model(serialized_model)
            self.current_model = model
            self.logger.info(f"Model received and loaded from agent {sender_id}")
        except Exception as e:
            self.logger.error(f"Error handling model share from agent {sender_id}: {e}", exc_info=True)

    def _handle_dataset_share(self, sender_id, encrypted_content):
        """
        Handles receiving a shared dataset from another agent.

        Args:
            sender_id (str): ID of the agent sharing the dataset.
            encrypted_content (str): The encrypted dataset.
        """
        try:
            self.logger.info(f"Receiving dataset from agent {sender_id}")
            dataset = self.security_module.decrypt_data(encrypted_content)
            # Incorporate the dataset for training or updating the model
            self.data_module.add_dataset(dataset)
            self.logger.debug(f"Dataset from agent {sender_id} added to data module.")
        except Exception as e:
            self.logger.error(f"Error handling dataset share from agent {sender_id}: {e}", exc_info=True)
