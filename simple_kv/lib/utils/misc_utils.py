from pathlib import Path


def to_path(x: str | Path) -> Path:
    fp = x
    if isinstance(fp, str):
        fp = Path(fp)
    return fp
