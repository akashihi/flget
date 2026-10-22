# flget

Local Flibusta mirror search tool.

`flget` indexes a local Flibusta mirror (from an INPX file and/or the published
SQL dumps) and lets you search it from the command line.

## Usage

```
flget sync                       # build/refresh the local index
flget search book "<query>"      # search books
flget search author "<query>"    # search authors
flget search series "<query>"    # search series
flget search all "<query>"       # search all of the above
flget get <book_id> [target]     # extract a book from the mirror
```

### Search filters

`search book`, `search author`, `search series` and `search all` accept filters
that narrow results by book attributes:

- `-g/--genre <code>` — genre code (repeatable)
- `-f/--format <ext>` — file format (repeatable)
- `-l/--language <code>` — language code (repeatable)
- `--year-from` / `--year-to` — publication year range
- `--min-size` / `--max-size` — file size range (e.g. `500K`, `2M`, `1.5G`)

Discover the valid values with:

```
flget filters genres
flget filters formats
flget filters languages
```
