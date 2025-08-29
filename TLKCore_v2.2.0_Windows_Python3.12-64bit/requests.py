import socket

def transmit(client_socket,mgs):
    response = client_socket.recv(1024)
    print("Server:", response.decode('utf-8'))

    print("Connected to server. Type 'exit' to quit.")

    message = mgs
    message = str(message)  # Convert float to string
    

    client_socket.sendall(message.encode('utf-8'))
    return response
    # Optional: Receive reply from server
