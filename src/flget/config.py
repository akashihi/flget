from pathlib import Path
from typing import Any, cast

import platformdirs
from tomlkit import comment, document, dump, load, nl, table


class Config:
    def __init__(self) -> None:
        flget_config_dir = platformdirs.user_config_dir("flget", ensure_exists=True)
        flget_config = Path(flget_config_dir) / "flget.toml"

        self._flget_config = flget_config

        self._libdir: Path | None = None
        if flget_config.exists():
            with flget_config.open() as config_file:
                doc = load(config_file)
                self._libdir = Path(str(cast("Any", doc)["flget"]["libdir"]))

    def libdir(self) -> Path | None:
        return self._libdir

    def require_libdir(self) -> Path:
        if self._libdir is None:
            msg = "Library location is not set"
            raise RuntimeError(msg)
        return self._libdir

    def set_libdir(self, path: Path) -> None:
        self._libdir = path

    def save(self) -> None:
        doc = document()
        doc.add(comment("flget/fltui configuration file."))
        doc.add(nl())

        flget = table()
        flget.add("libdir", str(self.require_libdir()))

        doc["flget"] = flget

        with self._flget_config.open("w") as config_file:
            dump(doc, config_file)
