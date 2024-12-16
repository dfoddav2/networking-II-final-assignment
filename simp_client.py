import socket
import threading
import sys
import queue
import time
import select
from typing import Optional, Tuple


class Client:
    def __init__(self, host: str) -> None:
        self.host: str = host
        self.username: Optional[str] = None
        self.connected: bool = False

        # Message management queue
        self.message_queue: queue.Queue[str] = queue.Queue()

        # TCP socket for Client to Daemon communication
        self.socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Invitation and chat details
        self.invitation: bool = False
        self.chatting: bool = False
        self.chat_addr: Optional[str] = None
        self.chat_user: Optional[str] = None

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
        initial_response: bytes = self.socket.recv(1024)
        if initial_response:
            message: str = initial_response.decode('ascii')
            print("** DAEMON STATUS: ", message, " **\n")
            if "Another client is already connected." in message:
                # Connection was rejected; close the socket
                self.socket.close()
                return
            else:
                self.username = input("Please enter your username: ")
                print("Welcome, ", self.username,
                      " you may now connect to a user via their IP to chat or wait for somebody to connect to you.\n")
                self.socket.sendall(self.username.encode('ascii'))

        # Start receiving responses in a new thread
        self.connected = True  # Connection is established with the Daemon
        # the threads allows us to simulataneously wait for user input and receive messages
        threading.Thread(target=self.receive_response, daemon=True).start()

    # Send any string command to the local Daemon for processing
    def send_command(self, command: str) -> None:
        if self.connected:
            self.socket.sendall(command.encode('ascii'))
            # print(f"Sent command: {command}")
        else:
            print("\n!! Not connected to daemon. Cannot send command.\n")

    # Receive response from the Daemon and display it to the user
    def receive_response(self) -> None:
        while True:
            response: bytes = self.socket.recv(1024)
            if not response:
                break
            decoded_response: str = response.decode('ascii')
            self.message_queue.put(decoded_response)
            # NOTE: Due to how we are constantly receiving messages and asking for user input at all times,
            # I chose to manage it inside of a queue on the handle_uner_input method
            # Logic is:
            # - If there is a message in the queue, print it and handle it
            # - If there is no message in the queue, ask for user input as usual

    def handle_user_input(self) -> None:
        if not self.connected:
            print("Not connected to daemon. Exiting.")
            return

        self.expecting_invitation_input: bool = False
        prompt_displayed: bool = False

        while True:
            # Check for messages from the daemon
            while not self.message_queue.empty():
                message: str = self.message_queue.get()
                if message.startswith("CONNECT"):
                    # Handle the invitation
                    self.handle_invitation(message)
                elif message.startswith("CHAT"):
                    _, from_user, message_payload = message.split(" ", 2)
                    # Display the chat message
                    print(
                        f"\n\n<------\n{from_user}: {message_payload}\n<------")
                elif "Chat connection established" in message:
                    print("\n" + message)
                    self.chatting = True
                    self.invitation = False
                    self.expecting_invitation_input = False
                elif "invitation rejected" in message or "already in chat" in message or "No client is connected" in message or "ended the chat" in message or "timed out" in message:
                    print("\n" + message)
                    self.invitation = False
                    self.expecting_invitation_input = False
                    self.chatting = False
                else:
                    print("\nResponse from daemon:", message)
                prompt_displayed = False  # Redisplay prompt

            # Now check for user input
            if not prompt_displayed:
                if self.expecting_invitation_input:
                    prompt: str = "\nDo you accept the invitation? (Y/N): "
                elif self.invitation:
                    prompt = ""
                elif self.chatting:
                    prompt = "\nEnter command (CHAT <message>, QUIT): "
                else:
                    prompt = "\nEnter command (CONNECT <ip>, QUIT): "
                print(prompt, end='', flush=True)
                prompt_displayed = True

            # Use select to check for input availability
            ready, _, _ = select.select([sys.stdin], [], [], 0.1)
            if ready:
                user_input: str = sys.stdin.readline().strip()
                prompt_displayed = False  # Redisplay prompt

                if self.expecting_invitation_input:
                    if user_input.lower() == 'y':
                        self.send_command("ACCEPT")
                        self.expecting_invitation_input = False
                    elif user_input.lower() == 'n':
                        self.send_command("REJECT")
                        self.expecting_invitation_input = False
                    else:
                        print("Invalid input. Please enter 'Y' or 'N'.")
                elif self.invitation:
                    # Do nothing; the invitation will be handled by the daemon
                    pass
                elif self.chatting:
                    if user_input.startswith("CHAT "):
                        _, message = user_input.split(" ", 1)
                        self.send_chat_message(message)
                    elif user_input == "QUIT":
                        self.quit_chat()
                        break
                    else:
                        print("Invalid command.")
                else:
                    if user_input.startswith("CONNECT "):
                        _, remote_ip = user_input.split(" ", 1)
                        self.connect_to_user(remote_ip)
                    elif user_input == "QUIT":
                        self.quit_chat()
                        break
                    else:
                        print("Invalid command.")
            else:
                # No input; continue loop
                time.sleep(0.1)

    # Handle the invitation message received through the Daemon
    def handle_invitation(self, message: str) -> None:
        print(message)  # Display the invitation message
        accept_invitation: Optional[str] = None
        while accept_invitation not in ["Y", "y", "N", "n"]:
            accept_invitation = input(
                "\nDo you accept the invitation? (Y/N): ")
            if accept_invitation in ["Y", "y"]:
                self.send_command("ACCEPT")
            elif accept_invitation in ["N", "n"]:
                self.send_command("REJECT")
            else:
                print("Invalid input. Please enter 'Y' or 'N'.")

    # Send an invitation to user with ip, through connection initiation message to the Daemon
    def connect_to_user(self, remote_ip: str) -> None:
        if remote_ip == self.host:
            print("Cannot connect to self.")
            return
        print(f"\nWaiting for user at {remote_ip} to accept the invitation...")
        command: str = f"CONNECT {remote_ip}"
        self.send_command(command)

        # Set the invitation details
        self.invitation = True

    # Send a message to the connected user through the Daemon
    def send_chat_message(self, message: str) -> None:
        print(f"\n------>\n{self.username}: {message}\n------>")
        command = f"CHAT {message}"
        self.send_command(command)

    def quit_chat(self) -> None:
        # TODO: Could do checks in the future to ensure that the user
        # - is the client and thus the Daemon in a chat already
        command = "QUIT"
        self.send_command(command)
        self.chatting = False
        self.invitation = False
        # TODO: For now quitting also disconnects from the Daemon but is this truly what we want?
        self.socket.close()
        print("Disconnected from daemon")


def show_usage():
    print("Usage: simp_daemon.py <host>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        show_usage()
        exit(1)

    # Start the daemon
    client = Client(sys.argv[1])
    if client.connected:
        client.handle_user_input()
    else:
        print("Exiting client.")
        exit(1)
