# sub_agents/decider.py

import logging
from modules.machine_learning.decision_module import DecisionModule
from modules.utilities.logging_manager import setup_logging


class Decider:
    """
    Makes the final decision based on verified agent results.
    """

    def __init__(self):
        self.name = 'Decider'
        self.decision_module = DecisionModule()
        self.logger = setup_logging(self.name)
        self.logger.info(f"{self.name} initialized successfully.")

    def decide(self, verified_results):
        """
        Decides on the best result from the list of verified results.

        Args:
            verified_results (list): A list of verified agent results.

        Returns:
            str: The final decision.
        """
        try:
            self.logger.info("Starting decision-making process.")
            if not verified_results:
                self.logger.warning("No verified results provided to Decider.")
                return "No valid results to decide upon."

            self.logger.debug(f"Verified results: {verified_results}")

            # Use advanced decision algorithms
            final_decision = self.decision_module.select_best_result(verified_results)
            self.logger.info(f"Final decision made: {final_decision}")

            return final_decision

        except Exception as e:
            self.logger.error(f"Error in decision-making: {e}", exc_info=True)
            return "An error occurred during decision-making."
