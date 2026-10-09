"""Serve only the web directory, on loopback. No secrets or raw-data exposure."""
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--port', type=int, default=8765)
args = ap.parse_args()
root = Path(__file__).resolve().parent/'web'
print(f'Local: http://127.0.0.1:{args.port}', flush=True)
ThreadingHTTPServer(('127.0.0.1', args.port), partial(SimpleHTTPRequestHandler, directory=str(root))).serve_forever()
