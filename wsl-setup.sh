#!/bin/bash
# WSL Ubuntu proper-MPI setup (run INSIDE Ubuntu, not PowerShell)
# Usage: bash wsl-setup.sh
set -e
sudo apt update
sudo apt install -y mpich python3-pip python3-venv
python3 -m pip install --upgrade pip
pip3 install flask numpy mpi4py
echo "--- verify ---"
mpirun -np 4 python3 sensor_mpi.py --ticks 5 --delay 0
echo "OK: MPI works. Start dashboard with: python3 app.py"
