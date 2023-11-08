from pathlib import Path

def remove_files(files: list[str]):
    for file in files:
        try:
            Path(file).unlink()
        except FileNotFoundError:
            pass
        except PermissionError:
            pass
