#!/usr/bin/env python3

from enum import Enum

# Types and enums


class OperationType(Enum):
    ERR = 0x01
    SYN = 0x02
    ACK = 0x04
    SYNACK = 0x06  # Combination of SYN and ACK
    FIN = 0x08
    FINERR = 0x09  # Combination of FIN and ERR


class MessageType(Enum):
    CONTROL = 0x01
    CHAT = 0x02


# Classes
class Header:
    def __init__(self, header_data: bytes):
        self.bytes: bytes = header_data
        self.message_type: MessageType = MessageType(
            header_data[0])  # 0x01, 0x02
        self.operation: OperationType = OperationType(
            header_data[1])  # 0x01, 0x02, 0x04, 0x08
        # 0x00 or 0x01, alternating
        self.sequence_number: int = header_data[2]
        self.user: str = header_data[3:35].decode(
            'ascii')  # User name, 32 bytes, ASCII
        self.payload_size: int = int.from_bytes(
            header_data[35:39], 'big')  # Size of the payload, 4 bytes


class Payload:
    def __init__(self, payload_data: bytes):
        self.bytes: bytes = payload_data
        self.message: str = payload_data.decode('ascii')


class Datagram:
    def __init__(self, data: bytes):
        self.header: Header = Header(data[0:39])
        self.payload: bytes = Payload(data[39:])

    def __str__(self):
        return f'''Datagram:
    Message type: {self.header.message_type.name}
    Operation type: {self.header.operation.name}
    Sequence number: {self.header.sequence_number}
    From user: {self.header.user}
    Payload size: {self.header.payload_size}
    Payload: {self.payload.message}'''


# Functions
# TODO: Validate sequence on the server side
def message_to_datagram(type: MessageType, operation: OperationType, sequence_number: int, user: str, payload: str) -> bytes:
    # Check argument types are valid
    if not isinstance(type, MessageType):
        raise ValueError('Invalid message type.')
    if not isinstance(operation, OperationType):
        raise ValueError('Invalid operation type.')
    if not isinstance(sequence_number, int):
        raise ValueError('Invalid sequence_number type.')
    if not isinstance(user, str):
        raise ValueError('Invalid user type.')
    if not isinstance(payload, str):
        raise ValueError('Invalid payload type.')
    if sequence_number not in [0x00, 0x01]:
        raise ValueError('Sequence_number must be 0x00 or 0x01.')

    # Check the legths of string items
    if len(user) > 32:
        raise ValueError('User name must be 32 characters or less.')
    if len(payload) > 2**32:
        raise ValueError(
            'Payload size must be less than 2^32 bytes (FFFF FFFF).')

    # Check that strings are ASCII compatible
    if not all(ord(c) < 128 for c in user):
        raise ValueError('User name must be ASCII compatible.')
    if not all(ord(c) < 128 for c in payload):
        raise ValueError('Payload must be ASCII compatible.')

    # Check that the sequence is valid
    if sequence_number not in [0x00, 0x01]:
        raise ValueError('Sequence_number must be 0x00 or 0x01.')

    # Check combined constraints
    if type == MessageType.CONTROL:
        if operation not in [OperationType.ERR, OperationType.SYN, OperationType.ACK, OperationType.SYNACK, OperationType.FIN, OperationType.FINERR]:
            raise ValueError(
                'Control messages must have SYN, ACK, SYNACK or FIN operations.')
        if operation not in [OperationType.ERR, OperationType.FINERR] and len(payload) > 0:
            raise ValueError(
                'Non-error control messages must not have a payload.')
        if operation in [OperationType.ERR, OperationType.FINERR] and len(payload) == 0:
            raise ValueError('Error control messages must have a payload.')
    elif type == MessageType.CHAT:
        if operation != OperationType.ERR:
            raise ValueError(
                'Chat messages must have same `0x01` operation as ERR.')
        if len(payload) == 0:
            raise ValueError('Chat messages must have a payload.')

    # Return the datagram
    return bytes([type.value, operation.value, sequence_number]) + user.encode('ascii').ljust(32, b'\x00') + len(payload).to_bytes(4, 'big') + payload.encode('ascii')


# Test
# if __name__ == '__main__':
    # Test the message_to_datagram function
    # print('Testing message_to_datagram function...')
    # print('Control message (SYN)')
    # control_message = message_to_datagram(MessageType.CONTROL,
    #                                       OperationType.SYN, 0x00, 'user1', '')
    # print(control_message)
    # print(Datagram(control_message))
    # print('\nControl message (ERR)')
    # error_message = message_to_datagram(MessageType.CONTROL,
    #                                     OperationType.ERR, 0x00, 'user3', 'This is an error description')
    # print(error_message)
    # print(Datagram(error_message))
    # print('\nChat message')
    # chat_message = message_to_datagram(MessageType.CHAT,
    #                                    OperationType.ERR, 0x00, 'user5', 'Hello, world!')
    # print(chat_message)
    # print(Datagram(chat_message))
