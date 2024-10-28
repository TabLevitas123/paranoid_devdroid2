# rlhf_agent.py

import threading
import logging
import random
from modules.machine_learning.rlhf_module import RLHFModule
from modules.communication.communication_module import CommunicationModule
from modules.security.security_module import SecurityModule
from modules.services.feedback_service import FeedbackService
from modules.utilities.logging_manager import setup_logging


class RLHFAgent:
    """
    Specializes in Reinforcement Learning from Human Feedback (RLHF).
    """

    def __init__(self, agent_id, communication_module, feedback_module, security_module):
        self.agent_id = agent_id
        self.communication_module = communication_module
        self.feedback_module = feedback_module
        self.security_module = security_module
        self.rlhf_module = RLHFModule()
        self.logger = setup_logging(f'RLHFAgent_{agent_id}')
        self.lock = threading.Lock()
        self.policy = None
        self.logger.info(f"RLHFAgent {self.agent_id} initialized successfully.")

    def perform_task(self, task_description):
        """
        Performs the given task using RLHF.

        Args:
            task_description (str): Description of the task to perform.

        Returns:
            str: Result of the task execution.
        """
        try:
            self.logger.info(f"Agent {self.agent_id} performing task: {task_description}")

            # Initialize policy if not already done
            if not self.policy:
                self.policy = self.rlhf_module.initialize_policy()
                self.logger.debug("Policy initialized.")

            # Generate initial output
            output = self.rlhf_module.generate_output(self.policy, task_description)
            self.logger.debug(f"Initial output generated: {output}")

            # Collect human feedback
            feedback = self.feedback_module.collect_feedback(output)
            self.logger.debug(f"Feedback received: {feedback}")

            # Update policy based on feedback
            self.policy = self.rlhf_module.update_policy(self.policy, feedback)
            self.logger.debug("Policy updated based on feedback.")

            # Generate improved output
            improved_output = self.rlhf_module.generate_output(self.policy, task_description)
            self.logger.debug(f"Improved output generated: {improved_output}")

            self.logger.info("RLHF task completed successfully.")
            return improved_output
        except Exception as e:
            self.logger.error(f"Error performing task: {e}", exc_info=True)
            return "An error occurred while performing the task."

    def receive_message(self, message):
        """
        Processes incoming messages related to RLHF tasks.

        Args:
            message (dict): The message received.
        """
        try:
            self.logger.debug(f"Received message: {message}")
            message_type = message.get('message_type')
            sender_id = message.get('sender_id')
            content = message.get('content')

            if message_type == 'policy_share':
                self._handle_policy_share(sender_id, content)
            else:
                self.logger.warning(f"Unknown message type received: {message_type}")
        except Exception as e:
            self.logger.error(f"Error processing received message: {e}", exc_info=True)

    def _handle_policy_share(self, sender_id, encrypted_content):
        """
        Handles receiving a shared policy from another agent.

        Args:
            sender_id (str): ID of the agent sharing the policy.
            encrypted_content (str): The encrypted serialized policy.
        """
        try:
            self.logger.info(f"Receiving policy from agent {sender_id}")
            serialized_policy = self.security_module.decrypt_data(encrypted_content)
            policy = self.rlhf_module.deserialize_policy(serialized_policy)
            # Merge the received policy with the current policy
            self._merge_policies(policy)
            self.logger.info(f"Policy received and merged from agent {sender_id}")
        except Exception as e:
            self.logger.error(f"Error handling policy share from agent {sender_id}: {e}", exc_info=True)

    def _merge_policies(self, other_policy):
        """
        Merges another policy into the current policy.

        Args:
            other_policy: The policy to merge.
        """
        try:
            self.policy = self.rlhf_module.merge_policies(self.policy, other_policy)
            self.logger.debug("Policies merged successfully.")
        except Exception as e:
            self.logger.error(f"Error merging policies: {e}", exc_info=True)

    def share_policy(self, agent_id):
        """
        Shares the current policy with another agent.

        Args:
            agent_id (str): The ID of the agent to share the policy with.

        Returns:
            bool: True if policy shared successfully, False otherwise.
        """
        try:
            if not self.policy:
                self.logger.warning("No policy available to share.")
                return False
            self.logger.info(f"Sharing policy with agent {agent_id}.")
            serialized_policy = self.rlhf_module.serialize_policy(self.policy)
            encrypted_policy = self.security_module.encrypt_data(serialized_policy)
            message = {
                'sender_id': self.agent_id,
                'receiver_id': agent_id,
                'message_type': 'policy_share',
                'content': encrypted_policy
            }
            self.communication_module.send_message(message)
            self.logger.debug(f"Policy sent to agent {agent_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error sharing policy with agent {agent_id}: {e}", exc_info=True)
            return False
