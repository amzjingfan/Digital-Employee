from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def read(url: str) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": "joukir-migration-check"})
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def read_json(url: str) -> tuple[int, dict[str, object]]:
    status, _headers, body = read(url)
    return status, json.loads(body.decode("utf-8"))


def header_value(headers: dict[str, str], name: str) -> str:
    wanted = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == wanted), ""
    )


def main() -> int:
    web_status, web = read_json("http://127.0.0.1:5173/api/health")
    gallery_status, _gallery_headers, gallery_body = read(
        "http://127.0.0.1:5173/workspace/gallery"
    )
    gallery = gallery_body.decode("utf-8", errors="replace")
    config_status, config = read_json("http://127.0.0.1:5173/api/auth/oidc/config")
    casdoor_status, casdoor = read_json("http://127.0.0.1:18000/api/health")
    redirect_status, redirect_headers, _redirect_body = read(
        "http://127.0.0.1:5173/api/auth/oidc/login"
    )
    location = header_value(redirect_headers, "Location")
    parsed = urlsplit(location)
    query = parse_qs(parsed.query, keep_blank_values=True)
    redirect_uri = query.get("redirect_uri", [""])[0]

    result = {
        "webHealth": {
            "statusCode": web_status,
            "statusOk": web.get("status") == "ok",
            "appMatches": web.get("app") == "九骥 Joukir",
        },
        "gallery": {
            "statusCode": gallery_status,
            "hasRoot": 'id="root"' in gallery,
            "hasScriptAsset": "<script" in gallery and "/assets/" in gallery,
        },
        "oidcConfig": {
            "statusCode": config_status,
            "enabled": config.get("enabled") is True,
            "loginPathMatches": config.get("login_url") == "/api/auth/oidc/login",
        },
        "casdoorHealth": {
            "statusCode": casdoor_status,
            "statusOk": casdoor.get("status") == "ok",
        },
        "oidcRedirect": {
            "statusCode": redirect_status,
            "isRedirect": redirect_status in {302, 303, 307, 308},
            "usesHttp": parsed.scheme == "http",
            "hostIsLoopback": parsed.hostname in {"localhost", "127.0.0.1"},
            "portMatches": parsed.port == 18000,
            "pathMatches": parsed.path == "/login/oauth/authorize",
            "responseTypeCode": query.get("response_type") == ["code"],
            "redirectUriMatches": redirect_uri
            == "http://127.0.0.1:5173/api/auth/oidc/callback",
            "hasState": bool(query.get("state", [""])[0]),
            "hasNonce": bool(query.get("nonce", [""])[0]),
            "hasCodeChallenge": bool(query.get("code_challenge", [""])[0]),
            "challengeMethodS256": query.get("code_challenge_method") == ["S256"],
        },
    }
    result["ok"] = (
        web_status == 200
        and result["webHealth"]["statusOk"] is True
        and result["webHealth"]["appMatches"] is True
        and gallery_status == 200
        and result["gallery"]["hasRoot"] is True
        and result["gallery"]["hasScriptAsset"] is True
        and config_status == 200
        and result["oidcConfig"]["enabled"] is True
        and result["oidcConfig"]["loginPathMatches"] is True
        and casdoor_status == 200
        and result["casdoorHealth"]["statusOk"] is True
        and redirect_status in {302, 303, 307, 308}
        and all(
            value is True
            for key, value in result["oidcRedirect"].items()
            if key != "statusCode"
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
