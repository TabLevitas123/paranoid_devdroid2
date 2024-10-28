# sub_agents/roastmaster.py

import logging
import threading
from modules.communication.communication_module import CommunicationModule
from modules.machine_learning.ml_module import MachineLearningModule
from modules.utilities.logging_manager import setup_logging

class RoastMaster:
    """
    Critiques agents' decisions to improve overall decision-making.
    """

    def __init__(self, communication_module):
        self.name = 'RoastMaster'
        self.communication_module = communication_module
        self.ml_module = MachineLearningModule()
        self.logger = setup_logging(self.name)
        self.lock = threading.Lock()
        self.logger.info(f"{self.name} initialized successfully.")

    def critique_decision(self, agent_id, decision):
        """
        Provides a critique of the agent's decision.

        Args:
            agent_id (str): Identifier of the agent.
            decision (str): The decision made by the agent.

        Returns:
            None
        """
        try:
            self.logger.info(f"Critiquing decision from agent {agent_id}: {decision}")

            # Generate critique using ML models
            critique = self.generate_critique(decision)
            self.logger.debug(f"Generated critique for agent {agent_id}: {critique}")

            # Send critique to the agent
            self.communication_module.send_message(
                sender_id=self.name,
                receiver_id=agent_id,
                message_type='critique',
                content=critique
            )
            self.logger.debug(f"Critique sent to agent {agent_id}.")
        except Exception as e:
            self.logger.error(f"Error critiquing decision from agent {agent_id}: {e}", exc_info=True)

    def generate_critique(self, decision):
        """
        Generates a detailed critique of the decision using advanced ML.

        Args:
            decision (str): The decision to critique.

        Returns:
            str: The critique message.
        """
        try:
            self.logger.debug("Generating critique using ML models.")

            # Analyze decision using ML models
            critique = self.ml_module.analyze_decision(decision)
            self.logger.debug("Critique generated successfully.")

            return critique
        except Exception as e:
            self.logger.error(f"Error generating critique: {e}", exc_info=True)
            return "An error occurred while generating the critique."
