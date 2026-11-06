"""Entry point of the packaged program (SubDrive.exe and friends)."""
import multiprocessing
import sys

from subdrive.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # the PGS drawing runs in parallel processes
    sys.exit(main())
