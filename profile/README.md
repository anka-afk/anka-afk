# Profile card rendering

Run `python3 profile/render.py` to fetch public data and render the cards. Node.js
22+ and Chrome are required; set `PROFILE_BROWSER` to use another Chromium browser.

Each successful external section is saved in `profile/cache/*.json`, including
its last successful fetch time. These files are committed with the rendered cards
so scheduled runs can reuse them on a fresh runner. Failed requests or invalid
responses keep the previous cache unchanged. If no usable cache exists, the
section displays "temporarily unavailable" instead of fabricated zero values.
Workflow warnings identify the affected source and the age of the reused data.

Transient requests get at most three attempts with exponential backoff. HTTP 429
uses 15/30-second delays and honors longer `Retry-After` values (seconds or HTTP
date). If the required wait exceeds 120 seconds, the section falls back immediately
instead of retrying before the server's cooldown expires. Permanent HTTP errors
are not retried. Rendering errors and programming errors still fail the job.

Run the offline regression tests with:

```sh
python3 -m unittest discover -s profile -p 'test_*.py' -v
```
