"""Thin client for the Google Health API (health.googleapis.com/v4), which is what a
Pixel Watch / Fitbit account exposes. Credentials live in credentials.json:
{"client_id": ..., "client_secret": ..., "refresh_token": ...}"""
from __future__ import annotations

import json
from typing import Iterator
from urllib.parse import urlencode

import requests

from .config import CREDENTIALS_PATH, HEALTH_API_BASE, OAUTH_SCOPES

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class AuthError(Exception):
    pass


def load_credentials() -> dict:
    if not CREDENTIALS_PATH.exists():
        return {}
    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_credentials(creds: dict) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as fh:
        json.dump(creds, fh, indent=2)


def credential_status() -> dict:
    c = load_credentials()
    return {
        "has_client": bool(c.get("client_id") and c.get("client_secret")),
        "has_refresh_token": bool(c.get("refresh_token")),
    }


def set_client(client_id: str, client_secret: str) -> None:
    c = load_credentials()
    c["client_id"] = client_id.strip()
    c["client_secret"] = client_secret.strip()
    save_credentials(c)


def build_auth_url(redirect_uri: str) -> str:
    c = load_credentials()
    if not c.get("client_id"):
        raise AuthError("credentials.json has no client_id")
    q = {
        "client_id": c["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def exchange_code(code: str, redirect_uri: str) -> None:
    c = load_credentials()
    res = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": c.get("client_id"),
            "client_secret": c.get("client_secret"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if res.status_code != 200:
        raise AuthError(f"token exchange failed ({res.status_code}): {res.text[:300]}")
    tokens = res.json()
    if not tokens.get("refresh_token"):
        raise AuthError("Google did not return a refresh token; revoke the app's access in your Google account and try again")
    c["refresh_token"] = tokens["refresh_token"]
    save_credentials(c)


def set_refresh_token(token: str) -> None:
    c = load_credentials()
    c["refresh_token"] = token.strip()
    save_credentials(c)


class HealthClient:
    def __init__(self) -> None:
        c = load_credentials()
        if not (c.get("client_id") and c.get("client_secret") and c.get("refresh_token")):
            raise AuthError("Google is not connected. Open Settings and connect your account.")
        res = requests.post(
            TOKEN_URL,
            data={
                "client_id": c["client_id"],
                "client_secret": c["client_secret"],
                "refresh_token": c["refresh_token"],
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if res.status_code != 200:
            raise AuthError(f"Token refresh failed ({res.status_code}). Reconnect Google in Settings. {res.text[:200]}")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {res.json()['access_token']}"})

    def _get(self, url: str, params: dict | None = None) -> dict:
        res = self.session.get(url, params=params, timeout=60)
        if res.status_code != 200:
            raise RuntimeError(f"Google Health API error {res.status_code} for {url}: {res.text[:300]}")
        return res.json()

    def _paginate(self, url: str, params: dict) -> Iterator[dict]:
        token = None
        while True:
            p = {"pageToken": token} if token else dict(params)
            data = self._get(url, p)
            for dp in data.get("dataPoints", []):
                yield dp
            token = data.get("nextPageToken")
            if not token:
                return

    def exercises_since(self, start_iso: str) -> list[dict]:
        url = f"{HEALTH_API_BASE}/users/me/dataTypes/exercise/dataPoints"
        params = {"filter": f'exercise.interval.start_time >= "{start_iso}"'}
        try:
            return list(self._paginate(url, params))
        except RuntimeError:
            # Some API builds reject the filter expression; fall back to a full pull.
            return list(self._paginate(url, {}))

    def heart_rate_between(self, start_iso: str, end_iso: str) -> list[dict]:
        url = f"{HEALTH_API_BASE}/users/me/dataTypes/heart-rate/dataPoints"
        params = {
            "filter": (
                f'heart_rate.sample_time.physical_time >= "{start_iso}" AND '
                f'heart_rate.sample_time.physical_time < "{end_iso}"'
            ),
            "pageSize": 2000,
        }
        return list(self._paginate(url, params))

    def exercise_tcx(self, resource_name: str) -> str:
        data = self._get(f"{HEALTH_API_BASE}/{resource_name}:exportExerciseTcx")
        return data.get("tcxData", "")
