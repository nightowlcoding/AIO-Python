#!/bin/bash
# This script sets up an Intel (x86_64) Conda environment for dlib/face_recognition on Apple Silicon Macs using Rosetta.
# Run this script from a Terminal launched with Rosetta (see instructions below).

set -e

# 1. Check if running under Rosetta
arch_name=$(uname -m)
if [[ "$arch_name" != "x86_64" ]]; then
  echo "[ERROR] You must run this script from a Terminal opened with Rosetta (x86_64)."
  echo "See instructions: Duplicate Terminal.app, Get Info, check 'Open using Rosetta', then open."
  exit 1
fi

echo "[INFO] Running under Rosetta (x86_64)."

# 2. Download and install Miniforge (Intel/x86_64) if not already installed
if ! command -v conda &> /dev/null; then
  echo "[INFO] Installing Miniforge (Intel/x86_64)..."
  curl -LO https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-x86_64.sh
  bash Miniforge3-MacOSX-x86_64.sh -b -p "$HOME/miniforge3-x86_64"
  export PATH="$HOME/miniforge3-x86_64/bin:$PATH"
  echo 'export PATH="$HOME/miniforge3-x86_64/bin:$PATH"' >> ~/.zshrc
else
  echo "[INFO] Conda already installed."
fi

# 3. Initialize conda for zsh
conda init zsh
source ~/.zshrc

# 4. Create the environment with all required packages
if conda env list | grep -q aiointel; then
  echo "[INFO] Conda environment 'aiointel' already exists."
else
  echo "[INFO] Creating conda environment 'aiointel' with Python 3.10 and all required packages..."
  conda create -y -n aiointel python=3.10 pillow pytesseract pypdf dlib face_recognition
fi

echo "[INFO] To activate the environment, run:"
echo "    conda activate aiointel"
echo "[INFO] To run your program, use:"
echo "    python /Users/arnoldoramirezjr/Documents/AIO\ Python/Sorting\ App/AIO_File_Organizer_GUI.py"
