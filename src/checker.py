"""High-concurrency async dead-link checker with 1x retry on flaky errors.

Bounded worker pool -> memory-safe for 200k+ URLs. Each URL fetched once
(minimal read). Timeouts/connection errors are retried up to `retries` times;
a definitive bad HTTP status is NOT retried (it won't change).
"""
import asyncio
import aiohttp

ALIVE_STATUS = (200, 206)


async def _check(session, url, headers, timeout, hls_verify, retries):
    attempt = 0
    while True:
        try:
            async with session.get(
                url, headers=headers, timeout=timeout, allow_redirects=True
            ) as r:
                if r.status not in ALIVE_STATUS:
                    return False
                ctype = r.headers.get("Content-Type", "").lower()
                if hls_verify and (".m3u8" in url.lower() or "mpegurl" in ctype):
                    chunk = await r.content.read(256)
                    return b"#EXT" in chunk
                return True
        except Exception:
            if attempt >= retries:
                return False
            attempt += 1
            await asyncio.sleep(0.4)


async def run_checks(url_headers, concurrency, total, connect, hls_verify, retries=1):
    """url_headers: {url: {header: value}} -> returns {url: bool}."""
    urls = list(url_headers.keys())
    n = len(urls)
    results = {}
    queue = asyncio.Queue()
    for u in urls:
        queue.put_nowait(u)

    timeout = aiohttp.ClientTimeout(
        total=total, connect=connect, sock_connect=connect, sock_read=total
    )
    connector = aiohttp.TCPConnector(
        limit=concurrency, limit_per_host=40, ttl_dns_cache=300,
        ssl=False, enable_cleanup_closed=True,
    )

    done = 0
    async with aiohttp.ClientSession(connector=connector) as session:
        async def worker():
            nonlocal done
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                results[url] = await _check(
                    session, url, url_headers[url], timeout, hls_verify, retries
                )
                done += 1
                if done % 2000 == 0:
                    print(f"[check] {done}/{n}", flush=True)

        await asyncio.gather(*[asyncio.create_task(worker()) for _ in range(concurrency)])

    return results
