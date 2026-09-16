"""The total size in bytes of every Dandiset's assets, deduplicated across the archive.

A join of two upstream caches and nothing else: no network, and no state carried from the previous
run, so every run recomputes the whole cache from the input commits its provenance pins.

    content-id-to-usage-dandiset-path   {content_id: {dandiset_id: path}}
    usage-dandiset-path-to-asset-size   {content_id: size_in_bytes}

The first assigns each content ID to exactly one Dandiset, so a blob shared by several Dandisets
is counted once, against its usage Dandiset only. The totals therefore sum to the deduplicated
footprint of the archive rather than to the sum of the per-Dandiset apparent sizes.

Sizes come from the asset-size cache, which is accumulative and lags its own source: a content ID
whose size is not resolved yet is simply absent there. Each total is therefore a lower bound
whenever its Dandiset still has unresolved content IDs, and the accounting for that is written
beside the cache rather than folded into it.

Everything shared -- the argument parsing, the logging, the input reading, the output paths,
testing mode and the JSON Lines writing -- comes from `dandi_cache_utils`.
"""

import dandi_cache_utils as dandi_cache

#: Named beside the cache rather than inside it: a total is a number, and "how much of this
#: Dandiset could not be resolved" is a different question about the same run.
UNRESOLVED_LOG_NAME = "unresolved_asset_sizes.txt"


def main() -> None:
    dataset, arguments = dandi_cache.open_dataset()

    usage_dandiset_path = dataset.read_input("content-id-to-usage-dandiset-path")
    asset_size = dataset.read_input("usage-dandiset-path-to-asset-size")
    dandi_cache.logger.info("Loaded %d usage paths and %d asset sizes.", len(usage_dandiset_path), len(asset_size))

    # Each value is a single-entry `{dandiset_id: path}`; only the Dandiset ID matters here, since
    # the size is keyed by content ID.
    dandiset_of = {
        content_id: next(iter(dandiset_path))
        for content_id, dandiset_path in usage_dandiset_path.items()
        if dandiset_path
    }

    dandiset_ids = sorted(set(dandiset_of.values()))
    if dataset.testing:
        dandiset_ids = dandiset_ids[: dandi_cache.TESTING_LIMIT]
    targeted = set(dandiset_ids)
    dandi_cache.logger.info("Totalling asset sizes across %d Dandisets.", len(dandiset_ids))

    total_of = dict.fromkeys(dandiset_ids, 0)
    resolved_of = dict.fromkeys(dandiset_ids, 0)
    unresolved_of = dict.fromkeys(dandiset_ids, 0)
    for content_id, dandiset_id in dandiset_of.items():
        if dandiset_id not in targeted:
            continue
        size = asset_size.get(content_id)
        if size is None:
            unresolved_of[dandiset_id] += 1
            continue
        total_of[dandiset_id] += size
        resolved_of[dandiset_id] += 1

    def build() -> list[dict]:
        # A Dandiset whose content IDs are all unresolved would otherwise publish as a total of
        # zero, which reads as an empty Dandiset rather than an unresolved one. Leave it out and
        # let the log account for it.
        return [{dandiset_id: total_of[dandiset_id]} for dandiset_id in dandiset_ids if resolved_of[dandiset_id] > 0]

    dandi_cache.run_full_rebuild(dataset, build=build, limit=arguments.limit)

    # Rewritten in full every run, so it always describes the current state of the upstream data
    # rather than accumulating history.
    incomplete = [dandiset_id for dandiset_id in dandiset_ids if unresolved_of[dandiset_id] > 0]
    dandi_cache.logger.info("%d Dandisets have at least one content ID without a resolved size.", len(incomplete))
    dataset.logs_directory.mkdir(parents=True, exist_ok=True)
    log_file_path = dataset.logs_directory / f"{dataset.log_prefix}{UNRESOLVED_LOG_NAME}"
    with log_file_path.open(mode="w") as file_stream:
        file_stream.writelines(
            f"dandiset_id={dandiset_id!r}, "
            f"unresolved_content_ids={unresolved_of[dandiset_id]}, "
            f"resolved_content_ids={resolved_of[dandiset_id]}\n"
            for dandiset_id in incomplete
        )


if __name__ == "__main__":
    main()
