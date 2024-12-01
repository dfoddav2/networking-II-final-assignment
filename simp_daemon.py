import socket
import threading
import sys
import time

from simp_classes import Datagram, MessageType, OperationType, message_to_datagram


class Daemon:
    def __init__(self, host, username):
        self.host = host
        self.username = username
        self.is_in_chat = False
        self.remote_addr = None
        self.client_is_connected = False

        # Create a UDP socket - for Daemon to Daemon communication
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, 7777))

        # Create a TCP socket - for Client to Daemon communication
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.bind((self.host, 7778))
        self.client_socket.listen()
        self.client_lock = threading.Lock()

    # Send a datagram and wait for an ACK of the message
    # TODO: Use this function to send messages

    # Send a datagram and wait for an ACK of the message

    def send_with_retransmission(self, datagram, addr):
        self.socket.settimeout(5)  # 5-second timeout for ACK
        self.socket.sendto(datagram, addr)
        start_time = time.time()
        while True:
            try:
                data, addr = self.socket.recvfrom(1024)
                message_received = Datagram(data)
                if message_received.header.operation == OperationType.ACK:
                    break
            except socket.timeout:
                if time.time() - start_time > 5:  # 5-second timeout
                    self.socket.sendto(datagram, addr)
                    start_time = time.time()
        self.socket.settimeout(None)  # Remove timeout

    # Handle an incoming datagram
    def handle_datagram(self, message_received, addr):
        next_sequence_number = 0x00
        if message_received.header.sequence_number == 0x00:
            next_sequence_number = 0x01

        # Handle message type
        # 1. Control message
        if message_received.header.message_type == MessageType.CONTROL:
            # SYN: Other client wants to start a chat
            if message_received.header.operation == OperationType.SYN:
                # Check if user is already in a chat
                # If not, "establish channel" and send SYNACK
                if not self.is_in_chat:
                    self.is_in_chat = True
                    reply_operation = OperationType.SYNACK
                    reply = message_to_datagram(
                        MessageType.CONTROL, reply_operation, next_sequence_number, self.username, "")
                    self.socket.sendto(reply, addr)
                    self.remote_addr = addr  # Save the remote address
                    # TODO: Communicate to client that chat was started
                # If already in a chat, send error message
                else:
                    err_payload = "User already in another chat"
                    reply_err = message_to_datagram(
                        MessageType.CONTROL, OperationType.ERR, next_sequence_number, self.username, err_payload)
                    self.socket.sendto(reply_err, addr)
                    reply_fin = message_to_datagram(
                        MessageType.CONTROL, OperationType.FIN, next_sequence_number, self.username, "")
                    self.socket.sendto(reply_fin, addr)
                    # TODO: Communicate to client that another user tried to start a chat
            # FIN: Other client wants to end the chat
            elif message_received.header.operation == OperationType.FIN:
                reply = message_to_datagram(
                    MessageType.CONTROL, OperationType.ACK, next_sequence_number, self.username, "")
                self.socket.sendto(reply, addr)
                self.is_in_chat = False
                self.remote_addr = None
                # TODO: Communicate to client that chat was ended by other user
            # ACK: The other client received the message
            elif message_received.header.operation == OperationType.ACK:
                # TODO: Handle ACK -> Maybe somehow mark the message as received
                pass
        # 2. Chat message (simply forward to client and send ACK)
        elif message_received.header.message_type == MessageType.CHAT:
            # Handle chat message
            reply = message_to_datagram(
                MessageType.CONTROL, OperationType.ACK, next_sequence_number, self.username, "")
            self.socket.sendto(reply, addr)
            # TODO: Forward message to client

    # Start the daemon
    def start(self):
        # Timeout of 1 second for keyboard interrupt
        print("Starting SIMP daemon...")
        print(f"Listening for daemon connections on {self.host}:7777...")
        print(f"Username: {self.username}")
        self.socket.settimeout(1.0)
        # Loop forever
        try:
            while True:
                try:
                    # Receive data with timeout
                    data, addr = self.socket.recvfrom(1024)
                    message_received = Datagram(data)
                    print(
                        f"DAEMON: Received datagram from {addr}:\n{message_received}")
                    # Handle the datagram
                    self.handle_datagram(message_received, addr)
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("Exiting...")
            self.socket.close()
        print("Daemon shutdown.")

    def handle_client(self, conn, addr):
        # Ensure thread safety with a lock and check if a client is already connected
        with self.client_lock:
            if not self.client_is_connected:
                self.client_is_connected = True
                print(f"Local SIMP client connected from: {addr}")
                conn.sendall("Only client, connection successfully established.".encode('ascii'))
            else:
                # Client is already connected, reject the new connection
                print(
                    f"Rejected connection from {addr} because a client is already connected.")
                conn.sendall("Another client is already connected.".encode('ascii'))
                conn.close()
                return
        # Handle the client connection if it is accepted
        try:
            with conn:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    command = data.decode('ascii')
                    if command.startswith("CONNECT"):
                        # TODO: Handle client wanting to connect to another user
                        # - get the details of the other user from the command
                        # - send a SYN message to the other user
                        # - wait for a SYNACK message from the other user
                        #   - IF SYNACK received, start chat
                        #   - IF ERR received, send ERR to client "connection not established"
                        remote_ip = command.split(" ")[1]
                        print(
                            f"Client is trying to connect to user with ip: {remote_ip}")
                        pass
                    elif command.startswith("CHAT"):
                        # TODO: Handle client wanting to send a chat message
                        # - get the message from the command
                        # - IF not in chat, send an ERR message to the client
                        # - ELSE send a CHAT message to the other user
                        pass
                    elif command.startswith("QUIT"):
                        # TODO: Handle client wanting to quit the chat
                        # - send a FIN message to the other user
                        if self.is_in_chat and self.remote_addr:
                            datagram = message_to_datagram(
                                MessageType.CONTROL, OperationType.FIN, 0x00, self.username, "")
                            self.send_with_retransmission(
                                self.socket, datagram, self.remote_addr)
                            self.is_in_chat = False
                            self.remote_addr = None
                        print(f"Client user quit")
                        break
        finally:
            # Client disconnected or finished, reset client_is_connected
            with self.client_lock:
                self.client_is_connected = False
            print(f"Client at {addr} disconnected.")

    def start_client_listener(self):
        print("Waiting for client connection on port 7778...")
        while True:
            conn, addr = self.client_socket.accept()
            # Start a new thread to handle the connection
            # Sleep for a short time to avoid busy-waiting
            threading.Thread(target=self.handle_client,
                             args=(conn, addr)).start()


def show_usage():
    print("Usage: simp_daemon.py <host> <username>")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        show_usage()
        exit(1)

    # Start the daemon
    daemon = Daemon(sys.argv[1], sys.argv[2])
    threading.Thread(target=daemon.start).start()
    threading.Thread(target=daemon.start_client_listener).start()
