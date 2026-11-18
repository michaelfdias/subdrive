import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # o PGS é desenhado em vários processos ao mesmo tempo
    multiprocessing.set_start_method("spawn", force=True)  # o mesmo jeito em todo sistema (seguro com a janela aberta)
    from subdrive_app.app import main
    sys.exit(main())
