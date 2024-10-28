# marvin/agent_manager.py

import logging
from modules.utilities.logging_manager import setup_logging
from marvin.sub_agents.hallucination_monitor import HallucinationMonitor
from marvin.sub_agents.interrogator import Interrogator
from marvin.sub_agents.roastmaster import Roastmaster
from marvin.sub_agents.verifier import Verifier
from marvin.sub_agents.decider import Decider
from marvin.sub_agents.expert_panel import ExpertPanel


class AgentManager:
    def __init__(self, communication_module, shared_memory, encryption_manager, llm_service):
        self.communication_module = communication_module
        self.shared_memory = shared_memory
        self.encryption_manager = encryption_manager
        self.llm_service = llm_service
        self.logger = setup_logging('AgentManager')
        self.logger.info("AgentManager initialized.")

    def create_agents(self, task):
        agents = []

        # Expert Panel
        expert_panel = ExpertPanel(self.llm_service, task)
        agents.append(expert_panel)

        # Hallucination Monitor
        hallucination_monitor = HallucinationMonitor(self.shared_memory)
        agents.append(hallucination_monitor)

        # Verifier
        verifier = Verifier(self.llm_service)
        agents.append(verifier)

        # Interrogator
        interrogator = Interrogator(self.communication_module)
        agents.append(interrogator)

        # Roastmaster
        roastmaster = Roastmaster(self.communication_module)
        agents.append(roastmaster)

        # Decider
        decider = Decider()
        agents.append(decider)

        self.logger.debug(f"Agents created: {[agent.name for agent in agents]}")
        return agents

    def decide(self, results):
        try:
            decider = Decider()
            final_decision = decider.decide(results)
            self.logger.debug(f"Decider output: {final_decision}")
            return final_decision
        except Exception as e:
            self.logger.error(f"Error in decision-making: {e}", exc_info=True)
            return "An error occurred during decision-making."
