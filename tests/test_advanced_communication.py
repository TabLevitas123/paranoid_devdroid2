# tests/test_advanced_communication.py

"""
Advanced Unit Tests for CommunicationModule

This module contains advanced unit tests for the CommunicationModule class,
including stress testing, concurrent message handling, and security compliance.
"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from modules.communication.communication_module import CommunicationModule, CommunicationModuleError
from modules.security.encryption_manager import EncryptionManager
from modules.communication.message_broker import MessageBroker
from modules.utilities.logging_manager import setup_logging


@pytest.fixture
def mock_encryption_manager():
    with patch('modules.communication.communication_module.EncryptionManager') as mock_enc:
        instance = mock_enc.return_value
        instance.encrypt_data = MagicMock(side_effect=lambda x: f"encrypted_{x}")
        instance.decrypt_data = MagicMock(side_effect=lambda x: x.replace("encrypted_", ""))
        yield instance


@pytest.fixture
def mock_message_broker():
    with patch('modules.communication.communication_module.MessageBroker') as mock_mb:
        instance = mock_mb.return_value
        instance.publish_message = MagicMock()
        instance.consume_message = MagicMock(return_value=None)
        instance.publish_broadcast = MagicMock()
        instance.consume_broadcast = MagicMock(return_value=None)
        instance.create_group = MagicMock()
        instance.publish_group_message = MagicMock()
        instance.consume_group_message = MagicMock(return_value=None)
        yield instance


@pytest.fixture
def communication_module(mock_encryption_manager, mock_message_broker):
    cm = CommunicationModule()
    yield cm


def test_concurrent_send_messages(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test sending multiple messages concurrently to ensure thread safety and performance.
    """
    def send_messages(sender, receiver, count):
        for i in range(count):
            communication_module.send_message(
                sender_id=sender,
                receiver_id=receiver,
                message_type="task",
                content={"action": f"task_{i}"}
            )

    threads = []
    num_threads = 5
    messages_per_thread = 10

    for t in range(num_threads):
        thread = threading.Thread(target=send_messages, args=(f"agent_{t}", f"agent_{t+1}", messages_per_thread))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    assert mock_message_broker.publish_message.call_count == num_threads * messages_per_thread
    for t in range(num_threads):
        for i in range(messages_per_thread):
            mock_message_broker.publish_message.assert_any_call(
                f"agent_{t+1}",
                {
                    'message_id': pytest.any(str),
                    'timestamp': pytest.any(float),
                    'sender_id': f"agent_{t}",
                    'receiver_id': f"agent_{t+1}",
                    'message_type': "task",
                    'content': f"encrypted_{{'action': 'task_{i}'}}"
                }
            )


def test_concurrent_receive_messages(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test receiving multiple messages concurrently to ensure thread safety and performance.
    """
    mock_message_broker.consume_message.side_effect = [
        {
            'message_id': f'msg_{i}',
            'timestamp': time.time(),
            'sender_id': 'agent_sender',
            'receiver_id': 'agent_receiver',
            'message_type': 'task',
            'content': f"encrypted_{{'action': 'task_{i}'}}"
        } for i in range(20)
    ] + [None]*5  # To simulate no more messages

    received_messages = []

    def receive_messages(receiver, count):
        for _ in range(count):
            msg = communication_module.receive_message(
                receiver_id=receiver,
                message_type_filter="task",
                timeout=2
            )
            if msg:
                received_messages.append(msg)

    threads = []
    num_threads = 4
    messages_per_thread = 5

    for t in range(num_threads):
        thread = threading.Thread(target=receive_messages, args=("agent_receiver", messages_per_thread))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    assert len(received_messages) == num_threads * messages_per_thread
    for i, msg in enumerate(received_messages):
        assert msg['message_id'] == f'msg_{i}'
        assert msg['sender_id'] == 'agent_sender'
        assert msg['receiver_id'] == 'agent_receiver'
        assert msg['message_type'] == 'task'
        assert msg['content'] == f"{{'action': 'task_{i}'}}"


def test_security_compliance(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test that all messages are encrypted and decrypted properly to ensure security compliance.
    """
    message_content = {"action": "secure_task", "data": "Sensitive information"}
    communication_module.send_message(
        sender_id="agent_secure",
        receiver_id="agent_secure_receiver",
        message_type="secure_task",
        content=message_content
    )
    mock_encryption_manager.encrypt_data.assert_called_once_with(message_content)
    mock_message_broker.publish_message.assert_called_once()
    args, kwargs = mock_message_broker.publish_message.call_args
    receiver_id_arg, message_arg = args
    assert message_arg['content'] == "encrypted_{'action': 'secure_task', 'data': 'Sensitive information'}"

    # Simulate receiving the message
    mock_message = {
        'message_id': 'msg_secure_001',
        'timestamp': time.time(),
        'sender_id': 'agent_secure',
        'receiver_id': 'agent_secure_receiver',
        'message_type': 'secure_task',
        'content': "encrypted_{'action': 'secure_task', 'data': 'Sensitive information'}"
    }
    mock_message_broker.consume_message.return_value = mock_message

    received_message = communication_module.receive_message(
        receiver_id="agent_secure_receiver",
        message_type_filter="secure_task",
        timeout=5
    )

    mock_encryption_manager.decrypt_data.assert_called_once_with("encrypted_{'action': 'secure_task', 'data': 'Sensitive information'}")
    assert received_message['content'] == "{'action': 'secure_task', 'data': 'Sensitive information'}"


def test_listener_invocation(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test that registered listeners are invoked upon receiving messages.
    """
    received = []

    def listener_callback(message):
        received.append(message)

    communication_module.register_listener("agent_listener", listener_callback)

    mock_message = {
        'message_id': 'msg_listener_001',
        'timestamp': time.time(),
        'sender_id': 'agent_sender',
        'receiver_id': 'agent_listener',
        'message_type': 'task',
        'content': "encrypted_{'action': 'listen_task'}"
    }
    mock_message_broker.consume_message.return_value = mock_message

    # Allow some time for the listener thread to process the message
    time.sleep(2)

    assert len(received) == 1
    assert received[0]['message_id'] == 'msg_listener_001'
    assert received[0]['sender_id'] == 'agent_sender'
    assert received[0]['receiver_id'] == 'agent_listener'
    assert received[0]['message_type'] == 'task'
    assert received[0]['content'] == "{'action': 'listen_task'}"

    communication_module.unregister_listener("agent_listener")


def test_broadcast_message_concurrent_consumption(communication_module, mock_encryption_manager, mock_message_broker):
    """
    Test that broadcast messages are consumed correctly by multiple agents concurrently.
    """
    broadcast_message = {
        'message_id': 'msg_broadcast_002',
        'timestamp': time.time(),
        'sender_id': 'agent_admin',
        'receiver_id': 'ALL',
        'message_type': 'announcement',
        'content': "encrypted_{'info': 'New policy updates available.'}"
    }
    communication_module.broadcast_message(
        sender_id="agent_admin",
        message_type="announcement",
        content={"info": "New policy updates available."}
    )
    mock_encryption_manager.encrypt_data.assert_called_once_with({"info": "New policy updates available."})
    mock_message_broker.publish_broadcast.assert_called_once_with(broadcast_message)

    received_messages = []

    def consume_broadcast(receiver):
        msg = communication_module.message_broker.consume_broadcast(receiver)
        if msg:
            decrypted_content = communication_module.encryption_manager.decrypt_data(msg['content'])
            msg['content'] = decrypted_content
            received_messages.append(msg)

    agents = ["agent_10", "agent_11", "agent_12"]
    threads = []
    for agent in agents:
        thread = threading.Thread(target=consume_broadcast, args=(agent,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    assert len(received_messages) == len(agents)
    for msg in received_messages:
        assert msg['message_id'] == 'msg_broadcast_002'
        assert msg['sender_id'] == 'agent_admin'
        assert msg['receiver_id'] == 'ALL'
        assert msg['message_type'] == 'announcement'
        assert msg['content'] == "{'info': 'New policy updates available.'}"
