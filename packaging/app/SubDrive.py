"""Ponto de entrada do SubDrive com janelas empacotado (SubDrive.exe, SubDrive, SubDrive.app)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # o PGS é desenhado em vários processos
    multiprocessing.set_start_method("spawn", force=True)
    from subdrive_app.app import main
    sys.exit(main())
