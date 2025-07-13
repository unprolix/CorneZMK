#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path
import venv

LIB_DIR = Path(__file__).resolve().parent
PROJECT_DIR = LIB_DIR.parent.parent
PROJECT_NAME = "jjb-zmk"
VAR_DIR = Path.home() / ".local" / "var" / PROJECT_NAME
VENV_DIR = VAR_DIR / "venv"
VENV_DIR.mkdir(parents=True, exist_ok=True)

def is_in_venv():
    """Check if the current Python interpreter is running inside the project's venv"""
    return (
        hasattr(sys, 'real_prefix') or 
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) and
        Path(sys.prefix).resolve() == VENV_DIR.resolve()
    )

def initialize_venv(pip_modules=None):
    """
    Ensure a virtual environment exists in var/venv in the project directory.
    Create it if absent, then upgrade pip and install/update the given pip_modules.
    If not already running in the venv, re-execute the current script under the venv.

    Args:
        pip_modules (list[str] or None): List of pip modules to install/update. If None, no modules are installed.
    """
    if pip_modules is None:
        pip_modules = []

    if is_in_venv():
        print("Already running in the virtual environment")
        return None

    if sys.platform == 'win32':
        python_executable = VENV_DIR / "Scripts" / "python.exe"
    else:
        python_executable = VENV_DIR / "bin" / "python"

    if not python_executable.exists():
        print(f"Creating virtual environment in {VENV_DIR}")
        venv.create(VENV_DIR, with_pip=True)
    else:
        print(f"Virtual environment already exists in {VENV_DIR}")

    if not python_executable.exists():
        print(f"Error: venv python executable not found at {python_executable}")
        sys.exit(1)

    print("Upgrading pip...")
    subprocess.run([str(python_executable), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    for module in pip_modules:
        print(f"Installing/updating {module}...")
        subprocess.run([str(python_executable), "-m", "pip", "install", "--upgrade", module], check=True)

    if len(sys.argv) > 0:
        original_script = Path(sys.argv[0]).resolve()
        print(f"Re-executing {original_script} with the venv Python interpreter")
        os.execv(str(python_executable), [str(python_executable), str(original_script)] + sys.argv[1:])

    return str(python_executable)


if __name__ == "__main__":
    # Test the module
    initialize_venv()
