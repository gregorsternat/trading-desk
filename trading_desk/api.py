"""Allowlisted Hyperliquid /info client. No keys, wallet storage, or /exchange."""
import json
import math
import time
import urllib.error
import urllib.request

INFO = "https://api.hyperliquid.xyz/info"
ALLOWED = {
    "metaAndAssetCtxs", "meta", "perpDexs", "l2Book", "candleSnapshot",
    "clearinghouseState", "spotClearinghouseState", "frontendOpenOrders",
    "userFillsByTime", "userFunding", "userNonFundingLedgerUpdates", "userFees",
    "userAbstraction", "maxMarketOrderNtls",
}


class DataError(RuntimeError):
    pass


def request_weight(kind, result=None):
    base = 2 if kind in ("l2Book", "clearinghouseState", "spotClearinghouseState") else 20
    if isinstance(result, list):
        if kind == "candleSnapshot":
            base += math.ceil(len(result) / 60)
        elif kind in ("userFillsByTime", "userFunding", "userNonFundingLedgerUpdates"):
            base += math.ceil(len(result) / 20)
    return base


class InfoClient:
    def __init__(self, interval=0.65, timeout=20):
        self.interval = interval
        self.timeout = timeout
        self.last_request = 0
        self.next_request = 0
        self.requests = 0

    def post(self, kind, **params):
        if kind not in ALLOWED:
            raise ValueError("Unsupported read-only info request")
        payload = json.dumps(dict(type=kind, **params)).encode()
        for attempt in range(3):
            time.sleep(max(0, self.next_request - time.monotonic()))
            self.last_request = time.monotonic()
            self.next_request = self.last_request + max(self.interval, request_weight(kind) / 15)
            self.requests += 1
            request = urllib.request.Request(INFO, data=payload, headers={
                "Content-Type": "application/json", "User-Agent": "personal-trading-desk/0.1"
            })
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    result = json.load(response)
                # Pace at ~900 weight/min, below the shared 1200/min IP ceiling.
                self.next_request = self.last_request + max(self.interval, request_weight(kind, result) / 15)
                if isinstance(result, dict) and "error" in result:
                    raise DataError("Hyperliquid returned an API error for " + kind)
                return result
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise DataError("HTTP %s for %s" % (error.code, kind)) from None
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                if attempt == 2:
                    raise DataError("Transport or JSON failure for " + kind) from None
            time.sleep(2 ** attempt)
        raise DataError("Request failed: " + kind)


def time_pages(client, kind, start_ms, end_ms, identity, **params):
    """Inclusive time paging. Refuse ambiguous full pages sharing one timestamp."""
    cursor, result, seen = start_ms, [], set()
    while cursor <= end_ms:
        page = client.post(kind, startTime=cursor, endTime=end_ms, **params)
        if not isinstance(page, list):
            raise DataError("Expected a list for " + kind)
        if not page:
            break
        for row in page:
            key = identity(row)
            if start_ms <= int(row["time"]) <= end_ms and key not in seen:
                result.append(row)
                seen.add(key)
        latest = max(int(row["time"]) for row in page)
        if latest < cursor:
            raise DataError("Non-advancing pagination")
        # The endpoint limit varies (fills: 2000; other time ranges: 500).
        limit = 2000 if kind == "userFillsByTime" else 500
        if len(page) < limit:
            break
        # Query the boundary again to avoid dropping rows at the same millisecond.
        if latest == cursor:
            raise DataError("Saturated timestamp: export history to establish completeness")
        cursor = latest
    return sorted(result, key=lambda row: int(row["time"]))
