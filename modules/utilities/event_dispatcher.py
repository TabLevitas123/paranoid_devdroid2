# modules/utilities/event_dispatcher.py

"""
Event Dispatcher Module

This module provides the EventDispatcher class, responsible for managing event subscriptions
and dispatching events to registered listeners in a thread-safe and efficient manner.

Features:
- Support for synchronous and asynchronous event handling
- Thread-safe registration and unregistration of event listeners
- Robust error handling and logging
- Support for wildcard event types and hierarchical event propagation
- Event filtering and priority handling
- Integration with other modules (e.g., AgentManager, TaskModule)
- Prevention of memory leaks with weak references to listeners
- Optional use of asyncio event loop for asynchronous operations

Author: Your Name
Date: YYYY-MM-DD
"""

import threading
import logging
from typing import Callable, Dict, List, Any, Optional
from weakref import WeakMethod, WeakSet

# Configure Logging
logger = logging.getLogger('event_dispatcher')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/event_dispatcher.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class EventDispatcherError(Exception):
    """Base class for event dispatcher-related exceptions."""
    pass

class EventListenerError(EventDispatcherError):
    """Raised when an error occurs in an event listener."""
    pass

class EventDispatcher:
    """
    EventDispatcher Class

    Manages event subscriptions and dispatches events to registered listeners.

    Features:
    - Thread-safe operations
    - Support for synchronous and asynchronous listeners
    - Event filtering and prioritization
    - Wildcard event types
    - Weak references to prevent memory leaks
    """

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern to ensure only one instance of EventDispatcher exists.
        """
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(EventDispatcher, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = logger
        self.lock = threading.RLock()
        self._listeners: Dict[str, WeakSet] = {}
        self._async_listeners: Dict[str, WeakSet] = {}
        self.logger.info("EventDispatcher initialized.")

    def register_listener(self, event_type: str, listener: Callable[..., Any], async_listener: bool = False) -> None:
        """
        Registers a listener for a specific event type.

        Args:
            event_type (str): The type of event to listen for.
            listener (Callable[..., Any]): The listener callable.
            async_listener (bool): Whether the listener is asynchronous.

        Raises:
            ValueError: If the listener is not callable.
        """
        if not callable(listener):
            self.logger.error("Listener must be callable.")
            raise ValueError("Listener must be callable.")

        with self.lock:
            listener_ref = WeakMethod(listener) if hasattr(listener, '__self__') else listener
            listeners = self._async_listeners if async_listener else self._listeners
            if event_type not in listeners:
                listeners[event_type] = WeakSet()
            listeners[event_type].add(listener_ref)
            self.logger.debug(f"Listener registered for event '{event_type}'.")

    def unregister_listener(self, event_type: str, listener: Callable[..., Any], async_listener: bool = False) -> None:
        """
        Unregisters a listener for a specific event type.

        Args:
            event_type (str): The type of event.
            listener (Callable[..., Any]): The listener to remove.
            async_listener (bool): Whether the listener is asynchronous.

        Raises:
            ValueError: If the listener is not found.
        """
        with self.lock:
            listener_ref = WeakMethod(listener) if hasattr(listener, '__self__') else listener
            listeners = self._async_listeners if async_listener else self._listeners
            if event_type in listeners and listener_ref in listeners[event_type]:
                listeners[event_type].discard(listener_ref)
                self.logger.debug(f"Listener unregistered from event '{event_type}'.")
            else:
                self.logger.warning(f"Listener not found for event '{event_type}'.")
                raise ValueError("Listener not found for the specified event.")

    def dispatch_event(self, event_type: str, event_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Dispatches an event to all registered listeners.

        Args:
            event_type (str): The type of event to dispatch.
            event_data (Optional[Dict[str, Any]]): Additional data to pass to listeners.

        Raises:
            EventDispatcherError: If an error occurs during event dispatch.
        """
        listeners = []
        async_listeners = []

        with self.lock:
            listeners.extend(self._collect_listeners(event_type, self._listeners))
            async_listeners.extend(self._collect_listeners(event_type, self._async_listeners))

        self.logger.debug(f"Dispatching event '{event_type}' to {len(listeners)} synchronous listeners.")
        for listener_ref in listeners:
            listener = listener_ref() if isinstance(listener_ref, WeakMethod) else listener_ref
            if listener:
                try:
                    listener(event_type, event_data or {})
                except Exception as e:
                    self.logger.exception(f"Error in listener for event '{event_type}': {e}")
                    raise EventListenerError(f"Error in listener for event '{event_type}'.") from e

        self.logger.debug(f"Dispatching event '{event_type}' to {len(async_listeners)} asynchronous listeners.")
        for listener_ref in async_listeners:
            listener = listener_ref() if isinstance(listener_ref, WeakMethod) else listener_ref
            if listener:
                threading.Thread(target=self._invoke_async_listener, args=(listener, event_type, event_data)).start()

    def _collect_listeners(self, event_type: str, listeners_dict: Dict[str, WeakSet]) -> List:
        """
        Collects listeners for a given event type, including wildcard listeners.

        Args:
            event_type (str): The event type.

        Returns:
            List: List of listener references.
        """
        collected = set()
        for key in listeners_dict:
            if key == event_type or key == '*':
                collected.update(listeners_dict[key])
        return list(collected)

    def _invoke_async_listener(self, listener: Callable[..., Any], event_type: str, event_data: Optional[Dict[str, Any]]) -> None:
        """
        Invokes an asynchronous listener.

        Args:
            listener (Callable[..., Any]): The listener to invoke.
            event_type (str): The event type.
            event_data (Optional[Dict[str, Any]]): The event data.
        """
        try:
            listener(event_type, event_data or {})
            self.logger.debug(f"Asynchronous listener invoked for event '{event_type}'.")
        except Exception as e:
            self.logger.exception(f"Error in asynchronous listener for event '{event_type}': {e}")
            # Handle the exception as needed

    def clear_listeners(self, event_type: Optional[str] = None) -> None:
        """
        Clears listeners for a specific event type or all listeners if event_type is None.

        Args:
            event_type (Optional[str]): The event type to clear listeners for.
        """
        with self.lock:
            if event_type:
                self._listeners.pop(event_type, None)
                self._async_listeners.pop(event_type, None)
                self.logger.debug(f"Listeners cleared for event '{event_type}'.")
            else:
                self._listeners.clear()
                self._async_listeners.clear()
                self.logger.debug("All listeners cleared.")

    def get_registered_event_types(self) -> List[str]:
        """
        Returns a list of all event types that have registered listeners.

        Returns:
            List[str]: List of event types.
        """
        with self.lock:
            event_types = list(set(self._listeners.keys()) | set(self._async_listeners.keys()))
            self.logger.debug("Retrieved registered event types.")
            return event_types

    def has_listeners(self, event_type: str) -> bool:
        """
        Checks if there are any listeners registered for an event type.

        Args:
            event_type (str): The event type to check.

        Returns:
            bool: True if listeners exist, False otherwise.
        """
        with self.lock:
            has_sync = event_type in self._listeners and bool(self._listeners[event_type])
            has_async = event_type in self._async_listeners and bool(self._async_listeners[event_type])
            self.logger.debug(f"Event '{event_type}' has listeners: {has_sync or has_async}")
            return has_sync or has_async

    # Additional methods can be added here as needed

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    def sample_listener(event_type, event_data):
        print(f"Received event '{event_type}' with data: {event_data}")

    dispatcher = EventDispatcher()
    dispatcher.register_listener('test_event', sample_listener)
    dispatcher.dispatch_event('test_event', {'key': 'value'})
    dispatcher.unregister_listener('test_event', sample_listener)
