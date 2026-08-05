from pathlib import Path

import platformdirs
from tomlkit import comment, document, dump, load, nl, table


class Config:
    def __init__(self):
        flget_config_dir = platformdirs.user_config_dir("flget", ensure_exists=True)
        flget_config = Path(flget_config_dir) / "flget.toml"

        self._flget_config = flget_config

        if flget_config.exists():
            with flget_config.open() as config_file:
                doc = load(config_file)
                self._libdir = doc["flget"]["libdir"]
        else:
            self._libdir = platformdirs.user_documents_dir()

    def libdir(self):
        return self._libdir

    def set_libdir(self, path: str):
        doc = document()
        doc.add(comment("flget/fltui configuration file."))
        doc.add(nl())

        flget = table()
        flget.add("libdir", path)

        doc["flget"] = flget

        with self._flget_config.open("w") as config_file:
            dump(doc, config_file)

        self._libdir = path
