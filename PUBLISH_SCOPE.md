# Publication scope and integrity boundary

This repository is an archival export, not a new evaluation or a production
integration. It was assembled from two explicit source roots:

1. `/home/yanbo/net_vlm_person_fallen_v2_optimization`
2. `/home/yanbo/net_vlm_yanboversion/docs/person_fallen`

The source roots were not modified. Files were hard-linked into staging before
Git ingestion, and the staging copy was filtered only for generated/runtime
artifacts:

- Python `__pycache__/` directories and `*.pyc`/`*.pyo`/`*.pyd` files
- SQLite `*.sqlite3-wal`, `*.sqlite3-shm`, and `*.sqlite-journal` sidecars

All substantive event files, including images, raw response records, manifests,
reports, freeze files, ledgers, scripts, and lock/completion evidence, remain in
the archive. No production worktree files or unrelated events were copied.

The destination repository is public. The event handoff and README state the
result limitations and disclosure risks. The GitHub credential used for transport
is never written to a file, remote URL, commit, or report.
