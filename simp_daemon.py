import socket
import threading
import sys
import time

from simp_classes import Datagram, MessageType, OperationType, message_to_datagram


class Daemon:
    def __init__(self, host):
        self.host = host
        self.username = None
        # Used for surpressing the "Daemon listener thread shutdown." message for the first time
        self.has_been_connected = False

        # Create a UDP socket - for DAEMON to DAEMON communication
        self.daemon_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.daemon_socket.bind((self.host, 7777))
        self.next_sequence_number = 0x00

        # TCP socket and details for DAEMON to CLIENT conenction
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_conn = None
        self.client_is_connected = False
        self.client_lock = threading.Lock()
        # Start listening for client connections
        self.client_socket.bind((self.host, 7778))
        self.client_socket.listen()

        # Invitation related
        self.pending_invitation = False
        self.inviting_user = None
        self.inviting_addr = None

        # Chat related
        self.remote_addr = None
        self.is_in_chat = False
        self.chat_addr = None
        self.chat_user = None

    # Send a datagram and wait for an ACK of the message
    def send_with_retransmission(self, datagram, addr):
        max_retries = 3
        timeout = 5  # seconds
        retries = 0
        sequence_number = Datagram(datagram).header.sequence_number

        while retries < max_retries:
            self.daemon_socket.sendto(datagram, addr)
            print(
                f"\n----------->\nDAEMON (Attempt #{retries + 1}): Sending datagram {addr}:\n{Datagram(datagram)}\n----------->\n")
            start_time = time.time()
            self.daemon_socket.settimeout(timeout)
            try:
                while True:
                    time_elapsed = time.time() - start_time
                    if time_elapsed > timeout:
                        raise socket.timeout
                    response, _ = self.daemon_socket.recvfrom(1024)
                    ack = Datagram(response)
                    print(
                        f"\n<-----------\nDAEMON: Received datagram from {addr}:\n{ack}\n<-----------\n")
                    if (ack.header.operation == OperationType.ACK):  # TODO: Handle sequence number
                        self.daemon_socket.settimeout(None)
                        return True
            except socket.timeout:
                retries += 1
                print(f"Timeout waiting for ACK. Retrying...")
                continue

        self.daemon_socket.settimeout(None)
        print(f"Failed to receive ACK after {max_retries} attempts.")
        # TODO: Handle timeout
        return False

    # Handle an incoming datagram
    def handle_datagram(self, message_received, addr):
        # TODO: Handle and validate the next sequence number, but as a class variable
        # next_sequence_number = 0x00
        # if message_received.header.sequence_number == 0x00:
        #     next_sequence_number = 0x01
        received_sequence_number = message_received.header.sequence_number
        next_sequence_number = 0x01 if received_sequence_number == 0x00 else 0x00

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
                        reply_fin = message_to_datagram(
                            MessageType.CONTROL, OperationType.FINERR, self.next_sequence_number, "DAEMON", "No client is connected to the daemon.")
                        self.daemon_socket.sendto(reply_fin, addr)
                        print(
                            f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(reply_fin)}\n----------->\n")
                        print(
                            f"!! Sent FIN to {addr} trying to connect because no client is connected. !!\n")
                        return
                    # Notify the user that another user wants to start a chat with them
                    invitation_message = f"CONNECT User {message_received.header.user} wants to start a chat."
                    self.client_conn.sendall(
                        invitation_message.encode('ascii'))
                    print(
                        f"\nReceived an invitation, forwarding to client: {invitation_message}\n")
                    # Set the invitation details
                    self.pending_invitation = True
                    self.inviting_user = message_received.header.user
                    self.inviting_addr = addr

                    # TODO: Wait for user input to accept or reject the chat
                    # - If user accepts, send SYNACK
                    # - If user rejects, send ERR and FIN
                    print("\nWaiting for client to respond to chat invitation...")
                    response = self.client_conn.recv(1024).decode('ascii')
                    if response == "ACCEPT":
                        self.handle_accept()
                        # datagram = message_to_datagram(
                        #     MessageType.CONTROL, OperationType.SYNACK, self.next_sequence_number, self.username, "")
                        # print(
                        #     f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(datagram)}\n----------->\n")
                        # self.daemon_socket.sendto(datagram, addr)
                        # self.remote_addr = addr  # Save the remote address
                        # self.is_in_chat = True  # NOTE: This puts the responder into the chat
                        # print(f"** Sent accetping SYNACK to {addr} **\n")
                    else:
                        self.handle_reject()
                        # err_payload = "User rejected chat invitation."
                        # reply = message_to_datagram(
                        #     MessageType.CONTROL, OperationType.FINERR, self.next_sequence_number, self.username, err_payload)
                        # self.daemon_socket.sendto(reply, addr)
                        # print(
                        #     f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(reply)}\n----------->\n")
                        # print(
                        #     f"!! Sent FINERR to {addr} because user rejected chat. !!\n")
                        # self.pending_invitation = False
                        # self.inviting_user = None
                        # self.inviting_addr = None

                # If already in a chat, send error message
                else:
                    # Send FINERR to other user, as connection can not be made
                    err_payload = "User already in chat, or has pending invitation."
                    reply = message_to_datagram(
                        MessageType.CONTROL, OperationType.FINERR, self.next_sequence_number, self.username, err_payload)
                    self.daemon_socket.sendto(reply, addr)
                    print(
                        f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(reply)}\n----------->\n")
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
                reply_ack = message_to_datagram(
                    MessageType.CONTROL, OperationType.ACK, self.next_sequence_number, self.username, "")
                self.daemon_socket.sendto(reply_ack, addr)
                print(
                    f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(reply_ack)}\n----------->\n")
            elif message_received.header.operation == OperationType.ERR:
                # TODO: Maybe even send to the client in the future?
                # Print error message
                print(
                    f"\n!! Received an error message: {message_received.payload.message} !!\n")
                # Send ACK about the ERR
                reply_ack = message_to_datagram(
                    MessageType.CONTROL, OperationType.ACK, self.next_sequence_number, self.username, "")
                self.daemon_socket.sendto(reply_ack, addr)
                print(
                    f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(reply_ack)}\n----------->\n")
                pass
            # FIN: Other client wants to end the chat
            elif message_received.header.operation == OperationType.FIN:
                reply = message_to_datagram(
                    MessageType.CONTROL, OperationType.ACK, self.next_sequence_number, self.username, "")
                self.daemon_socket.sendto(reply, addr)
                print(
                    f"\n----------->\nDAEMON: Sending datagram {addr}:\n{Datagram(reply)}\n----------->\n")
                self.client_conn.sendall(
                    "User wants to end chat.".encode('ascii'))
                self.is_in_chat = False
                self.remote_addr = None
            # FINERR: Other client rejected the chat, or connection could not be established as no client was connected
            elif message_received.header.operation == OperationType.FINERR:
                print(
                    f"\n!! Chat invitation rejected: {message_received.payload.message} !!\n")
                self.client_conn.sendall(
                    f"Connection could not be established: {message_received.payload.message}.".encode('ascii'))
                # Send ACK
                reply = message_to_datagram(
                    MessageType.CONTROL, OperationType.ACK, self.next_sequence_number, self.username, "")
                self.daemon_socket.sendto(reply, addr)
                self.is_in_chat = False
                self.remote_addr = None
            # ACK: The other client received the message # TODO: Now the incoming ACK should be waited for at the send with retransmit
            elif message_received.header.operation == OperationType.ACK:
                # Conditionally handle the ACK if we are waiting for the ACK of a SYNACK
                if self.pending_invitation:
                    print(
                        f"\n** Received ACK from user {message_received.header.user} **\n")
                    self.client_conn.sendall(
                        f"Chat connection established with {message_received.header.user}.".encode('ascii'))
                    self.pending_invitation = False
                    self.inviting_user = None
                    self.inviting_addr = None
                pass
        # 2. Chat message (simply forward to client and send ACK)
        elif message_received.header.message_type == MessageType.CHAT:
            # print(
            #     f"\n**Received chat message from {message_received.header.user}, forwarding to client...\n")
            # ACK the chat message
            reply = message_to_datagram(
                MessageType.CONTROL, OperationType.ACK, self.next_sequence_number, self.username, "")
            self.daemon_socket.sendto(reply, addr)
            print(
                f"\n----------->\nDAEMON: Sending ACK {addr}:\n{Datagram(reply)}\n----------->\n")
            # Forward the chat message to the client
            self.client_conn.sendall(
                ("CHAT " + message_received.header.user + " " + message_received.payload.message).encode('ascii'))

    # Start the daemon

    def start_daemon_listener(self):
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

    def start_client_listener(self):
        print("\n** Waiting for client connection on port 7778... **\n")
        while True:
            conn, addr = self.client_socket.accept()
            # Start a new thread to handle the connection
            # Sleep for a short time to avoid busy-waiting
            threading.Thread(target=self.handle_client,
                             args=(conn, addr)).start()

    def handle_client(self, conn, addr):
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
                        #   - IF ERR received, send ERR to client "connection not established"
                        remote_ip = command.split(" ")[1]
                        self.remote_addr = (remote_ip, 7777)
                        # print(
                        #     f"\n** Client is trying to connect to user with ip: {remote_ip} **\n")
                        # Start the connection with a SYN message, sequence number 0x00
                        datagram = message_to_datagram(
                            MessageType.CONTROL, OperationType.SYN, 0x00, self.username, "")

                        # self.send_with_retransmission(datagram, self.remote_addr)
                        self.daemon_socket.sendto(datagram, self.remote_addr)
                        print(
                            f"\n----------->\nDAEMON: Sending datagram {self.remote_addr}:\n{Datagram(datagram)}\n----------->\n")
                        pass
                    elif command.startswith("CHAT"):
                        # TODO: Handle client wanting to send a chat message
                        # - get the message from the command
                        # - IF not in chat, send an ERR message to the client
                        # - ELSE send a CHAT message to the other user

                        message = command.split(" ", 1)[1]
                        # self.client_conn.sendall(
                        #     f"Sending chat message: {message}".encode('ascii'))
                        if self.is_in_chat:
                            datagram = message_to_datagram(
                                MessageType.CHAT, OperationType.ERR, 0x00, self.username, message)  # TODO: Sequence number
                            self.send_with_retransmission(datagram, self.remote_addr)
                            # self.daemon_socket.sendto(
                            #     datagram, self.remote_addr)
                            # print(
                            #     f"\n----------->\nDAEMON: Sending datagram {self.remote_addr}:\n{Datagram(datagram)}\n----------->\n")
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
                    MessageType.CONTROL, OperationType.FIN, 0x00, self.username, "")  # TODO: Sequence number
                # self.send_with_retransmission(datagram, self.remote_addr)
                self.daemon_socket.sendto(datagram, self.remote_addr)
                print(
                    f"\n----------->\nDAEMON: Sending datagram {self.remote_addr}:\n{Datagram(datagram)}\n----------->\n")
                self.is_in_chat = False
                self.remote_addr = None
                self.client_conn.close()
            with self.client_lock:
                self.client_is_connected = False

            print(f"\n!! Client at {addr} disconnected. !!\n")

    def handle_accept(self):
        print("\n** Handling accept... **\n")
        if self.pending_invitation and self.inviting_addr:
            # print("Pending invite and inviting address found:",
            #       self.pending_invitation, self.inviting_addr)
            # Send SYNACK to the remote daemon
            datagram = message_to_datagram(
                MessageType.CONTROL, OperationType.SYNACK, 0x01, self.username, "")
            # self.daemon_socket.sendto(datagram, self.inviting_addr)
            success = self.send_with_retransmission(
                datagram, self.inviting_addr)
            if success:
                print(
                    f"\n** Received ACK from user {self.inviting_user} **\n")
                self.client_conn.sendall(
                    f"Chat connection established with {self.inviting_user}.".encode('ascii'))

                # Set the chat details
                self.is_in_chat = True
                self.chat_addr = self.inviting_addr
                self.chat_user = self.inviting_user
                self.remote_addr = self.inviting_addr

                # Reset the invitation details
                self.pending_invitation = False
                self.inviting_addr = None
                self.inviting_user = None
            else:
                # TODO: Handle timeouts
                print("Connection timed out... :(")

        else:
            self.client_conn.sendall(
                "No pending chat invitations to accept.".encode('ascii'))

    def handle_reject(self):
        if self.pending_invitation and self.inviting_addr:
            # Send ERR and FIN to the remote daemon
            err_payload = "Chat invitation rejected."
            # TODO: Send ERR + FIN to target daemon in one go?
            reply = message_to_datagram(
                MessageType.CONTROL, OperationType.FINERR, 0x01, self.username, err_payload)
            self.daemon_socket.sendto(reply, self.inviting_addr)
            # reply_err = message_to_datagram(
            #     MessageType.CONTROL, OperationType.ERR, 0x01, self.username, err_payload)
            # self.daemon_socket.sendto(reply_err, self.inviting_addr)
            # print(
            #     f"\n----------->\nDAEMON: Sending datagram {self.inviting_addr}:\n{Datagram(reply_err)}\n----------->\n")
            # reply_fin = message_to_datagram(
            #     MessageType.CONTROL, OperationType.FIN, 0x01, self.username, "")
            # self.daemon_socket.sendto(reply_fin, self.inviting_addr)
            print(
                f"\n----------->\nDAEMON: Sending datagram {self.inviting_addr}:\n{Datagram(reply)}\n----------->\n")
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
