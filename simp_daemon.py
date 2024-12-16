import socket
import threading
import sys
import time
import random
from typing import Optional, Tuple

from simp_classes import Datagram, MessageType, OperationType, message_to_datagram


class Daemon:
    def __init__(self, host: str) -> None:
        self.host: str = host
        self.username: Optional[str] = None
        # Used for surpressing the "Daemon listener thread shutdown." message for the first time
        self.has_been_connected: bool = False

        # Create a UDP socket - for DAEMON to DAEMON communication
        self.daemon_socket: socket.socket = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM)
        self.daemon_socket.bind((self.host, 7777))
        self.send_sequence_number: int = 0x00  # For sending datagrams
        self.expected_sequence_number: int = 0x00  # For receiving datagrams

        # TCP socket and details for DAEMON to CLIENT conenction
        self.client_socket: socket.socket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self.client_conn: Optional[socket.socket] = None
        self.client_is_connected: bool = False
        self.client_lock: threading.Lock = threading.Lock()
        # Start listening for client connections
        self.client_socket.bind((self.host, 7778))
        self.client_socket.listen()

        # Invitation related
        self.pending_invitation: bool = False
        self.inviting_user: Optional[str] = None
        self.inviting_addr: Optional[str] = None

        # Chat related
        self.remote_addr: Optional[Tuple[str, int]] = None
        self.is_in_chat: bool = False

    # Send a datagram and wait for an ACK of the message
    def send_with_retransmission(self, datagram: bytes, addr: Tuple[str, int], skip_sequence_check: bool = False) -> bool:
        max_retries: int = 3
        timeout: int = 5  # seconds
        retries: int = 0
        drop_probability: float = 0.25
        sequence_number: int = Datagram(datagram).header.sequence_number

        while retries < max_retries:
            # Simulate packet loss
            if random.random() > drop_probability:
                self.daemon_socket.sendto(datagram, addr)
            print(
                f"\n----------->\nDAEMON (Attempt #{retries + 1}): Sending datagram {addr}:\n{Datagram(datagram)}\n----------->\n")
            start_time: float = time.time()
            self.daemon_socket.settimeout(timeout)
            try:
                while True:
                    time_elapsed: float = time.time() - start_time
                    if time_elapsed > timeout:
                        raise socket.timeout
                    response, _ = self.daemon_socket.recvfrom(1024)
                    ack = Datagram(response)
                    print(
                        f"\n<-----------\nDAEMON: Received datagram from {addr}:\n{ack}\n<-----------\n")
                    # If the ACK is coming from a third party being rejected, skip the sequence number check and switch
                    if ack.header.operation == OperationType.ACK and skip_sequence_check:
                        return True
                    # Handle sequence number validation and switch sequence numbers
                    if (ack.header.operation == OperationType.ACK and ack.header.sequence_number == sequence_number):
                        self.send_sequence_number = 0x01 if self.send_sequence_number == 0x00 else 0x00
                        self.expected_sequence_number = 0x01 if self.expected_sequence_number == 0x00 else 0x00
                        self.daemon_socket.settimeout(None)
                        return True  # Message was successfully sent, and correct ACK received
            except socket.timeout:
                retries += 1
                print(f"Timeout waiting for ACK. Retrying...")
                continue

        self.daemon_socket.settimeout(None)
        print(f"Failed to receive ACK after {max_retries} attempts.")
        # Handle timeout
        #  - Send FINERR to the other user
        #  - Inform the client
        print(
            f"\n** Connection timed out, sending FINERR to {self.inviting_addr} **\n")

        # Send FINERR to the remote daemon - trying to end the chat for them too
        err_payload: str = "Connection timed out, exiting chat... :("
        reply: bytes = message_to_datagram(
            MessageType.CONTROL, OperationType.FINERR, self.send_sequence_number, self.username, err_payload)
        if self.inviting_addr:
            self.send_with_retransmission(reply, self.inviting_addr)
            print(f"\n**Sent FINERR to {self.inviting_addr}**\n")
        else:
            self.send_with_retransmission(reply, self.remote_addr)
            print(f"\n**Sent FINERR to {self.remote_addr}**\n")

        # Inform the client and reset the chat details
        self.is_in_chat = False
        self.remote_addr = None
        # Reset sequence numbers
        self.send_sequence_number = 0x00
        self.expected_sequence_number = 0x00
        self.client_conn.sendall(
            "Connection timed out, exiting chat... :(".encode('ascii'))

    # Abstraction for sending an ACK
    def send_ack(self, addr: Tuple[str, int], received_sequence_number: int) -> None:
        reply_ack: bytes = message_to_datagram(
            MessageType.CONTROL, OperationType.ACK, received_sequence_number, self.username, "")  # Expected sequence number is the same as the received sequence number
        self.daemon_socket.sendto(reply_ack, addr)
        print(
            f"\n----------->\nDAEMON: Sending ACK {addr}:\n{Datagram(reply_ack)}\n----------->\n")

    # Handle an incoming datagram
    def handle_datagram(self, message_received: Datagram, addr: Tuple[str, int]) -> None:
        # Validating the sequence number
        received_sequence_number: int = message_received.header.sequence_number
        # SYN messages are not validated to be of the expected sequence number as third party would not know the current sequence number
        if received_sequence_number != self.expected_sequence_number and message_received.header.operation != OperationType.SYN:
            print(
                f"\n!! Received out-of-order datagram from {addr}, expected {self.expected_sequence_number}, got {received_sequence_number}. !!\n")
            # NOTE: For now with this we are essentially just ignoring any incoming datagrams that are out of order
            return

        # Handle message type
        # 1. Control message
        if message_received.header.message_type == MessageType.CONTROL:
            # SYN: Other client wants to start a chat
            if message_received.header.operation == OperationType.SYN:
                # Check if user is already in a chat
                # If not, "establish channel" and send SYNACK
                if not self.is_in_chat and not self.pending_invitation:
                    # Additionally check that there is connected client, if not send FINERR and decline chat
                    if not self.client_is_connected:
                        reply_fin: bytes = message_to_datagram(
                            MessageType.CONTROL, OperationType.FINERR, message_received.header.sequence_number, "DAEMON", "No client is connected to the daemon.")
                        self.send_with_retransmission(
                            reply_fin, addr, skip_sequence_check=True)
                        print(
                            f"!! Sent FINERR to {addr} trying to connect because no client is connected. !!\n")
                        return
                    # Notify the user that another user wants to start a chat with them
                    invitation_message: str = f"CONNECT User {message_received.header.user} wants to start a chat."
                    self.client_conn.sendall(
                        invitation_message.encode('ascii'))
                    print(
                        f"\nReceived an invitation, forwarding to client: {invitation_message}\n")
                    # Set the invitation details
                    self.pending_invitation = True
                    self.inviting_user = message_received.header.user
                    self.inviting_addr = addr

                    # Wait for user input to accept or reject the chat
                    # - If user accepts, send SYNACK (via `handle_accept`)
                    # - If user rejects, send FINERR ()
                    print("\nWaiting for client to respond to chat invitation...")
                    response: str = self.client_conn.recv(1024).decode('ascii')
                    if response == "ACCEPT":
                        self.handle_accept(
                            message_received.header.sequence_number)
                    else:
                        self.handle_reject(
                            message_received.header.sequence_number)

                # If already in a chat, send error message
                else:
                    # Send FINERR to other user, as connection can not be made
                    err_payload: str = "User already in chat, or has pending invitation."
                    reply: bytes = message_to_datagram(
                        MessageType.CONTROL, OperationType.FINERR, message_received.header.sequence_number, self.username, err_payload)
                    self.send_with_retransmission(
                        reply, addr, skip_sequence_check=True)
                    print(
                        f"\n!! Sent FINERR to {addr} because user is busy. !!\n")
                    # Communicate to client that another user tried to start a chat
                    self.client_conn.sendall(
                        f"User {message_received.header.user} tried to start a chat, but was automatically rejected.".encode('ascii'))
            elif message_received.header.operation == OperationType.SYNACK:
                print(
                    f"\n** User {message_received.header.user} accepted the chat, connection established. **\n")
                self.client_conn.sendall(
                    f"Chat connection established with {message_received.header.user}.".encode('ascii'))
                self.is_in_chat = True  # NOTE: This puts the initiator into the chat
                self.remote_addr = addr
                # Send ACK to the other user
                self.send_ack(addr, message_received.header.sequence_number)
                # Once we have received the SYNACK, we can toggle the sequence numbers
                self.expected_sequence_number = 0x01 if self.expected_sequence_number == 0x00 else 0x00
                self.send_sequence_number = 0x01 if self.send_sequence_number == 0x00 else 0x00

            elif message_received.header.operation == OperationType.ERR:
                # TODO: Maybe even send to the client in the future?
                # Print error message
                print(
                    f"\n!! Received an error message: {message_received.payload.message} !!\n")
                # Send ACK about the ERR
                self.send_ack(addr, message_received.header.sequence_number)
                pass
            # FIN: Other client wants to end the chat
            elif message_received.header.operation == OperationType.FIN:
                self.send_ack(addr, message_received.header.sequence_number)
                self.client_conn.sendall(
                    f"!! User {message_received.header.user} ended the chat. !!".encode('ascii'))
                self.is_in_chat = False
                self.remote_addr = None
                # Reset sequence numbers
                self.send_sequence_number = 0x00
                self.expected_sequence_number = 0x00
            # FINERR: Other client rejected the chat, or connection could not be established as no client was connected
            elif message_received.header.operation == OperationType.FINERR:
                print(
                    f"\n!! Chat invitation rejected: {message_received.payload.message} !!\n")
                self.client_conn.sendall(
                    f"Connection could not be established: {message_received.payload.message}.".encode('ascii'))
                # Send ACK
                self.send_ack(addr, message_received.header.sequence_number)
                self.is_in_chat = False
                self.remote_addr = None
                # Reset sequence numbers
                self.send_sequence_number = 0x00
                self.expected_sequence_number = 0x00
            # ACK: The other client received the message
            elif message_received.header.operation == OperationType.ACK:
                # Conditionally handle the ACK if we are waiting for the ACK of a SYNACK
                if self.pending_invitation:
                    print(
                        f"\n** Connection establishment ACK by: {message_received.header.user} **\n")
                    self.client_conn.sendall(
                        f"Chat connection established with {message_received.header.user}.".encode('ascii'))
                    self.pending_invitation = False
                    self.inviting_user = None
                    self.inviting_addr = None
                    # Processed datagram, now we can toggle expected_sequence_number and send sequence number
                    self.expected_sequence_number = 0x01 if self.expected_sequence_number == 0x00 else 0x00
                    self.send_sequence_number = 0x01 if self.send_sequence_number == 0x00 else 0x00
                pass
        # 2. Chat message (simply forward to client and send ACK)
        elif message_received.header.message_type == MessageType.CHAT:
            # ACK the chat message
            self.send_ack(addr, message_received.header.sequence_number)
            # Forward the chat message to the client
            self.client_conn.sendall(
                ("CHAT " + message_received.header.user + " " + message_received.payload.message).encode('ascii'))
            # Processed datagram, now we can toggle expected_sequence_number and send sequence number
            self.expected_sequence_number = 0x01 if self.expected_sequence_number == 0x00 else 0x00
            self.send_sequence_number = 0x01 if self.send_sequence_number == 0x00 else 0x00

    # Start the daemon

    def start_daemon_listener(self) -> None:
        # Timeout of 1 second for keyboard interrupt
        print("** Starting SIMP daemon...")
        print(f"Listening for daemon connections on {self.host}:7777... **\n")
        self.daemon_socket.settimeout(1.0)
        # Loop forever
        try:
            while True:
                try:
                    # Receive data with timeout
                    data, addr = self.daemon_socket.recvfrom(1024)
                    message_received = Datagram(data)
                    print(
                        f"\n<-----------\nDAEMON: Received datagram from {addr}:\n{message_received}\n<-----------\n")
                    # Handle the datagram
                    self.handle_datagram(message_received, addr)
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("Exiting...")
            self.daemon_socket.close()
        if self.has_been_connected:
            print("Daemon listener thread shutdown.")

    def start_client_listener(self) -> None:
        print("\n** Waiting for client connection on port 7778... **\n")
        while True:
            conn, addr = self.client_socket.accept()
            # Start a new thread to handle the connection
            # Sleep for a short time to avoid busy-waiting
            threading.Thread(target=self.handle_client,
                             args=(conn, addr)).start()

    def handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        # Ensure thread safety with a lock and check if a client is already connected
        with self.client_lock:
            # If no client is connected yet, accept the connection and set `self.client_conn` to the connection
            if not self.client_is_connected:
                self.client_is_connected = True
                self.has_been_connected = True
                # Save the connection on the class so that it can be accessed in handle datagram
                self.client_conn = conn
                print(f"Local SIMP client connected from: {addr}")
                self.client_conn.sendall(
                    "Only client, connection successfully established.".encode('ascii'))
                self.username = self.client_conn.recv(1024).decode('ascii')
                print(f"**Client username set: {self.username}**")
            # If there is already a client connected, reject the new connection using the connection
            else:
                # Client is already connected, reject the new connection
                print(
                    f"Rejected connection from {addr} because a client is already connected.")
                conn.sendall(
                    "Another client is already connected.".encode('ascii'))
                conn.close()
                return

        # Handle the client connection if it is accepted
        try:
            with self.client_conn:
                while True:
                    data = self.client_conn.recv(1024)
                    if not data:
                        break
                    command = data.decode('ascii')
                    if command.startswith("CONNECT"):
                        # Handle client wanting to connect to another user
                        # - get the details of the other user from the command
                        # - send a SYN message to the other user
                        # - wait for a SYNACK message from the other user
                        #   - IF SYNACK received, start chat
                        #   - IF FINERR received, send ERR to client "connection not established"
                        remote_ip = command.split(" ")[1]
                        self.remote_addr = (remote_ip, 7777)
                        datagram = message_to_datagram(
                            MessageType.CONTROL, OperationType.SYN, self.send_sequence_number, self.username, "")

                        # NOTE: SYN message does not use retransmission on purpose
                        self.daemon_socket.sendto(datagram, self.remote_addr)
                        print(
                            f"\n----------->\nDAEMON: Sending datagram {self.remote_addr}:\n{Datagram(datagram)}\n----------->\n")
                        pass
                    elif command.startswith("CHAT"):
                        # Handle client wanting to send a chat message
                        # - get the message from the command
                        # - IF not in chat, send an ERR message to the client
                        # - ELSE send a CHAT message to the other user
                        message = command.split(" ", 1)[1]
                        if self.is_in_chat:
                            datagram = message_to_datagram(
                                MessageType.CHAT, OperationType.ERR, self.send_sequence_number, self.username, message)
                            self.send_with_retransmission(
                                datagram, self.remote_addr)
                        else:
                            print("Client is not in chat, cannot send message.")
                            self.client_conn.sendall(
                                "Not in chat, can not send message.".encode('ascii'))
                        pass
                    elif command.startswith("QUIT"):
                        # NOTE: This just breaks the loop, as there is cleanup needed
                        # - if the user deliberately quits or
                        # - if the user is disconnected

                        print(f"Client user quit deliberately.")
                        break
                    else:
                        print(
                            f"Received invalid command from client: {command}")
        except Exception as e:
            print(f"Error in handle_client: {e}")
        finally:
            # Client disconnected or finished, reset connections and give information to other Daemon
            if self.is_in_chat and self.remote_addr:
                # Send FIN message to the other user
                datagram = message_to_datagram(
                    MessageType.CONTROL, OperationType.FIN, self.send_sequence_number, self.username, "")  # TODO: Sequence number
                self.send_with_retransmission(datagram, self.remote_addr)
                # Set flags
                self.is_in_chat = False
                self.remote_addr = None
                self.client_conn.close()
                # Reset sequence numbers
                self.send_sequence_number = 0x00
                self.expected_sequence_number = 0x00
            with self.client_lock:
                self.client_is_connected = False

            print(f"\n!! Client at {addr} disconnected. !!\n")

    def handle_accept(self, syn_sequence_number: int) -> None:
        print("\n** Handling accept... **\n")
        if self.pending_invitation and self.inviting_addr:
            # Send SYNACK to the remote daemon
            datagram: bytes = message_to_datagram(
                MessageType.CONTROL, OperationType.SYNACK, syn_sequence_number, self.username, "")
            success: bool = self.send_with_retransmission(
                datagram, self.inviting_addr)
            if success:
                print(
                    f"\n** Received ACK from user {self.inviting_user} **\n")
                self.client_conn.sendall(
                    f"Chat connection established with {self.inviting_user}.".encode('ascii'))

                # Set the chat details
                self.is_in_chat = True
                self.remote_addr = self.inviting_addr

                # Reset the invitation details
                self.pending_invitation = False
                self.inviting_addr = None
                self.inviting_user = None

        else:
            self.client_conn.sendall(
                "No pending chat invitations to accept.".encode('ascii'))

    def handle_reject(self, syn_sequence_number: int) -> None:
        if self.pending_invitation and self.inviting_addr:
            # Send FINERR to the remote daemon
            err_payload: str = "Chat invitation rejected."
            reply: bytes = message_to_datagram(
                MessageType.CONTROL, OperationType.FINERR, syn_sequence_number, self.username, err_payload)
            self.send_with_retransmission(
                reply, self.inviting_addr, skip_sequence_check=True)
            print(f"\n**Sent FINERR to {self.inviting_addr}**\n")

            # Notify the client of successful rejection
            self.client_conn.sendall(
                "Chat invitation rejected.".encode('ascii'))

            # Reset the invitation details
            self.pending_invitation = False
            self.inviting_addr = None
            self.inviting_user = None
        else:
            self.client_conn.sendall(
                "No pending chat invitations to reject.".encode('ascii'))


def show_usage():
    print("Usage: simp_daemon.py <host>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        show_usage()
        exit(1)

    # Start the daemon
    daemon = Daemon(sys.argv[1])
    threading.Thread(target=daemon.start_client_listener).start()
    threading.Thread(target=daemon.start_daemon_listener).start()
