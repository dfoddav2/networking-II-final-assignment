# David Fodor - networking-II-final-assignment

This is the repository for the final assignment of the WS24/25 course of Networking II.

SIMP (Simple IMC Messaging Protocol) is a simple messaging protocol for chat applications built on top of UDP. This protocol could in theory be used by a third-party to implement a chat program at the application layer level. The way the implementation works is quite simple, there are two main components:

- Daemon
- Client

Clients are the interfaces users can utilize to message each other, which behind the scenes utilizes an always running Daemon to actually send the message to the desired destination. For example user A sending a message to user B would look as such: `(Client A) -> (Daemon A) -> (Daemon B) -> (Client B)`. Our messaging protocol defines what the communication between Daemons looks like. For more details on the protocol requirements, check out the [REQUIREMENTS.md](./REQUIREMENTS.md) file.

# Table of Contents

1. [Introduction](#introduction)
2. [How to Run](#how-to-run)
3. [Components](#components)
   - [Daemon to Daemon](#daemon-to-daemon)
     - [Datagram Header and Message Types](#datagram-header-and-message-types)
     - [Connection Establishment, Three-Way Handshake](#connection-establishment-three-way-handshake)
     - [Stopping the Connection](#stopping-the-connection)
     - [Handling Lost Datagrams, Retransmissions, and ACKs, Stop-and-Wait](#handling-lost-datagrams-retransmissions-and-acks-stop-and-wait)
     - [Sequence Numbers](#sequence-numbers)
   - [Client to Daemon](#client-to-daemon)
     - [Message Handling, Queueing, and Select](#message-handling-queueing-and-select)
     - [Connecting to Daemon](#connecting-to-daemon)
     - [Disconnecting from Daemon](#disconnecting-from-daemon)
4. [Challenges](#challenges)

## How to run

My prefered method for running the application is by using 4 seperate terminals in VSC, because you can create split view terminals and see what is happening to the Daemon and to the Client at the same time.
NOTE: This could be interesting, because on the Daemon I am logging out the sent and received datagrams in an easily readable format.

What I would recommend is to start a terminal in the root directory, then split the terminal.

In one of the split terminals write:
`python3 simp_daemon.py 127.0.0.1`

Then in the other one start the corresponding client:
`python3 simp_daemon.py 127.0.0.1`

This should connect the Client automatically to the Daemon running on the same host, give feedback about it and then prompt the user for their username.

After this you may simulate a separate Daemon + Client combination, by doing the same as before, but with a different host, e.g. `127.0.0.2`.
This will also prompt you for a username, after which you can use the following commands to interact with the system:

`CONNECT <ip>` - To connect to a user on a different address, running the Client and the Daemon.
`CHAT <message>` - Once connected to a remote user, you may send chat messages back and forth, messages can have spaces and can include any ASCII character.
`QUIT` - At any given point, the Client may quit the application with this function.

There is an additional phase where the user is prompted to accept chat a invitation, here you can simply answer with `y` or `n` and their capitalized versions.

Now I will continue by describing the components of the application and the communication between them. (Plus some interesting challenges, and solutions I have found.)

## Daemon to Daemon

Daemon to Daemon communication is the focal point of this project, as it is what implements the SIMP protocol for communication.

### Datagram header and message types

As behind the scenes our protocol uses UDP sockets, I have decided to name the message units Datagrams. To make the messages more easily understandable for humans, I have implemented them using abstractions like Enums and Classes in [simp_classes.py](./simp_classes.py) and have additionally created a funcion named `message_to_datagram()` that with a given set of input paramaters creates the binary datagram. This binary datagram then can easily be parsed by turning it into a `Datagram` object, by `Datagram(example_message_to_datagram)` (Of course only given that the specific combination of inputs is valid.)

As defined in the [REQUIREMENTS.md](./REQUIREMENTS.md), the datagram looks like the following:

"Each datagram in the SIMP protocol is composed by a header and a payload. The header includes metainformation about the contents of the datagram itself, like type, sequence number, and other parameters. The payload is mainly used to carry the contents of the chat (the messages themselves). Note: all text (strings) will be encoded using plain ASCII characters.
The header is composed of the following fields:"

1. Type (1 byte): the type of the datagram as outlined before. Possible values:

- 0x01 = control datagram.
- 0x02 = chat datagram.

2.  Operation (1 byte): indicates the type of operation of the datagram. Possible values:

- If Type == 0x01 (control datagram):
  - 0x01: ERR (some error condition occurred).
  - 0x02: SYN (used in sliding window algorithm).
  - 0x04: ACK (used in sliding window algorithm and as general acknowledgement).
  - 0x08: FIN (used to close the connection).
- If Type == 0x02 (chat datagram): field Operation takes the constant value 0x01.

3. Sequence (1 byte): a sequence number that can take the values 0x00 or 0x01 used to identify resent or lost datagrams.
4. User (32 bytes): user name encoded as an ASCII string.
5. Length (4 bytes): length of the datagram payload in bytes.
6. Payload: depending on the field Type:

- If Type == 0x01 (control datagram) and Operation == 0x01 (error): a human-readable error message as an ASCII string.
- If Type == 0x02 (chat datagram): the contents of the chat message to be sent.

### Connection establishment, three-way handshake

The handshake is implemented as described in the requirements.
In the following cases we take it as a given that both users have connected to their respective daemons. (Specific edge cases are discussed in the next section about Stopping the connection.)

1. Everything goes well

   - user who wants to connect writes in the CLI: `CONNECT <ip>` (of course except their own, this edge case is also handled)
   - this makes the Daemon send a `SYN` to the target
   - target Daemon receives `SYN`, forwards question to Client and waits for the Client's answer on what to do
   - client writes `y`, accepting the invite, which gets sent as a `ACCEPT` signal to the Daemon
   - the target Daemon now creates the response message, which is a `SYNACK`, sends it, then waits for the `ACK` from the original Daemon
   - the original Daemon responds with an `ACK` and sends a message to the client, informing that the connection has been made

2. Target rejects invitation
   - (same as the first step)
   - client writes `n`, rejecting the invite, which gets sent as a `REJECT` signal to the Daemon
   - the target Daemon now creates the response message which is `FINERR` and sends it to the original Daemon
   - the original Daemon receives the `FINERR` and forwards its payload to the connected client, sends `ACK` (as the requirements didn't state it had to be `FINACK`, I tried to follow them as closely as possible and simply using an `ACK`)
   - the connected client prints the message of the payload and resets the invitation status

### Stopping the connection

In this scenario as well we can separate different cases.

1. The Client on one side disconnects deliberately using the `QUIT` function

   - in this case the client sends a `QUIT` command to the Daemon, which then breaks the infinite loop of handling the user's inputs cleaning up the thread
   - if a chat has been started between users (Daemons are connected), then the Daemon intitiates the the closure of the connection by sending a `FIN` datagram
   - this prompts the other Daemon to respond with an `ACK` and notifies the connected Client that the chat has finished. (As outlined in the requirements.)

2. The Client stops the connection abruptly

   - meanwhile this behaviour is not generally expected from Daemons, Clients can abruptly end the connection, by for example xiting the application, instead of deliberately exiting with the `QUIT` function. (For example in our client's case pressing Ctrl + C)
   - when a client disconnects this way, the same cleanup function happens on the Daemon's end as in the first case
   - with the simple difference that we do not print on the Daemon that the Client quit deliberately

3. Target Daemon is busy, already in chat with other user / waiting for an invitation to be answered

   - this situation is handled via locked class wide flags and the threaded handling of incoming connections to the Daemon
   - the Daemon, although it is busy, can receive the request to connect from a separate Daemon
   - then given that the user is busy in one of the above mentioned ways, the Daemon sends a `FINERR` datagram with the corresponding `error payload`, which the clients can understand and print for the user, resetting the Daemon's invitation and connection status

4. Target Daemon is running, but no connected user
   - it could happen that we are trying to connect to someone who has the Daemon running, but is not actively connected to it with a Client
   - in this case the Daemon similarly to the case before returns a `FINERR` with the payload `No client is connected to the daemon.`
   - (Additional nice feature could be that we log these attempts and store them on the Daemon somewhere, then once the Client connects we push it to the Client's message queue to immedieately see.)

### Handling lost Datagrams, retransmissions and ACKs, Stop-and-wait

Retransmission of datagrams is done via the main sending function, that is aptly named `send_with_retransmission`. It takes in the variables: `datagram` - binary message to send, `addr` - who to send to, `skip_sequence_check=False` - an optional setting that skips the sequence number validation. (Useful for communicating with third parties, e.g. rejecting a third party trying to connect.) This function implements the stop-and-wait functionality by waiting for an `ACK` for each of the packets sent via this function.

It also has some variables set inside of it that change how it functions, feel free to change these to see how it behaves:

```py
max_retries = 3            # how many max retransmits we can have before finally timing out
timeout = 5                # seconds we wait for the ACK before retransmit
retries = 0                # this is just a flag we iterate on to see < max_retries
drop_probability = 0.25    # the chance of a packet "dropping" (not being sent)
```

If the timeout does happen after all, e.g. for all 3 tries the message was dropped, the Daemons get disconnected and this show on their client's end too. (Of course it may still happen that the `FINERR` sent out to the other Daemon also gets lost. In this case the other Daemon would only get disconnected once it tries to send something but doesn't get the ACK back.)

> [!NOTE]
> The very start of the handshake, `SYN` is sent plainly via the UDP socket method to make life easier. That one could also of course use `send_with_retransmission` with some adjustment and additonal flags, but for this simplified case, this suffices I believe.

### Sequence numbers

The sequence numbers are utilized in a way where for each communication block the same sequence number is being used. E.g. for the whole of the three-way handshake the default starter sequence number is used: `SYN (0x00)` -> `SYNACK (0x00)` -> `ACK (0x00)`, or similarly any chat message may go like this: `CHAT ERR (0x01/0x00) -> ACK (0x01/0x00)`.

They are keepen track of via these class variables:

```py
self.send_sequence_number = 0x00       # For sending datagrams
self.expected_sequence_number = 0x00   # For receiving datagrams
```

Essentially:

- Whenever we are sending a response to an action like an `ACK` or `SYNACK`, we use the sequence number of the received message to to show that this answer belongs to the block.
- Whenever a block ends in one way or another we iterate on both sequence numbers, switching back and forth between `0x00` and `0x01`, this happens for both of the connected Daemons.
- When checking for correctness we test the equivalence of sequence numbers
  - -> This happens at the start of the `handle_datagram` which is the main function being ran in loop, when we receive a message.
  - `ack.header.sequence_number == sequence_number` -> And the checking of the reply matching happens in the `send_with_retransmit` as the stop-and-wait can only end if we have received the ACK type datagram with the appropriat sequence number.
- When a chat ends in one way or another, we reset to the default starting point for the sequence numbers being `0x00`.
- If the datagram fails the sequence number check we just ignore that datagram, as we weren't given any specific tasks to do with them in the requirements.

Extra considerations:

- I have made sure that a third party tring to connect doesn't affect and mess up our synchronized sequence number exchange with a different user, so these external requests do not prompt a switch of the class wide sequence numbers and aren't being tested for sequence number correctness. This is what the `skip_sequence_check` attribute is for.

## Client to Daemon

The Client to Daemon communication was left up to us to implement, so I used the simples solutions I could think of, which is simply using a TCP connection between them and simply sending ASCII encoded and decoded string commands. These commands have already been introduced in the [How to run section](#how-to-run) of this document. Namely these are: `CONNECT <ip>`, `CHAT <message>`, `QUIT`.

Once these commands are sent to the Daemon, the Daemon conditionally acts based on the input.

### Message handling, queueing and select

Messages and input on the Client side are all handled via a `message_queue` and a fallback to requesting input from the user. You can see it in the `handle_user_input()` function of the Client class. Essentially, if there is any message in the queue, we print it (or in case of an invitation for example also handle the invitation) until there are no messages left. Once there are no messages left we wait for the input of the user on what to do, based on the current situation. (Either (`CONNCET <ip>` and `QUIT`), or (`CHAT <message>` and `QUIT`))

One thing that made this CLI approach significantly harder is the fact that `input()` is a blocking statement, so I had to find a workaround to waiting for input in a non-blocking way, allowing messages to come through.
You can read more about the need and oddities of the `select` library in the [Challenges section](#challenges) at the end of the document.

### Connecting to Daemon

Connecting to the Daemon happens automatically on start based on the host ip given when running the command `python3 simp_daemon.py 127.0.0.1`. There are three possible scenarios here:

1. There is a Daemon running already that is waiting for a client connection
   - the TCP connection simply goes through and we are given feedback about it on the logs for both the Client and Daemon
2. There is no Daemon running at the given host ip
   - the Client expects this via `ConnectionRefusedError`, logs that connection could not be made and exits
3. There is a Daemon running, but it is already occupied by a Client
   - In this case the Client trying to connect gets handled by a separate thread that notices based on the class flags, that it is occupied
   - Sends back the message `** DAEMON STATUS:  Another client is already connected.  **`, closes the connection and the Client exits

### Disconnecting from Dameon

As I have already described it in points 2 and 3 of the [Stopping the connection section of Daemon to Daemon](#stopping-the-connection), the user can quit at any given time using the `QUIT` command, but even if the user quits some other way, like a KeyboardInterrupt, the Daemon notices it and handles it accordingly.

> [!NOTE]
> The requirements stated that `The user will always have the option to quit (disconnect from the daemon) by pressing the key "q".`, I believe that the current solution suffices this description, but it would definitely be nice if I had also implemented a soft quit too, which simply disconnects from just the chat and not the whole application.
>
> This way to start a new chat, the user has to rerurn the Client.

## Challenges

Since the client was created as a simple CLI tool, always waiting for an answer from the user using `input()` would keep blocking the incoming messages from other threads. This is why I had to use the `select` library which allows for the manipulation of `stdin`.

Shortcomings:

- When the user has already written something to the `stdin` and a message comes in, that already written message is nulled, this could be annoying in a real setting.
  - This could be solved with some mechanism that also reads in the `stdin` before resetting it, then populating the new one with the old message, but I think this is outside of the scope of the project.
- The `select` library only operates on `stdin` on Linux systems, so the app won't work on Windows.
  - There is apparently a `msvcrt` module that can do the same for Windows systems, but as system agnosticity is not a requirement, I deemed this too as outside the scope of implementation.
