import multiprocessing
import sys

from .cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed by the packaged program (parallel PGS drawing)
    sys.exit(main())
