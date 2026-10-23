# Multi-Threaded HTTP Proxy Server with LRU Caching & Streamlit Telemetry

A high-performance, multithreaded HTTP caching proxy server built from low-level Python TCP sockets. The project features an in-memory Least Recently Used (LRU) cache with $\mathcal{O}(1)$ eviction, thread synchronization, real-time bandwidth savings quantification, and an interactive Streamlit telemetry dashboard.

---

## Key Features

- **Low-Level Socket Architecture:** Implements raw TCP socket handling on `127.0.0.1:8888` via Python's built-in `socket` library.
- **Multithreaded Concurrency:** Spawns isolated worker threads via `threading.Thread` per client request to prevent I/O blocking.
- **$\mathcal{O}(1)$ LRU Cache Engine:** Implements cache eviction using thread-safe `collections.OrderedDict` protected by re-entrant mutex locks (`threading.Lock`).
- **Telemetry Dashboard:** Live web-based instrumentation panel tracking hit/miss ratios, round-trip latency, bytes saved, and cache memory states.

---

## Prerequisites

- **Python 3.10+** (Tested on Python 3.13)
- Windows PowerShell, Command Prompt, or Linux/macOS terminal

---

## Installation & Setup

### 1. Clone or Navigate to the Project Folder
Open your terminal and ensure you are in the project root directory:

```bash
cd C:\Users\username\OneDrive\Desktop\cn_proxy_server


& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m pip install streamlit pandas

---
## YOUTUBE VIDEO LINK
https://youtu.be/N_heo-BIv9g?si=EKfISfUlzkMf9yjU
