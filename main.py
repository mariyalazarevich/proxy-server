import socket
import threading


def handle_client(client_socket):
    log_url = "Unknown"

    server_socket = None
    logged_once = False
    try:
        request_data = client_socket.recv(4096)
        if not request_data:
            return

        request = request_data.decode('utf-8', errors='ignore')
        lines = request.split('\r\n')
        if not lines:
            client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return

        first_line = lines[0].split()
        if len(first_line) < 3:
            client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        method, uri, http_version = first_line

        host, port = None, 80
        if uri.startswith('http://'):
            uri_part = uri[7:].split('/', 1)
            host_port = uri_part[0]
            path = '/' + uri_part[1] if len(uri_part) > 1 else '/'
            if ':' in host_port:
                host, port_str = host_port.split(':', 1)
                port = int(port_str)
            else:
                host = host_port
        else:
            for line in lines[1:]:
                if line.lower().startswith('host:'):
                    host = line.split(':', 1)[1].strip()
                    if ':' in host:
                        host, port_str = host.split(':', 1)
                        port = int(port_str)
                    break
            if not host:
                client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            path = uri

        log_url = f"http://{host}:{port}{path}" if port != 80 else f"http://{host}{path}"
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.settimeout(15)
        try:
            server_socket.connect((host, port))
        except Exception as e:
            print(f"{log_url} - Connection Failed: {e}")
            client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return

        headers = [f"{method} {path} {http_version}"]
        host_header_added = False
        for line in lines[1:]:
            if not line.strip():
                break
            if line.lower().startswith('host:'):
                headers.append(f"Host: {host}")
                host_header_added = True
            else:
                headers.append(line)
        if not host_header_added:
            headers.append(f"Host: {host}")

        server_socket.sendall('\r\n'.join(headers).encode() + b'\r\n\r\n')
        while True:
            try:
                data = server_socket.recv(4096)
                if not data:
                    break
                if not logged_once:
                    try:
                        status_line = data.split(b'\r\n')[0].decode()
                        http_status = status_line.split(' ')[1]
                        print(f"{log_url} - {http_status}")
                        logged_once = True
                    except:
                        pass

                client_socket.sendall(data)
            except (socket.timeout, ConnectionResetError):
                break

    except Exception as e:
        if not logged_once:
            print(f"{log_url} - Processing Error: {str(e)}")
    finally:
        client_socket.close()
        if server_socket:
            server_socket.close()


def main():
    proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy.bind(('127.0.0.2', 8000))
    proxy.listen(5)
    print("Proxy server running on port 8000...")
    try:
        while True:
            client, addr = proxy.accept()
            threading.Thread(target=handle_client, args=(client,)).start()
    except KeyboardInterrupt:
        print("Shutting down proxy...")
    finally:
        proxy.close()

if __name__ == '__main__':
    main()