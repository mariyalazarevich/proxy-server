import socket
import threading


def handle_client(client_socket):
    log_url = "Unknown"
    server_socket = None
    logged_once = False  # Flag to track if log was already printed for this request

    try:
        # Reading the HTTP request
        request_data = client_socket.recv(4096)
        if not request_data:
            return

        request = request_data.decode('utf-8', errors='ignore')
        lines = request.split('\r\n')
        if not lines:
            client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return

        first_line = lines[0]
        parts = first_line.split()
        if len(parts) < 3:
            client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return

        method, uri, http_version = parts[0], parts[1], parts[2]

        host, port, path = None, 80, uri
        if uri.startswith('http://'):
            uri_part = uri.split('://', 1)[1]
            host_port_path = uri_part.split('/', 1)
            host_port = host_port_path[0]
            path = '/' + host_port_path[1] if len(host_port_path) > 1 else '/'
            if ':' in host_port:
                host, port_str = host_port.split(':', 1)
                port = int(port_str)
            else:
                host = host_port
        else:
            for line in lines[1:]:
                if line.lower().startswith('host:'):
                    host_header = line.split(':', 1)[1].strip()
                    if ':' in host_header:
                        host, port_str = host_header.split(':', 1)
                        port = int(port_str)
                    else:
                        host = host_header
                    break
            if not host:
                client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return

        log_url = f"http://{host}:{port}{path}" if port != 80 else f"http://{host}{path}"

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.settimeout(5)
        try:
            server_socket.connect((host, port))
        except Exception as e:
            if not logged_once:  # Log only once per request
                print(f"{log_url} - Connection Failed: {e}")
                logged_once = True
            client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return

        new_headers = []
        host_added = False
        for line in lines[1:]:
            if not line.strip():
                break
            if line.lower().startswith('host:'):
                new_headers.append(f"Host: {host}")
                host_added = True
            else:
                new_headers.append(line)
        if not host_added:
            new_headers.append(f"Host: {host}")

        modified_request = f"{method} {path} {http_version}\r\n" + '\r\n'.join(new_headers) + "\r\n\r\n"
        server_socket.sendall(modified_request.encode())

        response = server_socket.recv(4096)
        if response:
            try:
                status_line = response.split(b'\r\n')[0].decode('utf-8', errors='ignore')
                http_status = status_line.split(' ')[1]
            except Exception:
                http_status = 'Unknown'
            if not logged_once:  # Log only once per request
                print(f"{log_url} - {http_status}")
                logged_once = True

            client_socket.sendall(response)
            while True:
                data = server_socket.recv(4096)
                if not data:
                    break
                client_socket.sendall(data)

    except Exception as e:
        if not logged_once:  # Log only once per request
            print(f"{log_url} - Error: {e}")
            logged_once = True
    finally:
        client_socket.close()
        if server_socket:
            server_socket.close()


def main():
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.bind(('0.0.0.0', 8000))
    proxy.listen(5)
    print("Proxy running on port 8000...")

    try:
        while True:
            client, _ = proxy.accept()
            threading.Thread(target=handle_client, args=(client,)).start()
    except KeyboardInterrupt:
        print("Stopping proxy...")
    finally:
        proxy.close()

if __name__ == '__main__':
    main()
