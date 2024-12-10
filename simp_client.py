import socket
import threading
import sys
import queue
import time


class Client:
    def __init__(self, host, username):
        self.host = host
        self.username = username
        self.connected = False
        
        # Message management queue
        self.message_queue = queue.Queue()
        
        # TCP socket for Client to Daemon communication
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Invitation details
        self.invitation = False
        self.invitation_addr = None
        self.invitation_user = None

        # Chat details
        self.chatting = False
        self.chat_addr = None
        self.chat_user = None

        # Connect to the Daemon
        try:
            self.socket.connect((self.host, 7778))
            print(f"\n** Client connected to Daemon at {self.host}:7778 **")
        except ConnectionRefusedError:
            print(f"\n!! Could not connect to Daemon at {self.host}:7778 !!")
            return

        # Print out the connection output from the Daemon
        # - either fail because the Daemon is already connected to client
        # - or success because the Daemon is connected to the
        initial_response = self.socket.recv(1024)
        if initial_response:
            message = initial_response.decode('ascii')
            print("** DAEMON STATUS: ", message, " **\n")
            if "Another client is already connected." in message:
                # Connection was rejected; close the socket
                self.socket.close()
                return

        # Start receiving responses in a new thread
        self.connected = True  # Connection is established with the Daemon
        # TODO: Do we need a thread here? 
        # - the threads allows us to simulataneously wait for user input
        # - and receive messages from the Daemon
        threading.Thread(target=self.receive_response, daemon=True).start()
        # self.receive_response()
        

    # Send any string command to the local Daemon for processing
    def send_command(self, command):
        if self.connected:
            self.socket.sendall(command.encode('ascii'))
            print(f"Sent command: {command}")
        else:
            print("Not connected to daemon. Cannot send command.")

    # Receive response from the Daemon and display it to the user
    def receive_response(self):
        while True:
            response = self.socket.recv(1024)
            if not response:
                break
            decoded_response = response.decode('ascii')
            self.message_queue.put(decoded_response)
            # NOTE: Due to how we are constantly receiving messages and asking for user input at all times,
            # I chose to manage it inside of a queue on the handle_uner_input method
            # Logic is:
            # - If there is a message in the queue, print it and handle it
            # - If there is no message in the queue, ask for user input as usual

            # TODO: Somehow we need to handle the fact that there is an ongoing input waiting for the user
            # - this blocks operation so we need to skip the input and handle the message
            # - we can do this by writing to stdin maybe?

    # Handle user input:
    # Logic is:
    # - If there is a message in the queue, print it and handle it
    # - If there is no message in the queue, ask for user input as usual
    def handle_user_input(self):
        if not self.connected:
            print("Not connected to daemon. Exiting.")
            return
        while True:
            # Check for messages from the daemon
            while not self.message_queue.empty():
                message = self.message_queue.get()
                if message.startswith("CONNECT"):
                    # Handle the invitation
                    self.handle_invitation(message)
                elif "Chat connection established" in message:
                    print(message)
                    self.chatting = True
                    self.invitation = False
                elif "Chat invitation rejected" in message:
                    print(message)
                    self.invitation = False
                else:
                    print("Response from daemon:", message)



            # If no message from the daemon, ask for user input based on the current state
            if self.invitation:
                time.sleep(0.1)
                continue
            elif self.chatting:
                command = input(
                    "Enter command (CHAT <message>, QUIT): ")
                # User wants to send a chat message to connected user
                if command.startswith("CHAT"):
                    _, message = command.split(maxsplit=1)
                    self.send_chat_message(message)
                # User wants to quit the chat
                elif command == "QUIT":
                    self.quit_chat()
                    break
                else:
                    print("Invalid command.")
            else:
                command = input("Enter command (CONNECT <ip>, QUIT): ")
                # User wants to connect to another user
                if command.startswith("CONNECT"):
                    _, remote_ip = command.split()
                    self.connect_to_user(remote_ip)
                # User wants to quit the chat
                elif command == "QUIT":
                    self.quit_chat()
                    break
                else:
                    print("Invalid command.")

    # Handle the invitation message received through the Daemon
    def handle_invitation(self, message):
        print(message)  # Display the invitation message
        accept_invitation = None
        while accept_invitation not in ["Y", "y", "N", "n"]:
            accept_invitation = input("Do you accept the invitation? (Y/N): ")
            if accept_invitation in ["Y", "y"]:
                self.send_command("ACCEPT")
            elif accept_invitation in ["N", "n"]:
                self.send_command("REJECT")
            else:
                print("Invalid input. Please enter 'Y' or 'N'.")

    # Send an invitation to user with ip, through connection initiation message to the Daemon
    def connect_to_user(self, remote_ip):
        command = f"CONNECT {remote_ip}"
        self.send_command(command)

        # Set the invitation details
        self.invitation = True
        self.invitation_addr = remote_ip

    # Send a message to the connected user through the Daemon
    def send_chat_message(self, message):
        command = f"CHAT {message}"
        self.send_command(command)

    def quit_chat(self):
        # TODO: Here make checks:
        # - is the client and thus the Daemon in a chat already
        command = "QUIT"
        self.send_command(command)
        # TODO: For now quitting also disconnects from the Daemon but is this truly what we want?
        self.socket.close()
        print("Disconnected from daemon")


def show_usage():
    print("Usage: simp_daemon.py <host> <username>")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        show_usage()
        exit(1)

    # Start the daemon
    client = Client(sys.argv[1], sys.argv[2])
    if client.connected:
        client.handle_user_input()
    else:
        print("Exiting client.")
        exit(1)
