"""Small cached client for the official stats.nba.com JSON endpoints."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = "https://stats.nba.com/stats"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


class NBAClient:
    def __init__(
        self,
        cache_dir: Path,
        offline: bool = False,
        refresh: bool = False,
        timeout: int = 30,
        delay_seconds: float = 0.6,
        retries: int = 2,
    ) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.refresh = refresh
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self.retries = retries

    def get(self, endpoint: str, params: dict[str, object], cache_key: str) -> dict[str, Any]:
        path = self.cache_dir / f"{cache_key}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        if self.offline:
            raise FileNotFoundError(f"No cached response for {cache_key}: {path}")
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{BASE_URL}/{endpoint}?{query}", headers=HEADERS
        )
        last_error: Exception | None = None
        payload = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
        if payload is None:
            raise RuntimeError(
                f"NBA endpoint {endpoint} failed for {cache_key} after "
                f"{self.retries + 1} attempts: {last_error}"
            ) from last_error
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        time.sleep(self.delay_seconds)
        return payload


def result_rows(payload: dict[str, Any], expected_name: str | None = None) -> list[dict[str, Any]]:
    """Convert either NBA resultSets response shape into dictionaries."""
    result_sets = payload.get("resultSets", payload.get("resultSet"))
    if isinstance(result_sets, dict):
        result_sets = [result_sets]
    if not isinstance(result_sets, list):
        raise ValueError("NBA response has no result set")
    selected = None
    if expected_name:
        selected = next(
            (item for item in result_sets if item.get("name") == expected_name), None
        )
    if selected is None and result_sets:
        selected = result_sets[0]
    if not selected:
        return []
    headers = selected.get("headers", [])
    return [dict(zip(headers, row)) for row in selected.get("rowSet", [])]


def combine_season(year: int) -> str:
    """Return the season label used by the live Combine pages, e.g. 2019-20."""
    return f"{year}-{str(year + 1)[-2:]}"


def fetch_combine_year(client: NBAClient, year: int) -> tuple[list[dict], list[dict], list[dict]]:
    common = {"LeagueID": "00", "SeasonYear": combine_season(year)}
    anthro = result_rows(
        client.get("draftcombineplayeranthro", common, f"{year}_anthro"), "Results"
    )
    drills = result_rows(
        client.get("draftcombinedrillresults", common, f"{year}_drills"), "Results"
    )
    draft_params = {
        "College": "", "LeagueID": "00", "OverallPick": "", "RoundNum": "",
        "RoundPick": "", "Season": year, "TeamID": "0", "TopX": "",
    }
    draft = result_rows(
        client.get("drafthistory", draft_params, f"{year}_draft"), "DraftHistory"
    )
    return anthro, drills, draft


def fetch_player_profile(client: NBAClient, player_id: int) -> dict[str, Any] | None:
    payload = client.get(
        "commonplayerinfo",
        {"LeagueID": "", "PlayerID": player_id},
        f"profiles/{player_id}",
    )
    # The official endpoint returns an empty JSON object for some Combine-only
    # players who never received a populated NBA profile. This is a legitimate
    # unresolved birth year, not a malformed Combine or draft response.
    if not payload.get("resultSets") and not payload.get("resultSet"):
        return None
    rows = result_rows(payload, "CommonPlayerInfo")
    return rows[0] if rows else None
