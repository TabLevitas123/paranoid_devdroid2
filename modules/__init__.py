# modules/__init__.py

"""
Initialization of the modules package.
"""

# Import submodules to make them accessible when importing the modules package
from .communication import CommunicationModule, AdvancedCommunication, MessageBroker
# Note: Other modules (memory, machine_learning, etc.) would be imported similarly

__all__ = [
    'communication',
    # 'memory',
    # 'machine_learning',
    # 'user_interface',
    # 'security',
    # 'utilities',
    # 'services',
]
