# GR3 runner plan (not executable in this preparation)

`NO_RETRY_GUARANTEE=false` because the installed runtime reports
`max_retries=3` and exposes no supported
`--no-retry`/`--max-retries` flag. Therefore no runner is created and no
provider request is permitted. A future authorized revision must first provide
a supported one-attempt mechanism, then implement concurrency=1, micro-batch=10,
durable state, and global first-429/401/403 stop behavior.
