# sub_agents/interrogator.py

import logging
import threading
from modules.communication.communication_module import CommunicationModule
from modules.utilities.logging_manager import setup_logging

class Interrogator:
    """
    Questions agents about their decisions to ensure optimal choices.
    """

    def __init__(self, communication_module):
        self.name = 'Interrogator'
        self.communication_module = communication_module
        self.logger = setup_logging(self.name)
        self.lock = threading.Lock()
        self.logger.info(f"{self.name} initialized successfully.")

    def interrogate_agent(self, agent_id, decision):
        """
        Sends an interrogation message to an agent regarding its decision.

        Args:
            agent_id (str): Identifier of the agent.
            decision (str): The decision made by the agent.

        Returns:
            str: The agent's explanation or None if no response.
        """
        try:
            self.logger.info(f"Interrogating agent {agent_id} about decision: {decision}")

            # Send interrogation message
            self.communication_module.send_message(
                sender_id=self.name,
                receiver_id=agent_id,
                message_type='interrogation',
                content=f"Please explain your decision: '{decision}'"
            )
            self.logger.debug(f"Interrogation message sent to agent {agent_id}.")

            # Wait for response with a timeout
            response = self.communication_module.receive_message(
                receiver_id=self.name,
                expected_message_type='explanation',
                timeout=15  # seconds
            )

            if response and response.get('sender_id') == agent_id:
                explanation = response.get('content')
                self.logger.debug(f"Received explanation from agent {agent_id}: {explanation}")
                self.evaluate_explanation(agent_id, decision, explanation)
                return explanation
            else:
                self.logger.warning(f"No explanation received from agent {agent_id} within timeout.")
                return None
        except Exception as e:
            self.logger.error(f"Error interrogating agent {agent_id}: {e}", exc_info=True)
            return None

    def evaluate_explanation(self, agent_id, decision, explanation):
        """
        Evaluates the agent's explanation to determine its adequacy.

        Args:
            agent_id (str): Identifier of the agent.
            decision (str): The decision made by the agent.
            explanation (str): The agent's explanation of the decision.

        Returns:
            bool: True if explanation is satisfactory, False otherwise.
        """
        try:
            self.logger.info(f"Evaluating explanation from agent {agent_id}.")

            # Implement evaluation logic (e.g., check for completeness, relevance)
            is_satisfactory = len(explanation) > 50  # Example criterion
            if is_satisfactory:
                self.logger.debug(f"Explanation from agent {agent_id} is satisfactory.")
                return True
            else:
                self.logger.warning(f"Explanation from agent {agent_id} is unsatisfactory.")
                # Optionally, request further clarification
                self.request_clarification(agent_id, decision)
                return False
        except Exception as e:
            self.logger.error(f"Error evaluating explanation from agent {agent_id}: {e}", exc_info=True)
            return False

    def request_clarification(self, agent_id, decision):
        """
        Requests further clarification from the agent.

        Args:
            agent_id (str): Identifier of the agent.
            decision (str): The decision needing clarification.
        """
        try:
            self.logger.info(f"Requesting clarification from agent {agent_id}.")

            self.communication_module.send_message(
                sender_id=self.name,
                receiver_id=agent_id,
                message_type='clarification_request',
                content=f"Your explanation for decision '{decision}' was insufficient. Please provide more details."
            )
            self.logger.debug(f"Clarification request sent to agent {agent_id}.")
        except Exception as e:
            self.logger.error(f"Error requesting clarification from agent {agent_id}: {e}", exc_info=True)
