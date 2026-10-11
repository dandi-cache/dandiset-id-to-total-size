# DANDI Cache: `dandiset-id-to-total-size`

A cache mapping each Dandiset ID to the total size in bytes of the assets attributed to it.

Each record is a single-key JSON object mapping a Dandiset ID to its total size in bytes:

```json
{"000003": 8567810761}
```

The totals are derived by joining two upstream caches, both consumed as input subdatasets:

- [`dandi-cache/content-id-to-usage-dandiset-path`](https://github.com/dandi-cache/content-id-to-usage-dandiset-path) assigns every content ID to exactly one (Dandiset ID, asset path) pair — the *usage* determination.
- [`dandi-cache/usage-dandiset-path-to-asset-size`](https://github.com/dandi-cache/usage-dandiset-path-to-asset-size) gives each of those content IDs its size in bytes.

Every content ID is therefore counted exactly once, against its usage Dandiset only. A blob shared by several Dandisets contributes its bytes solely to the one the usage determination picked, so these totals sum to the deduplicated footprint of the archive rather than to the sum of the per-Dandiset apparent sizes — they are *not* the sizes the DANDI Archive reports for each Dandiset.

The upstream size cache is accumulative and lags its own source: a content ID whose size is not resolved yet (for example, one belonging to an embargoed Dandiset) is simply absent there and cannot contribute. A total is thus a lower bound whenever the Dandiset still has unresolved content IDs; those counts are published alongside the cache in [`derivatives/logs/unresolved_asset_sizes.txt`](https://github.com/dandi-cache/dandiset-id-to-total-size/blob/derivatives/derivatives/logs/unresolved_asset_sizes.txt), and a Dandiset with no resolved content IDs at all is omitted rather than published as a total of zero.

Updated frequently.

Primarily for use by developers.



## One-time use

`dist` publishes each output as a [Zarr](https://zarr.dev/) store: the cache itself is `derivatives/dandiset_id_to_total_size.zarr/`.
A store is one array of [JSON Lines](https://jsonlines.org/) text cut into chunk files, each holding whole lines and gzip-compressed.
Where a key appears more than once, the last line is its current entry, and the published copy has no repeats.
It can be read with the standard library alone, or opened remotely with any Zarr library.

### Python API (recommended)

Fetch `stream/zarr.json` for the array's length and chunk size, then each chunk in order:

```python
import gzip
import json
import math
import urllib.request

store = "https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-total-size/refs/heads/dist/derivatives/dandiset_id_to_total_size.zarr"


def fetch(path):
    with urllib.request.urlopen(f"{store}/{path}") as response:
        return response.read()


array = json.loads(fetch("stream/zarr.json"))
length = array["shape"][0]
chunk_bytes = array["chunk_grid"]["configuration"]["chunk_shape"][0]

dandiset_id_to_total_size = {}
for index in range(math.ceil(length / chunk_bytes)):
    for line in gzip.decompress(fetch(f"stream/c/{index}")).decode("utf-8").splitlines():
        if line.strip():
            dandiset_id_to_total_size.update(json.loads(line))
```

An entry is not filed under its key: the chunks hold the entries in the order they were recorded, so looking up one means reading through them.
To look up many, read it once as above, or clone the `derivatives` branch.

### Remote Zarr store

Anything that opens Zarr can open the store over HTTP, reading only the chunks it needs.
The group's `zarr.json` carries the array's metadata, so opening it takes one request:

```bash
pip install "zarr>=3" fsspec aiohttp
```

```python
import json

import zarr

url = "https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-total-size/refs/heads/dist/derivatives/dandiset_id_to_total_size.zarr"
stream = zarr.open_group(url, mode="r")["stream"]
print(stream.shape, stream.chunks)  # Bytes in all, and bytes per chunk.

# The first chunk, fetched and decompressed on its own: whole lines, each `{"<key>": <value>}`.
first_chunk = stream[: stream.chunks[0]].tobytes().decode("utf-8")
for line in first_chunk.splitlines():
    if line.strip():
        print(json.loads(line))
        break
```

Reading `stream[:]` returns the whole text; to read it in pieces, step through it by `stream.chunks[0]`, as each chunk is fetched whole.

### Save to file

A raw URL cannot be listed, so to fetch every chunk at once clone the `dist` branch, which holds nothing else:

```bash
git clone --branch dist --depth 1 https://github.com/dandi-cache/dandiset-id-to-total-size.git
```



## Repeated use

If you plan on using this cache regularly, clone the `derivatives` branch of this repository:

```bash
git clone --branch derivatives https://github.com/dandi-cache/dandiset-id-to-total-size.git
```

Or, if you prefer [DataLad](https://www.datalad.org/):

```bash
datalad clone https://github.com/dandi-cache/dandiset-id-to-total-size.git --branch derivatives
```

Then set up a CRON on your system to pull the latest version of the cache at your desired frequency.

For example, through `crontab -e`, add:

```bash
0 0 * * * git -C /path/to/dandiset-id-to-total-size pull
```

This will minimize data overhead by only loading the most recent changes.



### Local development

The container image is the authoritative runtime, but you can recreate the environment locally with [uv](https://docs.astral.sh/uv/) for debugging:

```bash
uv run --project envs python code/update.py --testing
```

The `--testing` flag processes only the first few Dandisets and writes `derivatives/testing_dandiset_id_to_total_size.zarr`, leaving the real cache untouched; omit it for a complete update. Either way, the two source caches must already be present under `sourcedata/` (the pipeline provides them as input subdatasets).

Each output is a store on the `derivatives` branch, where it is the whole log, uncompacted, and plain text:

```python
import json
import pathlib

chunks = pathlib.Path("dandiset-id-to-total-size/derivatives/dandiset_id_to_total_size.zarr/stream/c")
dandiset_id_to_total_size = {}
for chunk in sorted(chunks.iterdir(), key=lambda path: int(path.name)):
    for line in chunk.read_text().splitlines():
        if line.strip():
            dandiset_id_to_total_size.update(json.loads(line))  # A later line for a key replaces an earlier one.
```
