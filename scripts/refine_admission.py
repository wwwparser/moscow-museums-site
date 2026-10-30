"""Refresh evidence and enqueue sources needing internal Luna review."""
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(ROOT/'scripts/collect_admission.py'),'--stage','all','--refresh'],check=True)
subprocess.run([sys.executable,str(ROOT/'scripts/prepare_luna_queue.py')],check=True)
