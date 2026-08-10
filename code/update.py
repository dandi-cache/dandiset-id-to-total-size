import argparse
import json
import pathlib

# Testing mode processes only this many dandisets and writes to its own designated files
# (`derivatives/testing.jsonl` and `testing_`-prefixed logs), leaving the real cache untouched.
_TESTING_LIMIT = 10
_CACHE_FILE_NAME = "dandiset_id_to_total_size.jsonl"
_TESTING_FILE_NAME = "testing.jsonl"

# Both source caches are registered as input subdatasets under `sourcedata` and publish their
# derivatives as JSON Lines (one single-key object per line).
#
#   content-id-to-usage-dandiset-path  {content_id: {dandiset_id: path}}
#   usage-dandiset-path-to-asset-size  {content_id: size_in_bytes}
#
# The first assigns every content id to exactly one dandiset (the usage determination); the
# second gives that content id's size. The join of the two, summed per dandiset id, is this
# cache.
_USAGE_PATH_SUBDATASET_NAME = "content-id-to-usage-dandiset-path"
_USAGE_PATH_FILE_NAME = "content_id_to_usage_dandiset_path.jsonl"
_ASSET_SIZE_SUBDATASET_NAME = "usage-dandiset-path-to-asset-size"
_ASSET_SIZE_FILE_NAME = "usage_dandiset_path_to_asset_size.jsonl"


def _load_source_mapping(base_directory: pathlib.Path, subdataset_name: str, file_name: str) -> dict:
    """Read a source cache's JSON Lines derivative into a single mapping."""
    file_path = base_directory / "sourcedata" / subdataset_name / "derivatives" / file_name
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    mapping: dict = {}
    with file_path.open(mode="r") as file_stream:
        for line in file_stream:
            if stripped_line := line.strip():
                mapping.update(json.loads(stripped_line))
    return mapping


def _run(base_directory: pathlib.Path, testing: bool) -> None:
    # Total the asset sizes of every dandiset, attributing each content id to the single
    # dandiset the usage determination assigned it to. A content id that appears in several
    # dandisets is therefore counted once, against its usage dandiset only, so the totals
    # across all dandisets sum to the deduplicated footprint of the archive rather than to the
    # sum of the per-dandiset apparent sizes.
    #
    # The join is a pure local computation over the two input subdatasets: no network access
    # and no state carried over from the previous run, so every run recomputes the cache in
    # full from the input commits pinned in its provenance.
    #
    # Sizes come from the asset-size cache, which is accumulative and lags its own source: a
    # content id whose size is not resolved yet (e.g. an embargoed dandiset) is simply absent
    # there. Those ids cannot contribute, so each total is a lower bound whenever the dandiset
    # has unresolved content ids; the counts are written to the logs alongside the cache.

    content_id_to_usage_dandiset_path = _load_source_mapping(
        base_directory, _USAGE_PATH_SUBDATASET_NAME, _USAGE_PATH_FILE_NAME
    )
    content_id_to_asset_size = _load_source_mapping(base_directory, _ASSET_SIZE_SUBDATASET_NAME, _ASSET_SIZE_FILE_NAME)
    print(
        f"Loaded {len(content_id_to_usage_dandiset_path)} usage paths and "
        f"{len(content_id_to_asset_size)} asset sizes.",
        flush=True,
    )

    # Each value is a single-entry `{dandiset_id: path}` mapping; only the dandiset id matters
    # here, since the size is keyed by content id.
    content_id_to_dandiset_id = {
        content_id: next(iter(dandiset_path))
        for content_id, dandiset_path in content_id_to_usage_dandiset_path.items()
        if dandiset_path
    }

    dandiset_ids = sorted(set(content_id_to_dandiset_id.values()))
    if testing:
        # Testing run: keep only the first few dandisets, so the run is fast but still
        # exercises the real join, the unresolved accounting, and the output writing.
        dandiset_ids = dandiset_ids[:_TESTING_LIMIT]
    targeted_dandiset_ids = set(dandiset_ids)
    print(f"Totalling asset sizes across {len(dandiset_ids)} dandisets.", flush=True)

    total_size_of: dict[str, int] = {dandiset_id: 0 for dandiset_id in dandiset_ids}
    resolved_count_of: dict[str, int] = {dandiset_id: 0 for dandiset_id in dandiset_ids}
    unresolved_count_of: dict[str, int] = {dandiset_id: 0 for dandiset_id in dandiset_ids}
    for content_id, dandiset_id in content_id_to_dandiset_id.items():
        if dandiset_id not in targeted_dandiset_ids:
            continue

        size = content_id_to_asset_size.get(content_id)
        if size is None:
            unresolved_count_of[dandiset_id] += 1
            continue

        total_size_of[dandiset_id] += size
        resolved_count_of[dandiset_id] += 1

    # A dandiset whose content ids are all unresolved would otherwise be published as a total
    # of zero, which reads as an empty dandiset rather than an unresolved one; omit it and let
    # the log account for it instead.
    records = [
        {dandiset_id: total_size_of[dandiset_id]} for dandiset_id in dandiset_ids if resolved_count_of[dandiset_id] > 0
    ]

    derivatives_directory = base_directory / "derivatives"
    derivatives_directory.mkdir(parents=True, exist_ok=True)

    # Testing runs write to their own designated files, so the real cache is never touched.
    output_file_path = derivatives_directory / (_TESTING_FILE_NAME if testing else _CACHE_FILE_NAME)
    print(f"Writing {len(records)} entries to {output_file_path}", flush=True)
    with output_file_path.open(mode="w") as file_stream:
        file_stream.writelines(f"{json.dumps(record)}\n" for record in records)

    # The log is rewritten in full on every run so it always reflects the current state of the
    # upstream data, and is saved into the derivatives dataset alongside the output for
    # provenance.
    incomplete_dandiset_ids = [dandiset_id for dandiset_id in dandiset_ids if unresolved_count_of[dandiset_id] > 0]
    print(
        f"{len(incomplete_dandiset_ids)} dandisets have at least one content id without a resolved size.",
        flush=True,
    )
    logs_directory = derivatives_directory / "logs"
    logs_directory.mkdir(parents=True, exist_ok=True)
    log_file_prefix = "testing_" if testing else ""
    with (logs_directory / f"{log_file_prefix}unresolved_asset_sizes.txt").open(mode="w") as file_stream:
        file_stream.writelines(
            f"dandiset_id={dandiset_id!r}, "
            f"unresolved_content_ids={unresolved_count_of[dandiset_id]}, "
            f"resolved_content_ids={resolved_count_of[dandiset_id]}\n"
            for dandiset_id in incomplete_dandiset_ids
        )


if __name__ == "__main__":
    default_base_directory = pathlib.Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Update the dandiset-id-to-total-size DANDI cache.")
    parser.add_argument(
        "--base-directory",
        type=pathlib.Path,
        default=default_base_directory,
        help=(
            "The directory containing the `sourcedata` and `derivatives` directories. "
            "Set to the mounted dataset path when run inside the pipeline container; "
            "defaults to the repository root."
        ),
    )
    parser.add_argument(
        "--testing",
        action="store_true",
        help=(
            f"Run in testing mode: process only the first {_TESTING_LIMIT} dandisets and write "
            f"`derivatives/{_TESTING_FILE_NAME}` (and `testing_`-prefixed logs) instead of the "
            "real cache, leaving it untouched. Omit for a complete update."
        ),
    )
    args = parser.parse_args()

    _run(base_directory=args.base_directory, testing=args.testing)
