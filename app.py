import socket
import threading
import hashlib
import time
from datetime import datetime
from collections import OrderedDict
from urllib.parse import urlparse
import pandas as pd
import streamlit as st

# ==========================================
# 1. CORE NETWORKING & CACHE ENGINE
# ==========================================

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 8888
BUFFER_SIZE = 8192
CACHE_CAPACITY = 15

class IntelligentLRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.bytes_saved = 0
        self.logs = []

    def get(self, key):
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            self.hits += 1
            self.cache.move_to_end(key)
            entry = self.cache[key]
            self.bytes_saved += len(entry['data'])
            return entry

    def put(self, key, url, response_data):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            elif len(self.cache) >= self.capacity:
                self.cache.popitem(last=False)  # Evict least recently used

            self.cache[key] = {
                'url': url,
                'data': response_data,
                'cached_at': datetime.now().strftime("%H:%M:%S"),
                'size_kb': round(len(response_data) / 1024, 2)
            }

    def log_event(self, url, status, size_bytes, client_ip):
        with self.lock:
            self.logs.insert(0, {
                "Timestamp": datetime.now().strftime("%H:%M:%S"),
                "Client IP": client_ip,
                "Requested URL": url,
                "Status": status,
                "Size (KB)": round(size_bytes / 1024, 2)
            })
            if len(self.logs) > 50:
                self.logs.pop()

# Global Singleton Cache
if "global_cache" not in st.session_state:
    st.session_state.global_cache = IntelligentLRUCache(capacity=CACHE_CAPACITY)

cache = st.session_state.global_cache

def handle_client(client_socket, client_address):
    try:
        raw_request = client_socket.recv(BUFFER_SIZE)
        if not raw_request:
            return

        request_line = raw_request.decode('utf-8', errors='ignore').split('\r\n')[0]
        tokens = request_line.split()
        if len(tokens) < 3 or tokens[0] != 'GET':
            client_socket.sendall(b"HTTP/1.1 501 Not Implemented\r\n\r\nOnly GET supported.")
            return

        method, target_url, protocol = tokens[0], tokens[1], tokens[2]

        parsed = urlparse(target_url)
        host = parsed.hostname or target_url.split('/')[0]
        port = parsed.port or 80
        path = parsed.path if parsed.path else '/'
        if parsed.query:
            path += '?' + parsed.query

        cache_key = hashlib.md5(target_url.encode('utf-8')).hexdigest()
        cached_entry = cache.get(cache_key)

        # CACHE HIT
        if cached_entry:
            client_socket.sendall(cached_entry['data'])
            cache.log_event(target_url, "CACHE HIT (0ms upstream)", len(cached_entry['data']), client_address[0])
            return

        # CACHE MISS: Forward to origin server
        origin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        origin_socket.settimeout(6.0)
        origin_socket.connect((host, port))

        formatted_request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: IntelligentProxyDashboard/1.0\r\n"
            f"Connection: close\r\n\r\n"
        ).encode('utf-8')

        origin_socket.sendall(formatted_request)

        response_buffer = bytearray()
        while True:
            chunk = origin_socket.recv(BUFFER_SIZE)
            if not chunk:
                break
            response_buffer.extend(chunk)
        origin_socket.close()

        # Cache 200 OK responses
        if b"200 OK" in response_buffer[:100]:
            cache.put(cache_key, target_url, bytes(response_buffer))
            cache.log_event(target_url, "CACHE MISS (Saved)", len(response_buffer), client_address[0])
        else:
            cache.log_event(target_url, "CACHE MISS (Not Cached)", len(response_buffer), client_address[0])

        client_socket.sendall(response_buffer)

    except Exception as e:
        cache.log_event(target_url if 'target_url' in locals() else "Unknown", f"ERROR: {str(e)}", 0, client_address[0])
    finally:
        client_socket.close()

def run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((PROXY_HOST, PROXY_PORT))
        server.listen(50)
        while True:
            client_sock, client_addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, client_addr), daemon=True)
            t.start()
    except Exception as e:
        pass

# Start background server daemon only once
if "server_started" not in st.session_state:
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    st.session_state.server_started = True

# ==========================================
# 2. STREAMLIT CONTROL ROOM UI
# ==========================================

st.set_page_config(page_title="HTTP Proxy & Intelligent Cache Monitor", page_icon="🌐", layout="wide")

st.title("🌐 HTTP Proxy Server with Intelligent LRU Caching")
st.caption(f"Listening on `{PROXY_HOST}:{PROXY_PORT}` | Socket Multi-Threaded Daemon Active")

# Real-Time Telemetry Bar
total_reqs = cache.hits + cache.misses
hit_ratio = round((cache.hits / total_reqs * 100), 1) if total_reqs > 0 else 0.0
saved_kb = round(cache.bytes_saved / 1024, 2)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Requests", total_reqs)
col2.metric("Cache Hits", cache.hits)
col3.metric("Cache Misses", cache.misses)
col4.metric("Hit Ratio", f"{hit_ratio}%")
col5.metric("Bandwidth Saved", f"{saved_kb} KB")

st.markdown("---")

# Client Request Tester Section
st.subheader("🚀 Test Client Request Through Proxy")
st.write("Send test HTTP GET requests directly through the proxy to observe cache mechanics live.")

test_col1, test_col2 = st.columns([4, 1])

with test_col1:
    test_url = st.text_input(
        "Enter Plain HTTP URL to fetch:", 
        value="http://example.com/", 
        help="Use plain HTTP endpoints (e.g., http://example.com/, http://neverssl.com/)"
    )

with test_col2:
    st.write("") # spacing
    st.write("")
    send_btn = st.button("Send Request", use_container_width=True)

if send_btn and test_url:
    try:
        start_time = time.time()
        # Direct socket call through the proxy
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((PROXY_HOST, PROXY_PORT))
        req = f"GET {test_url} HTTP/1.1\r\nHost: {urlparse(test_url).hostname}\r\n\r\n"
        s.sendall(req.encode('utf-8'))
        
        resp = bytearray()
        while True:
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            resp.extend(chunk)
        s.close()
        elapsed = round((time.time() - start_time) * 1000, 2)
        
        st.success(f"Response Received in **{elapsed} ms** ({round(len(resp)/1024, 2)} KB)")
        with st.expander("View Raw HTTP Response Header & Body"):
            st.code(resp[:1000].decode('utf-8', errors='ignore'))
    except Exception as e:
        st.error(f"Request failed: {e}")

st.markdown("---")

# Split View: Live Logs & Active Cache State
log_col, cache_col = st.columns([3, 2])

with log_col:
    st.subheader("📋 Real-Time Request Activity Log")
    if cache.logs:
        df_logs = pd.DataFrame(cache.logs)
        st.dataframe(df_logs, use_container_width=True, height=300)
    else:
        st.info("No network requests recorded yet. Send a test request above!")

with cache_col:
    st.subheader(f"🧠 Active LRU Cache ({len(cache.cache)} / {CACHE_CAPACITY})")
    if cache.cache:
        cache_data = []
        for k, v in list(cache.cache.items()):
            cache_data.append({
                "Key (MD5)": k[:8] + "...",
                "URL": v['url'],
                "Size (KB)": v['size_kb'],
                "Cached At": v['cached_at']
            })
        st.dataframe(pd.DataFrame(cache_data), use_container_width=True, height=300)
    else:
        st.info("LRU cache is currently empty.")

# Refresh Button
if st.button("🔄 Refresh Telemetry"):
    st.rerun()
    #& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m streamlit run app.py