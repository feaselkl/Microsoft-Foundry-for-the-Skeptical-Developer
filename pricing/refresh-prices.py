#!/usr/bin/env python3
"""Re-pull the nine Foundry meters the cost calculator uses.

Prices in index.html are a snapshot. Run this before a delivery and paste the
output over the PRICES block in index.html, so the numbers on screen are the
numbers Azure is charging that week.

Source is the public Azure Retail Prices API -- no auth, no subscription, and
authoritative. Which also makes it the honest answer to "where did you get
these numbers?" from the floor.

    python3 refresh-prices.py
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://prices.azure.com/api/retail/prices"


def get_json(url: str, attempts: int = 6) -> dict:
    """GET with backoff. The retail API rate-limits with HTTP 429, and a full
    pull is ~55 pages, so a hard failure on the first 429 is the common case
    rather than the exception. Honors Retry-After when the API sends one."""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == attempts:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or min(60, 5 * 2 ** (attempt - 1))
            print(f"// rate limited (429), waiting {wait}s, attempt {attempt}/{attempts}")
            time.sleep(wait)
    raise RuntimeError("unreachable")

# Exact meter names, Global Standard where a choice exists. Data Zone runs
# roughly 10% higher; regional varies.
WANTED = {
    "GPT 5 Mini Inpt Glbl 1M Tokens":        ("modelIn",     "per 1M input tokens"),
    "GPT 5 Mini cchd Inpt Glbl 1M Tokens":   ("modelCached", "per 1M cached input tokens"),
    "GPT 5 Mini outpt Glbl 1M Tokens":       ("modelOut",    "per 1M output tokens"),
    "text-embedding-3-small-glbl Tokens":    ("embed",       "per 1K tokens"),
    "Assistants-File Search-glbl GB":        ("fileSearch",  "per GB per day"),
    "Web Grounding Calls":                   ("webGrounding","per 1K calls"),
    "Code-Interpreter-global Session":       ("codeSession", "per session"),
    "Hosted vCPU Usage":                     ("vcpuHour",    "per vCPU-hour"),
    "Hosted Memory Usage":                   ("memHour",     "per GiB-hour"),
}


def fetch(service: str) -> list[dict]:
    url = BASE + "?" + urllib.parse.urlencode(
        {"$filter": f"serviceName eq '{service}'", "currencyCode": "USD"}
    )
    rows, pages = [], 0
    while url and pages < 60:
        payload = get_json(url)
        rows.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
        pages += 1
        time.sleep(0.25)  # be polite; the API throttles bursts
    return rows


# Chat models for the calculator's dropdown: (input, cached input, output) meters.
MODEL_METERS = {
    "gpt-6-luna":   ("6-luna ShortCo Inp Std Gl 1M Tokens",
                     "6-luna ShortCo Cd Inp Std Gl 1M Tokens",
                     "6-luna ShortCo Opt Std Gl 1M Tokens"),
    "gpt-5-mini":   ("GPT 5 Mini Inpt Glbl 1M Tokens",
                     "GPT 5 Mini cchd Inpt Glbl 1M Tokens",
                     "GPT 5 Mini outpt Glbl 1M Tokens"),
    "gpt-5.4-mini": ("5.4 mini Inp Gl 1M Tokens",
                     "5.4 mini cd Inp Gl 1M Tokens",
                     "5.4 mini Opt Gl 1M Tokens"),
    "gpt-6.1-sol":  ("6.1-sol ShortCo Inp Std Gl 1M Tokens",
                     "6.1-sol ShortCo Cd Inp Std Gl 1M Tokens",
                     "6.1-sol ShortCo Opt Std Gl 1M Tokens"),
}


def main() -> None:
    rows = fetch("Foundry Models") + fetch("Foundry Tools")
    print(f"// scanned {len(rows)} meter rows\n")

    price = {}
    for row in rows:
        price.setdefault(row.get("meterName"), (row.get("retailPrice"), row.get("serviceName")))

    missing = []

    print("// ---- PRICES block ----")
    for name, (key, unit) in WANTED.items():
        if name not in price:
            missing.append(name)
            continue
        value, service = price[name]
        print(f'  {key + ":":<14}{value:<10}// {unit}  [{service}: {name}]')

    print("\n// ---- MODELS block (input / cached / output per 1M) ----")
    for model, meters in MODEL_METERS.items():
        vals = []
        for m in meters:
            if m in price:
                vals.append(price[m][0])
            else:
                vals.append(None)
                missing.append(m)
        if None in vals:
            print(f'  // "{model}": incomplete, see NOT FOUND below')
        else:
            i, c, o = vals
            print(f'  "{model}": {{ in: {i}, cached: {c}, out: {o} }},')

    if missing:
        print("\n// NOT FOUND -- meter renamed or retired, check the portal:")
        for name in missing:
            print(f"//   {name}")


if __name__ == "__main__":
    main()
