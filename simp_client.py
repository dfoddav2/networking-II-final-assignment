import socket
import threading
import sys
import time


class Client:
    def __init__(self, host, username):
        self.host = host
        self.username = username
        self.connected = False
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((self.host, 7778))
            print(f"Client connected to Daemon at {self.host}:7778")
        except ConnectionRefusedError:
            print(f"Could not connect to Daemon at {self.host}:7778")
            return

        print(f"Client connected to Daemon at {self.host}:7778")
        # Print out the connection output from the Daemon
        # - either fail because the Daemon is already connected to client
        # - or success because the Daemon is connected to the
        # Receive the initial message from the Daemon
        initial_response = self.socket.recv(1024)
        if initial_response:
            message = initial_response.decode('ascii')
            print("Initial response from daemon:", message)
            if "Another client is already connected." in message:
                # Connection was rejected; close the socket
                self.socket.close()
                return

        # Start receiving responses in a new thread
        threading.Thread(target=self.receive_response, daemon=True).start()
        self.connected = True  # Connection is established

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
            # TODO: Here handle the actual types of responses from the Daemon, not simply print it
            print("Response received from daemon:", response.decode('ascii'))

    # Handle user input and send commands to the Daemon accordingly
    def handle_user_input(self):
        if not self.connected:
            print("Not connected to daemon. Exiting.")
            return
        while True:
            command = input(
                "Enter command (CONNECT <ip>, CHAT <message>, QUIT): ")
            if command.startswith("CONNECT"):
                _, remote_ip = command.split()
                self.connect_to_user(remote_ip)
            elif command.startswith("CHAT"):
                _, message = command.split(maxsplit=1)
                self.send_chat_message(message)
            elif command == "QUIT":
                self.quit_chat()
                break

    # Send a connection initiation message to the Daemon
    def connect_to_user(self, remote_ip):
        # TODO: Here make checks:
        # - is the client and thus the Daemon in a chat already
        command = f"CONNECT {remote_ip}"
        self.send_command(command)

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
