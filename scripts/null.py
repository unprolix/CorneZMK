#!/usr/bin/env python3
import sys
import os
import subprocess
import argparse
from pathlib import Path

# Add the lib directory to the Python path so we can import the setup module
script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent
lib_dir = script_dir / "lib"
sys.path.insert(0, str(lib_dir))

# Import the setup module
import setup

def start_interactive_repl():
    """
    Start an interactive Python REPL using the venv's Python interpreter
    """
    # We're already in the venv at this point, so just start Python in interactive mode
    print("Starting interactive Python REPL...")
    os.execv(sys.executable, [sys.executable])

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Python utility script')
    parser.add_argument('--interactive', '-i', action='store_true', 
                        help='Start an interactive Python REPL using the venv\'s Python')
    args = parser.parse_args()
    
    # Initialize the virtual environment
    # This will re-execute this script under the venv if needed
    setup.initialize_venv()
    
    # If we get here, we're running in the venv
    
    # If interactive mode is requested, start the REPL
    if args.interactive:
        start_interactive_repl()
        return  # This won't actually be reached due to os.execv
    
    # Otherwise, list the libraries installed in the venv
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True)
    print(result.stdout)

if __name__ == "__main__":
    main()
