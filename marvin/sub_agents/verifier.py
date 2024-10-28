# sub_agents/verifier.py

import logging
import threading
from modules.services.api_access_service import APIAccessService
from modules.machine_learning.ml_module import MachineLearningModule
from modules.utilities.logging_manager import setup_logging


class Verifier:
    """
    Verifies the correctness and validity of agents' outputs.
    """

    def __init__(self, shared_memory):
        self.name = 'Verifier'
        self.shared_memory = shared_memory
        self.api_service = APIAccessService()
        self.ml_module = MachineLearningModule()
        self.logger = setup_logging(self.name)
        self.lock = threading.Lock()
        self.logger.info(f"{self.name} initialized successfully.")

    def verify_results(self, agent_results):
        """
        Verifies a list of results from agents.

        Args:
            agent_results (list): A list of agent outputs to verify.

        Returns:
            list: A list of verified results.
        """
        verified_results = []
        threads = []

        for result in agent_results:
            thread = threading.Thread(target=self._verify_single_result, args=(result, verified_results))
            threads.append(thread)
            thread.start()
            self.logger.debug(f"Started verification thread for result: {result}")

        for thread in threads:
            thread.join()
            self.logger.debug("Verification thread joined.")

        self.logger.info("All results verified.")
        return verified_results

    def _verify_single_result(self, result, verified_results):
        """
        Verifies a single result and appends it to the verified_results list if valid.

        Args:
            result (str): The result to verify.
            verified_results (list): The shared list to append verified results to.
        """
        try:
            self.logger.debug(f"Verifying result: {result}")

            # Cross-reference with external APIs
            api_verification = self.api_service.verify_data(result)
            self.logger.debug(f"API verification result: {api_verification}")

            # Machine learning consistency check
            ml_verification = self.ml_module.verify_consistency(result)
            self.logger.debug(f"ML verification result: {ml_verification}")

            if api_verification and ml_verification:
                with self.lock:
                    verified_results.append(result)
                    self.logger.debug("Result verified and added to verified_results.")
            else:
                self.logger.warning(f"Result failed verification: {result}")

        except Exception as e:
            self.logger.error(f"Error verifying result: {e}", exc_info=True)
