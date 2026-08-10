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

If you only plan to use this cache infrequently or from disparate locations, you can directly download the latest version of the cache as a compressed [JSON Lines](https://jsonlines.org/) file from the `dist` branch:

### Python API (recommended)

```python
import gzip
import json

import requests

url = "https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-total-size/refs/heads/dist/derivatives/dandiset_id_to_total_size.jsonl.gz"
response = requests.get(url)
lines = gzip.decompress(data=response.content).decode("utf-8").splitlines()
dandiset_id_to_total_size = [json.loads(line) for line in lines]
```

### Save to file

```bash
curl https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-total-size/refs/heads/dist/derivatives/dandiset_id_to_total_size.jsonl.gz -o dandiset_id_to_total_size.jsonl.gz
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

The `--testing` flag processes only the first few Dandisets and writes `derivatives/testing.jsonl`, leaving the real cache untouched; omit it for a complete update. Either way, the two source caches must already be present under `sourcedata/` (the pipeline provides them as input subdatasets).
