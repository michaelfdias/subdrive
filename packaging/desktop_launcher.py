if __name__ == "__main__":
    # Must run before importing/creating Qt: PGS uses a process pool, and frozen
    # Windows/macOS workers otherwise open another GUI instead of rendering.
    import multiprocessing
    multiprocessing.freeze_support()
    from subdrive.desktop import main
    raise SystemExit(main())
