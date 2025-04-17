import socket
import re
import select
from urllib.parse import urlparse


def log_request(url, status_code, client_ip):
    """Функция для ведения журнала с IP клиента"""
    print(f"[{client_ip}] {url} {status_code}")


def parse_http_request(request):
    """Парсер HTTP-запросов"""
    try:
        headers_part = request.split('\r\n\r\n', 1)[0]
        lines = headers_part.split('\r\n')

        if not lines:
            return None, None, None, None

        first_line = lines[0].strip()

        if first_line.startswith('CONNECT '):
            return None, None, None, None

        match = re.match(r'^([A-Z]+)\s+(https?://[^\s]+|[^\s]+)\s+HTTP/1\.[01]$', first_line)
        if not match:
            return None, None, None, None

        method, url = match.groups()

        if url.startswith(('http://', 'https://')):
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            original_url = url
        else:
            path = url
            original_url = None
            host = None
            port = 80

        headers = {}
        for line in lines[1:]:
            if ':' in line:
                key, val = line.split(':', 1)
                headers[key.strip().lower()] = val.strip()
                if key.strip().lower() == 'host':
                    host_part = val.strip()
                    if ':' in host_part:
                        host, port_str = host_part.split(':', 1)
                        try:
                            port = int(port_str)
                        except ValueError:
                            pass
                    else:
                        host = host_part

        if not host:
            return None, None, None, None

        new_request = f"{method} {path} HTTP/1.1\r\n"
        for k, v in headers.items():
            if k not in ['proxy-connection', 'connection']:
                new_request += f"{k}: {v}\r\n"
        new_request += "\r\n"

        final_url = original_url or f"http://{host}{path}"
        return host, port, new_request, final_url

    except Exception as e:
        return None, None, None, None


def handle_client(client_sock, client_addr):
    """Обработка клиентского подключения"""
    server_sock = None
    try:
        # Получаем первый пакет данных от клиента
        data = client_sock.recv(4096)
        if not data:
            client_sock.close()
            return

        # Парсим HTTP-запрос
        try:
            request = data.decode('utf-8')
        except UnicodeDecodeError:
            request = data.decode('latin-1')

        host, port, new_req, orig_url = parse_http_request(request)
        if not all([host, port, new_req]):
            client_sock.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            client_sock.close()
            return

        # Устанавливаем соединение с целевым сервером
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((host, port))
        server_sock.setblocking(False)
        client_sock.setblocking(False)

        # Отправляем первоначальный запрос
        server_sock.sendall(new_req.encode('utf-8'))

        status_code = "000"
        headers_received = False
        timeout = 300  # 5 минут для потоковых соединений

        while True:
            # Используем select для обработки множественных соединений
            rlist, _, xlist = select.select(
                [server_sock, client_sock],
                [],
                [server_sock, client_sock],
                timeout
            )

            if xlist:
                break

            for sock in rlist:
                try:
                    if sock is server_sock:
                        # Данные от сервера -> клиенту
                        chunk = server_sock.recv(4096)
                        if not chunk:
                            break

                        # Извлечение статус-кода из первого чанка
                        if not headers_received:
                            try:
                                headers_end = chunk.find(b'\r\n\r\n')
                                headers_part = chunk[:headers_end] if headers_end != -1 else chunk
                                status_line = headers_part.split(b'\r\n')[0].decode('utf-8', 'ignore')
                                status_parts = status_line.split()
                                if len(status_parts) > 1:
                                    status_code = status_parts[1]
                                headers_received = True
                            except Exception:
                                pass

                        # Пересылка данных клиенту
                        try:
                            client_sock.sendall(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            break

                    else:
                        # Данные от клиента -> серверу
                        chunk = client_sock.recv(4096)
                        if chunk:
                            server_sock.sendall(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    break
                except BlockingIOError:
                    continue

            else:
                continue
            break

        log_request(orig_url, status_code, client_addr[0])

    except (socket.timeout, ConnectionRefusedError) as e:
        log_request(orig_url, "ERR", client_addr[0])
    except Exception as e:
        pass
    finally:
        try:
            client_sock.close()
        except:
            pass
        try:
            if server_sock:
                server_sock.close()
        except:
            pass


def start_proxy(host='0.0.0.0', port=8888):
    """Запуск прокси-сервера"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            s.listen(5)
            print(f"Proxy server started on {host}:{port}")

            while True:
                try:
                    conn, addr = s.accept()
                    handle_client(conn, addr)
                except KeyboardInterrupt:
                    print("\nShutting down proxy server...")
                    break
                except Exception:
                    continue

    except Exception as e:
        print(f"Failed to start proxy: {e}")


if __name__ == '__main__':
    start_proxy()