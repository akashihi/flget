import os
import platformdirs
from tomlkit import load, document, comment, nl, table, dump


class Config:
    def __init__(self):
        flget_config_dir = platformdirs.user_config_dir("flget", ensure_exists=True)
        flget_config = os.path.join(flget_config_dir, "flget.toml")

        self._flget_config = flget_config

        if os.path.exists(flget_config):
            with open(flget_config, "r") as config_file:
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

        with open(self._flget_config, "w") as config_file:
            dump(doc, config_file)

        self._libdir = path
