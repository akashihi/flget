import os
import zipfile
from pathlib import Path
from inpx import INPX


def list_unknown_archives(path: str, inpx: INPX) -> list[str]:
    unknown_archives = []
    for filename in os.listdir(path):
        if filename.lower().endswith(".zip"):
            if Path(filename.lower()).stem not in inpx.archives():
                unknown_archives.append(filename)
    return unknown_archives

def list_unknown_entries(path: str, inpx: INPX) -> list[str]:
    unknown_entries = []
    for archive in inpx.archives():
        archivepath = os.path.join(path, f"{archive}.zip")
        with zipfile.ZipFile(archivepath, "r") as zip:
            for member in zip.namelist():
                file_id = Path(member).stem
                if not inpx.exists(file_id):
                    unknown_entries.append(file_id)
    return unknown_entries