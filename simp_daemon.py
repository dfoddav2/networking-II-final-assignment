import socket
import threading
import sys

from simp_classes import Datagram, MessageType, OperationType, message_to_datagram

class Daemon:
    def __init__(self, host, port, username):
        self.host = host
        self.port = port
        self.username = username

    
    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            print("Starting SIMP daemon...")
            print(f"Listening on {self.host}:{self.port}")
            print(f"Username: {self.username}")
            s.bind((self.host, self.port))  # Bind the socket to the port
            s.settimeout(1.0)  # Timeout of 1 seconde for keyboard interrupt
            # Loop forever
            try:
                while True:
                    try:
                        # Receive data with timeout
                        data, addr = s.recvfrom(1024)
                        message_received = Datagram(data)
                        print(
                            f"Received datagram from {addr}:\n{message_received}")
                        # Decide on next sequence number
                        next_sequence_number = 0x00
                        if message_received.header.sequence_number == 0x00:
                            next_sequence_number = 0x01
                        # Send back ACK message
                        reply = message_to_datagram(
                            MessageType.CONTROL, OperationType.ACK, next_sequence_number, username, "")
                        print("Sending back data:", reply)
                        s.sendto(reply, addr)
                    except socket.timeout:
                        continue
            except KeyboardInterrupt:
                print("Exiting...")
            print("Daemon shutdown.")

def daemon(host, port, username):
    # Create a socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        print("Starting SIMP daemon...")
        print(f"Listening on {host}:{port}")
        print(f"Username: {username}")
        s.bind((host, port))  # Bind the socket to the port
        s.settimeout(1.0)  # Timeout of 1 seconde for keyboard interrupt
        # Loop forever
        try:
            while True:
                try:
                    # Receive data with timeout
                    data, addr = s.recvfrom(1024)
                    message_received = Datagram(data)
                    print(
                        f"Received datagram from {addr}:\n{message_received}")
                    # Decide on next sequence number
                    next_sequence_number = 0x00
                    if message_received.header.sequence_number == 0x00:
                        next_sequence_number = 0x01
                    # Send back ACK message
                    reply = message_to_datagram(
                        MessageType.CONTROL, OperationType.ACK, next_sequence_number, username, "")
                    print("Sending back data:", reply)
                    s.sendto(reply, addr)
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("Exiting...")
        print("Daemon shutdown.")


def show_usage():
    print("Usage: simp_daemon.py <host> <port> <username>")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        show_usage()
        exit(1)

    # Start the daemon
    daemon(sys.argv[1], int(sys.argv[2]), sys.argv[3])
