"""Small synchronous client; returns ordinary JSON-compatible dictionaries."""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

STEAM_BASE = 76561197960265728
MAX_ACCOUNT = 2**32 - 1


class InputError(ValueError):
    """Unsupported or invalid player identifier."""


class APIError(RuntimeError):
    """Remote service or transport error (URLs and API keys are omitted)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def resolve_numeric_id(value: str | int) -> int:
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise InputError("Expected Dota account ID or SteamID64")
    number = int(text)
    if STEAM_BASE < number <= STEAM_BASE + MAX_ACCOUNT:
        return number - STEAM_BASE
    if 0 < number <= MAX_ACCOUNT:
        return number
    raise InputError("Player ID is outside the supported range")


def _positive(value: int, name: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise InputError(f"{name} must be {'non-negative' if allow_zero else 'positive'} integer")
    return value


class DotaClient:
    """Use one instance per worker. API calls block; use a worker in GUI/async apps.

    API keys are optional, except steam_api_key for vanity Steam URLs.
    min_interval spaces requests; retries cover 429 and transient server errors.
    """

    def __init__(self, *, api_key: str | None = None,
                 steam_api_key: str | None = None, timeout: float = 30,
                 retries: int = 3, min_interval: float = 1.1):
        if not math.isfinite(timeout) or timeout <= 0:
            raise InputError("timeout must be positive and finite")
        if not math.isfinite(min_interval) or min_interval < 0:
            raise InputError("min_interval must be non-negative and finite")
        _positive(retries, "retries", allow_zero=True)
        self.api_key = api_key
        self.steam_api_key = steam_api_key
        self.timeout, self.retries, self.min_interval = timeout, retries, min_interval
        self._last_request = float("-inf")

    def _request(self, path: str, params: dict | None = None, *, steam: bool = False):
        query = dict(params or {})
        base = "https://api.steampowered.com" if steam else "https://api.opendota.com/api"
        if not steam and self.api_key:
            query["api_key"] = self.api_key
        url = base + path + ("?" + urlencode(query, doseq=True) if query else "")
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.min_interval - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            try:
                with urlopen(Request(url, headers={"User-Agent": "dota2parser/0.1", "Accept": "application/json"}), timeout=self.timeout) as response:
                    return json.load(response)
            except HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After")
                exc.close()
                if status not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise APIError(f"API returned HTTP {status}", status) from None
                delay = min(2**attempt, 30)
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            pass
                if not math.isfinite(delay) or delay > 60:
                    raise APIError("API requests a long wait; retry later", status) from None
                time.sleep(max(0, delay))
            except (URLError, TimeoutError, OSError):
                if attempt == self.retries:
                    raise APIError("Could not connect to API") from None
                time.sleep(min(2**attempt, 30))
            except (ValueError, UnicodeError):
                raise APIError("API returned invalid JSON") from None

    def resolve_player(self, player: str | int) -> int:
        text = str(player).strip()
        if re.fullmatch(r"[0-9]+", text):
            return resolve_numeric_id(text)
        url = urlsplit(text if "://" in text else "https://" + text)
        if url.scheme not in ("http", "https") or url.username or url.password:
            raise InputError("Unsupported player URL")
        host = (url.hostname or "").lower().removeprefix("www.")
        parts = url.path.strip("/").split("/")
        if len(parts) >= 2 and host in ("opendota.com", "dotabuff.com") and parts[0] == "players":
            return resolve_numeric_id(parts[1])
        if host == "steamcommunity.com" and len(parts) == 2:
            if parts[0] == "profiles":
                return resolve_numeric_id(parts[1])
            if parts[0] == "id" and re.fullmatch(r"[A-Za-z0-9_-]+", parts[1]):
                if not self.steam_api_key:
                    raise InputError("Steam /id/ URLs require steam_api_key; alternatively use a numeric ID")
                data = self._request("/ISteamUser/ResolveVanityURL/v1/", {"key": self.steam_api_key, "vanityurl": parts[1]}, steam=True)
                result = data.get("response", {}) if isinstance(data, dict) else {}
                if result.get("success") != 1:
                    raise InputError("Steam profile was not found")
                return resolve_numeric_id(result.get("steamid", ""))
        raise InputError("Use a player ID or Steam/OpenDota/Dotabuff player URL")

    def get_matches(self, player: str | int, *, limit: int = 100,
                    offset: int = 0, hero_id: int | None = None,
                    win: bool | None = None) -> list[dict]:
        """Return up to limit matches. Empty list means no available history.

        All provider fields are preserved; is_radiant and won are added.
        Pagination is bounded by limit and stops on an empty page.
        """
        _positive(limit, "limit")
        _positive(offset, "offset", allow_zero=True)
        if hero_id is not None:
            _positive(hero_id, "hero_id")
        if win is not None and not isinstance(win, bool):
            raise InputError("win must be bool or None")
        account_id = self.resolve_player(player)
        result = []
        seen = set()
        while len(result) < limit:
            params = {"limit": min(100, limit - len(result)), "offset": offset}
            if hero_id is not None:
                params["hero_id"] = hero_id
            if win is not None:
                params["win"] = int(win)
            page = self._request(f"/players/{account_id}/matches", params)
            if not isinstance(page, list) or any(not isinstance(row, dict) or not isinstance(row.get("match_id"), int) for row in page):
                raise APIError("Unexpected match history response")
            if not page:
                break
            added = 0
            for row in page:
                if row["match_id"] in seen:
                    continue
                seen.add(row["match_id"])
                item = dict(row)
                slot = item.get("player_slot")
                radiant = slot < 128 if isinstance(slot, int) else None
                item["is_radiant"] = radiant
                item["won"] = (radiant == item["radiant_win"] if radiant is not None and isinstance(item.get("radiant_win"), bool) else None)
                result.append(item)
                added += 1
                if len(result) == limit:
                    break
            offset += len(page)
            if not added:
                break
        return result

    def get_winrate(self, player: str | int, *, limit: int = 20) -> dict:
        """Summarize the latest available matches; unknown outcomes are excluded.

        winrate is a percentage (0..100), or None if no outcomes are known.
        Fewer than limit matches can be available from the provider.
        """
        matches = self.get_matches(player, limit=limit)
        wins = sum(match["won"] is True for match in matches)
        losses = sum(match["won"] is False for match in matches)
        counted = wins + losses
        return {
            "requested_matches": limit,
            "total_matches": len(matches),
            "counted_matches": counted,
            "wins": wins,
            "losses": losses,
            "unknown_matches": len(matches) - counted,
            "winrate": round(wins / counted * 100, 2) if counted else None,
        }

    def get_match(self, match: str | int) -> dict:
        """Return raw OpenDota match details by ID or match URL."""
        text = str(match).strip()
        if not re.fullmatch(r"[0-9]+", text):
            url = urlsplit(text if "://" in text else "https://" + text)
            parts = url.path.strip("/").split("/")
            if (url.scheme not in ("http", "https") or url.username or url.password
                    or (url.hostname or "").lower().removeprefix("www.") not in ("opendota.com", "dotabuff.com")
                    or len(parts) < 2 or parts[0] != "matches"):
                raise InputError("Expected match ID or OpenDota/Dotabuff match URL")
            text = parts[1]
        if not re.fullmatch(r"[0-9]+", text) or int(text) <= 0:
            raise InputError("Invalid match ID")
        data = self._request(f"/matches/{int(text)}")
        if not isinstance(data, dict) or data.get("match_id") != int(text):
            raise APIError("Unexpected match details response")
        return data
