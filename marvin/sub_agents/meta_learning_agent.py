# meta_learning_agent.py

import threading
import logging
from modules.machine_learning.meta_learning_module import MetaLearningModule
from modules.task.task_module import TaskModule
from modules.communication.communication_module import CommunicationModule
from modules.security.security_module import SecurityModule
from modules.utilities.logging_manager import setup_logging


class MetaLearningAgent:
    """
    Specializes in meta-learning to improve learning efficiency over time.
    """

    def __init__(self, agent_id, communication_module, task_module, security_module):
        self.agent_id = agent_id
        self.communication_module = communication_module
        self.task_module = task_module
        self.security_module = security_module
        self.meta_module = MetaLearningModule()
        self.logger = setup_logging(f'MetaLearningAgent_{agent_id}')
        self.lock = threading.Lock()
        self.meta_model = None
        self.logger.info(f"MetaLearningAgent {self.agent_id} initialized successfully.")

    def perform_task(self, task_description):
        """
        Performs the given task using meta-learning techniques.

        Args:
            task_description (str): Description of the task to perform.

        Returns:
            str: Result of the task execution.
        """
        try:
            self.logger.info(f"Agent {self.agent_id} performing task: {task_description}")
            task_data = self.task_module.get_task_data(task_description)
            self.logger.debug(f"Task data retrieved: {task_data}")

            if not self.meta_model:
                self.meta_model = self.meta_module.initialize_meta_model()
                self.logger.debug("Meta-model initialized.")

            # Adapt the meta-model to the new task
            adapted_model = self.meta_module.adapt_model(self.meta_model, task_data)
            self.logger.debug("Meta-model adapted to new task.")

            # Perform the task using the adapted model
            result = self.meta_module.perform_task(adapted_model, task_data)
            self.logger.debug(f"Task performed with result: {result}")

            # Update the meta-model based on performance
            self.meta_model = self.meta_module.update_meta_model(self.meta_model, adapted_model, task_data)
            self.logger.debug("Meta-model updated based on task performance.")

            self.logger.info("Meta-learning task completed successfully.")
            return result
        except Exception as e:
            self.logger.error(f"Error performing task: {e}", exc_info=True)
            return "An error occurred while performing the task."

    def receive_message(self, message):
        """
        Processes incoming messages related to meta-learning tasks.

        Args:
            message (dict): The message received.
        """
        try:
            self.logger.debug(f"Received message: {message}")
            message_type = message.get('message_type')
            sender_id = message.get('sender_id')
            content = message.get('content')

            if message_type == 'meta_model_share':
                self._handle_meta_model_share(sender_id, content)
            else:
                self.logger.warning(f"Unknown message type received: {message_type}")
        except Exception as e:
            self.logger.error(f"Error processing received message: {e}", exc_info=True)

    def _handle_meta_model_share(self, sender_id, encrypted_content):
        """
        Handles receiving a shared meta-model from another agent.

        Args:
            sender_id (str): ID of the agent sharing the meta-model.
            encrypted_content (str): The encrypted serialized meta-model.
        """
        try:
            self.logger.info(f"Receiving meta-model from agent {sender_id}")
            serialized_meta_model = self.security_module.decrypt_data(encrypted_content)
            meta_model = self.meta_module.deserialize_meta_model(serialized_meta_model)
            # Merge the received meta-model with the current meta-model
            self._merge_meta_models(meta_model)
            self.logger.info(f"Meta-model received and merged from agent {sender_id}")
        except Exception as e:
            self.logger.error(f"Error handling meta-model share from agent {sender_id}: {e}", exc_info=True)

    def _merge_meta_models(self, other_meta_model):
        """
        Merges another meta-model into the current meta-model.

        Args:
            other_meta_model: The meta-model to merge.
        """
        try:
            self.meta_model = self.meta_module.merge_meta_models(self.meta_model, other_meta_model)
            self.logger.debug("Meta-models merged successfully.")
        except Exception as e:
            self.logger.error(f"Error merging meta-models: {e}", exc_info=True)

    def share_meta_model(self, agent_id):
        """
        Shares the current meta-model with another agent.

        Args:
            agent_id (str): The ID of the agent to share the meta-model with.

        Returns:
            bool: True if meta-model shared successfully, False otherwise.
        """
        try:
            if not self.meta_model:
                self.logger.warning("No meta-model available to share.")
                return False
            self.logger.info(f"Sharing meta-model with agent {agent_id}.")
            serialized_meta_model = self.meta_module.serialize_meta_model(self.meta_model)
            encrypted_meta_model = self.security_module.encrypt_data(serialized_meta_model)
            message = {
                'sender_id': self.agent_id,
                'receiver_id': agent_id,
                'message_type': 'meta_model_share',
                'content': encrypted_meta_model
            }
            self.communication_module.send_message(message)
            self.logger.debug(f"Meta-model sent to agent {agent_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error sharing meta-model with agent {agent_id}: {e}", exc_info=True)
            return False
