"""Entry point of the packaged program (SubDrive-CLI.exe and friends)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # the PGS drawing runs in parallel processes
    if len(sys.argv) == 1 and sys.stdout.isatty():  # double click: say something while it loads
        print("Abrindo o SubDrive CLI...", flush=True)
    from subdrive.cli import main
    sys.exit(main())
