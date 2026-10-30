"""Compatibility command: external provider checks are forbidden."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.llm_client import ExternalLLMDisabled

def main():
    raise ExternalLLMDisabled('External provider balance checks and probes are disabled. Run scripts/prepare_luna_queue.py.')

if __name__=='__main__': main()
