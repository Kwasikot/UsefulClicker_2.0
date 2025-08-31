
import logging, sys
from pathlib import Path
def setup_logger(log_path: Path = None):
    logger = logging.getLogger("usefulclicker")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); logger.addHandler(sh)
    if log_path: 
        fh = logging.FileHandler(log_path, encoding="utf-8"); fh.setFormatter(fmt); logger.addHandler(fh)
    return logger
