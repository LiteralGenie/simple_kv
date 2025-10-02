from pathlib import Path

SRC_DIR = Path(__file__).parent.parent
ROOT_DIR = SRC_DIR.parent

DATA_DIR = ROOT_DIR / "data"
LOG_DIR = DATA_DIR / "logs"

for dir in [DATA_DIR, LOG_DIR]:
    dir.mkdir(exist_ok=True)
