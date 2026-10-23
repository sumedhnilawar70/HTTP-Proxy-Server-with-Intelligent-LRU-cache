import socket
import threading
import hashlib
import time
from collections import OrderedDict
from urllib.parse import urlparse

# Configuration
PROXY_HOST = '127.0.0.1'
PROXY_PORT = 8888
BUFFER_SIZE = 8192
CACHE_CAPACITY = 20  # Max cached items before LRU eviction

class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            self.hits += 1
            # Move accessed entry to end (marks as most recently used)
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key, response_data):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            elif len(self.cache) >= self.capacity:
                evicted_key, _ = self.cache.popitem(last=False)  # Evict least recently used
                print(f"[CACHE EVICTION] Evicted LRU object: {evicted_key[:8]}...")
            self.cache[key] = {
                'data': response_data,
                'cached_at': time.time()
            }

    def stats(self):
        total = self.hits + self.misses
        hit_ratio = (self.hits / total * 100) if total > 0 else 0
        return f"Hits: {self.hits} | Misses: {self.misses} | Hit Ratio: {hit_ratio:.1f}%"

cache = LRUCache(capacity=CACHE_CAPACITY)

def handle_client(client_socket, client_address):
    try:
        raw_request = client_socket.recv(BUFFER_SIZE)
        if not raw_request:
            client_socket.close()
            return

        request_line = raw_request.decode('utf-8', errors='ignore').split('\r\n')[0]
        print(f"\n[REQUEST] {client_address[0]}:{client_address[1]} -> {request_line}")

        tokens = request_line.split()
        if len(tokens) < 3:
            client_socket.close()
            return

        method, target_url, protocol = tokens[0], tokens[1], tokens[2]

        # Only cache GET requests
        if method != 'GET':
            client_socket.sendall(b"HTTP/1.1 501 Not Implemented\r\n\r\nOnly GET supported.")
            client_socket.close()
            return

        # Parse destination host and port
        parsed = urlparse(target_url)
        host = parsed.hostname or target_url.split('/')[0]
        port = parsed.port or 80
        path = parsed.path if parsed.path else '/'
        if parsed.query:
            path += '?' + parsed.query

        # Generate cache key (MD5 hash of URL)
        cache_key = hashlib.md5(target_url.encode('utf-8')).hexdigest()
        cached_entry = cache.get(cache_key)

        # Cache HIT: Serve directly to client
        if cached_entry:
            print(f"[CACHE HIT] Serving from memory: {target_url} [{cache.stats()}]")
            client_socket.sendall(cached_entry['data'])
            client_socket.close()
            return

        # Cache MISS: Forward request to origin web server
        print(f"[CACHE MISS] Fetching from origin: {host}:{port} [{cache.stats()}]")
        origin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        origin_socket.settimeout(5.0)
        origin_socket.connect((host, port))

        # Construct raw HTTP request for origin
        formatted_request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: Custom-Python-Proxy/1.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode('utf-8')

        origin_socket.sendall(formatted_request)

        # Receive complete response from origin
        response_buffer = bytearray()
        while True:
            chunk = origin_socket.recv(BUFFER_SIZE)
            if not chunk:
                break
            response_buffer.extend(chunk)

        origin_socket.close()

        # Cache successful 200 OK responses
        if b"200 OK" in response_buffer[:100]:
            cache.put(cache_key, bytes(response_buffer))
            print(f"[CACHE STORED] Saved {len(response_buffer)} bytes to cache.")

        # Relay origin response back to client
        client_socket.sendall(response_buffer)

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        client_socket.close()

def start_proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(50)
    print(f"=====================================================")
    print(f" HTTP Proxy Server active on http://{PROXY_HOST}:{PROXY_PORT}")
    print(f" Cache Policy: LRU (Capacity: {CACHE_CAPACITY})")
    print(f"=====================================================")

    while True:
        client_sock, client_addr = server.accept()
        # Spawn one worker thread per incoming request
        thread = threading.Thread(target=handle_client, args=(client_sock, client_addr), daemon=True)
        thread.start()

if __name__ == "__main__":
    start_proxy()