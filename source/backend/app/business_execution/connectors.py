from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.business_execution.contracts import (
    BusinessConnector,
    ConnectorOutcome,
    ExecutionContext,
)
from app.config import Settings, get_settings

_AUTH_PROFILE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_SENSITIVE_PARTS = ("authorization", "password", "secret", "token", "api_key", "private_key")


def connector_type_for(action_type: str, resource_type: str) -> str:
    if action_type in {
        "change_daily_budget",
        "change_ad_bid",
        "update_negative_keywords",
        "change_campaign_status",
    }:
        return "amazon_ads"
    if action_type == "change_routing_rule":
        return "logistics_http"
    if action_type == "issue_purchase_order":
        return "procurement_http"
    if action_type == "publish_creative_asset" and resource_type == "ad_account":
        return "amazon_ads"
    return "amazon_sp_api"


def build_connector(
    connector_type: str,
    *,
    settings: Settings | None = None,
    client_factory=None,
) -> BusinessConnector:
    resolved = settings or get_settings()
    if connector_type == "sandbox":
        return SandboxConnector()
    if connector_type == "amazon_sp_api":
        return AmazonSpApiConnector(settings=resolved, client_factory=client_factory)
    if connector_type == "amazon_ads":
        return AmazonAdsConnector(settings=resolved, client_factory=client_factory)
    if connector_type in {"logistics_http", "procurement_http"}:
        return GenericBusinessHttpConnector(
            connector_type=connector_type,
            settings=resolved,
            client_factory=client_factory,
        )
    raise ValueError(f"Unsupported business connector: {connector_type}")


class SandboxConnector(BusinessConnector):
    connector_type = "sandbox"
    replay_safe = True

    def execute(self, context: ExecutionContext) -> ConnectorOutcome:
        simulation = str(context.payload.get("simulate_outcome") or "").strip()
        if simulation == "retryable_once" and context.attempt_no == 1:
            return ConnectorOutcome(
                disposition="retryable_failure",
                error_code="sandbox_transient",
                error_message="Simulated transient dependency failure",
                retry_after_seconds=0,
            )
        if simulation == "terminal_failure":
            return ConnectorOutcome(
                disposition="terminal_failure",
                error_code="sandbox_terminal",
                error_message="Simulated terminal dependency failure",
            )
        if simulation == "unknown":
            return ConnectorOutcome(
                disposition="unknown",
                error_code="sandbox_remote_state_unknown",
                error_message="Simulated ambiguous remote outcome",
            )
        operation_id = f"sandbox-{context.execution_id}"
        return ConnectorOutcome(
            disposition="succeeded",
            external_operation_id=operation_id,
            receipt={
                "provider": "staffdeck-sandbox",
                "accepted": True,
                "action_type": context.action_type,
                "resource_code": context.resource_code,
                "operation_id": operation_id,
                "idempotency_key": context.idempotency_key,
            },
        )

    def compensate(self, context: ExecutionContext, receipt: dict[str, Any]) -> ConnectorOutcome:
        if context.action_type == "issue_refund":
            return ConnectorOutcome(
                disposition="terminal_failure",
                error_code="irreversible_refund",
                error_message="A completed refund cannot be reversed automatically",
            )
        operation_id = f"sandbox-compensation-{context.execution_id}"
        return ConnectorOutcome(
            disposition="succeeded",
            external_operation_id=operation_id,
            receipt={
                "provider": "staffdeck-sandbox",
                "compensated": True,
                "original_operation_id": receipt.get("operation_id"),
                "operation_id": operation_id,
            },
        )


class _LwaConnector(BusinessConnector):
    token_env_segment = ""

    def __init__(self, *, settings: Settings, client_factory=None):
        self.settings = settings
        self._client_factory = client_factory or (
            lambda: httpx.Client(
                timeout=httpx.Timeout(settings.business_execution_attempt_timeout_seconds),
                follow_redirects=False,
            )
        )

    def _access_token(self, metadata: dict[str, Any]) -> tuple[str | None, ConnectorOutcome | None]:
        profile = str(metadata.get("auth_profile") or "").strip().upper()
        if not _AUTH_PROFILE_RE.fullmatch(profile):
            return None, _terminal(
                "invalid_auth_profile", "Resource auth_profile is missing or invalid"
            )
        prefix = f"{profile}_{self.token_env_segment}"
        client_id = os.getenv(f"{prefix}_CLIENT_ID", "")
        client_secret = os.getenv(f"{prefix}_CLIENT_SECRET", "")
        refresh_token = os.getenv(f"{prefix}_REFRESH_TOKEN", "")
        if not all((client_id, client_secret, refresh_token)):
            return None, _terminal(
                "credentials_unavailable",
                f"Credential environment variables for auth profile {profile} are incomplete",
            )
        try:
            with self._client_factory() as client:
                response = client.post(
                    "https://api.amazon.com/auth/o2/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            return None, _transport_failure(exc, replay_safe=True)
        if response.status_code >= 500 or response.status_code == 429:
            return None, _retryable_response(response, "lwa_token_unavailable")
        if response.status_code >= 400:
            return None, _terminal(
                "lwa_authorization_failed", f"LWA returned HTTP {response.status_code}"
            )
        token = str(_safe_json(response).get("access_token") or "")
        if not token:
            return None, _terminal(
                "lwa_token_missing", "LWA response did not include an access token"
            )
        return token, None


class AmazonSpApiConnector(_LwaConnector):
    connector_type = "amazon_sp_api"
    token_env_segment = "SP_API"
    replay_safe = True

    def execute(self, context: ExecutionContext) -> ConnectorOutcome:
        if context.action_type == "issue_refund":
            return _terminal(
                "sp_api_refund_workflow_required",
                "Amazon marketplace refunds require a dedicated feed/order-adjustment workflow; "
                "a direct refund mutation is intentionally not guessed",
            )
        if context.action_type == "publish_listing":
            return self._put_listing(context)
        path = str(context.resource_metadata.get("creative_publish_path") or "").strip()
        if context.action_type == "publish_creative_asset" and path:
            return self._request(context, "POST", path, context.payload, replay_safe=True)
        return _terminal(
            "sp_api_operation_not_configured",
            f"No verified SP-API operation is configured for {context.action_type}",
        )

    def compensate(self, context: ExecutionContext, receipt: dict[str, Any]) -> ConnectorOutcome:
        if context.action_type != "publish_listing":
            return super().compensate(context, receipt)
        seller_id = str(context.resource_metadata.get("seller_id") or "").strip()
        marketplace_id = str(context.resource_metadata.get("marketplace_id") or "").strip()
        sku = str(context.payload.get("listing_id") or "").strip()
        if not all((seller_id, marketplace_id, sku)):
            return _terminal(
                "listing_identity_missing", "seller_id, marketplace_id and listing_id are required"
            )
        path = f"/listings/2021-08-01/items/{quote(seller_id, safe='')}/{quote(sku, safe='')}"
        return self._request(
            context,
            "DELETE",
            path,
            None,
            params={"marketplaceIds": marketplace_id},
            replay_safe=True,
        )

    def _put_listing(self, context: ExecutionContext) -> ConnectorOutcome:
        metadata = context.resource_metadata
        seller_id = str(metadata.get("seller_id") or "").strip()
        marketplace_id = str(metadata.get("marketplace_id") or "").strip()
        sku = str(context.payload.get("listing_id") or "").strip()
        product_type = str(context.payload.get("product_type") or "").strip()
        attributes = context.payload.get("attributes")
        if not all((seller_id, marketplace_id, sku, product_type)) or not isinstance(
            attributes, dict
        ):
            return _terminal(
                "listing_payload_incomplete",
                "seller_id, marketplace_id, listing_id, product_type and attributes are required",
            )
        path = f"/listings/2021-08-01/items/{quote(seller_id, safe='')}/{quote(sku, safe='')}"
        body = {
            "productType": product_type,
            "requirements": str(context.payload.get("requirements") or "LISTING"),
            "attributes": attributes,
        }
        return self._request(
            context,
            "PUT",
            path,
            body,
            params={"marketplaceIds": marketplace_id},
            replay_safe=True,
        )

    def _request(
        self,
        context: ExecutionContext,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        *,
        params: dict[str, str] | None = None,
        replay_safe: bool,
    ) -> ConnectorOutcome:
        token, error = self._access_token(context.resource_metadata)
        if error:
            return error
        base_url = _sp_api_base_url(context.resource_metadata)
        url_error = _validate_live_url(base_url + path, self.settings)
        if url_error:
            return url_error
        headers = {
            "x-amz-access-token": str(token),
            "x-amz-date": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
            "user-agent": "StaffDeck/0.1.0 (Language=Python/3)",
            "content-type": "application/json",
            "x-staffdeck-idempotency-key": context.idempotency_key,
        }
        return _send_json(
            self._client_factory,
            method,
            base_url + path,
            headers=headers,
            params=params,
            body=body,
            replay_safe=replay_safe,
        )


class AmazonAdsConnector(_LwaConnector):
    connector_type = "amazon_ads"
    token_env_segment = "ADS"
    replay_safe = True

    def execute(self, context: ExecutionContext) -> ConnectorOutcome:
        if context.action_type == "change_ad_bid":
            return self._change_bid(context)
        if context.action_type == "update_negative_keywords":
            return self._update_negative_keywords(context)
        if context.action_type == "change_campaign_status":
            return self._change_campaign_status(context)
        if context.action_type != "change_daily_budget":
            path = str(context.resource_metadata.get("creative_publish_path") or "").strip()
            if not path:
                return _terminal(
                    "ads_operation_not_configured",
                    f"No verified Amazon Ads operation is configured for {context.action_type}",
                )
            return self._request(context, path, context.payload)
        campaign_id = str(context.payload.get("campaign_id") or "").strip()
        if not campaign_id:
            return _terminal("campaign_id_missing", "campaign_id is required")
        body = [
            {
                "campaignId": campaign_id,
                "dailyBudget": context.payload.get("daily_budget"),
            }
        ]
        path = str(context.resource_metadata.get("campaign_update_path") or "").strip()
        if not path:
            return _terminal(
                "ads_campaign_path_missing",
                "campaign_update_path must be verified for this Amazon Ads account",
            )
        return self._request(context, path, body)

    def _change_bid(self, context: ExecutionContext) -> ConnectorOutcome:
        campaign_id = str(context.payload.get("campaign_id") or "").strip()
        target_id = str(context.payload.get("target_id") or "").strip()
        path = str(context.resource_metadata.get("bid_update_path") or "").strip()
        if not campaign_id or not target_id or not path:
            return _terminal(
                "ads_bid_path_missing",
                "campaign_id, target_id and verified bid_update_path are required",
            )
        return self._request(
            context,
            path,
            [{"campaignId": campaign_id, "targetId": target_id, "bid": context.payload.get("bid")}],
        )

    def _update_negative_keywords(self, context: ExecutionContext) -> ConnectorOutcome:
        campaign_id = str(context.payload.get("campaign_id") or "").strip()
        path = str(context.resource_metadata.get("negative_keyword_update_path") or "").strip()
        keywords = context.payload.get("keywords")
        if not campaign_id or not path or not isinstance(keywords, list):
            return _terminal(
                "ads_negative_keyword_path_missing",
                "campaign_id, keywords and verified negative_keyword_update_path are required",
            )
        body = [
            {
                "campaignId": campaign_id,
                "keywordText": str(keyword),
                "matchType": context.payload.get("match_type"),
            }
            for keyword in keywords
        ]
        return self._request(context, path, body)

    def _change_campaign_status(self, context: ExecutionContext) -> ConnectorOutcome:
        campaign_id = str(context.payload.get("campaign_id") or "").strip()
        path = str(context.resource_metadata.get("campaign_update_path") or "").strip()
        if not campaign_id or not path:
            return _terminal(
                "ads_campaign_path_missing",
                "campaign_id and verified campaign_update_path are required",
            )
        return self._request(
            context,
            path,
            [{"campaignId": campaign_id, "state": context.payload.get("status")}],
        )

    def compensate(self, context: ExecutionContext, receipt: dict[str, Any]) -> ConnectorOutcome:
        campaign_id = str(context.payload.get("campaign_id") or "").strip()
        if context.action_type == "change_ad_bid":
            previous_bid = context.payload.get("previous_bid")
            target_id = str(context.payload.get("target_id") or "").strip()
            path = str(context.resource_metadata.get("bid_update_path") or "").strip()
            if previous_bid is None or not campaign_id or not target_id or not path:
                return _terminal(
                    "previous_bid_missing",
                    "previous_bid, campaign_id, target_id and bid_update_path are required",
                )
            return self._request(
                context,
                path,
                [{"campaignId": campaign_id, "targetId": target_id, "bid": previous_bid}],
            )
        if context.action_type == "change_campaign_status":
            previous_status = str(context.payload.get("previous_status") or "").strip()
            path = str(context.resource_metadata.get("campaign_update_path") or "").strip()
            if not previous_status or not campaign_id or not path:
                return _terminal(
                    "previous_campaign_status_missing",
                    "previous_status, campaign_id and campaign_update_path are required",
                )
            return self._request(
                context,
                path,
                [{"campaignId": campaign_id, "state": previous_status}],
            )
        if context.action_type == "update_negative_keywords":
            keyword_ids = context.payload.get("rollback_keyword_ids") or receipt.get("keyword_ids")
            path = str(
                context.resource_metadata.get("negative_keyword_rollback_path") or ""
            ).strip()
            if not path or not isinstance(keyword_ids, list) or not keyword_ids:
                return _terminal(
                    "negative_keyword_rollback_unavailable",
                    "Verified rollback path and created keyword IDs are required; resolve manually",
                )
            return self._request(
                context,
                path,
                [{"keywordId": str(keyword_id), "state": "ARCHIVED"} for keyword_id in keyword_ids],
            )
        if context.action_type != "change_daily_budget":
            return _terminal(
                "ads_compensation_not_supported",
                f"No verified compensation is configured for {context.action_type}",
            )
        previous = context.payload.get("previous_daily_budget")
        if previous is None or not campaign_id:
            return _terminal(
                "previous_budget_missing",
                "previous_daily_budget and campaign_id are required for compensation",
            )
        path = str(context.resource_metadata.get("campaign_update_path") or "").strip()
        if not path:
            return _terminal(
                "ads_campaign_path_missing",
                "campaign_update_path must be verified for this Amazon Ads account",
            )
        return self._request(
            context,
            path,
            [{"campaignId": campaign_id, "dailyBudget": previous}],
        )

    def _request(self, context: ExecutionContext, path: str, body: Any) -> ConnectorOutcome:
        token, error = self._access_token(context.resource_metadata)
        if error:
            return error
        metadata = context.resource_metadata
        profile_id = str(metadata.get("profile_id") or "").strip()
        auth_profile = str(metadata.get("auth_profile") or "").strip().upper()
        client_id = os.getenv(f"{auth_profile}_ADS_CLIENT_ID", "")
        if not profile_id or not client_id:
            return _terminal("ads_profile_missing", "profile_id or Ads client id is unavailable")
        base_url = str(metadata.get("ads_base_url") or "https://advertising-api.amazon.com").rstrip(
            "/"
        )
        url_error = _validate_live_url(base_url + path, self.settings)
        if url_error:
            return url_error
        headers = {
            "Authorization": f"Bearer {token}",
            "Amazon-Advertising-API-ClientId": client_id,
            "Amazon-Advertising-API-Scope": profile_id,
            "Content-Type": "application/json",
            "Idempotency-Key": context.idempotency_key,
        }
        return _send_json(
            self._client_factory,
            "PUT",
            base_url + path,
            headers=headers,
            body=body,
            replay_safe=True,
        )


class GenericBusinessHttpConnector(BusinessConnector):
    def __init__(self, *, connector_type: str, settings: Settings, client_factory=None):
        self.connector_type = connector_type
        self.settings = settings
        self._client_factory = client_factory or (
            lambda: httpx.Client(
                timeout=httpx.Timeout(settings.business_execution_attempt_timeout_seconds),
                follow_redirects=False,
            )
        )

    def execute(self, context: ExecutionContext) -> ConnectorOutcome:
        return self._invoke(context, "execute_url", context.payload, phase="execute")

    def compensate(self, context: ExecutionContext, receipt: dict[str, Any]) -> ConnectorOutcome:
        body = {"original_payload": context.payload, "original_receipt": receipt}
        return self._invoke(context, "compensate_url", body, phase="compensate")

    def _invoke(
        self,
        context: ExecutionContext,
        url_key: str,
        operation_payload: dict[str, Any],
        *,
        phase: str,
    ) -> ConnectorOutcome:
        metadata = context.resource_metadata
        url = str(metadata.get(url_key) or "").strip()
        if not url:
            return _terminal("connector_url_missing", f"Resource metadata.{url_key} is required")
        url_error = _validate_live_url(url, self.settings)
        if url_error:
            return url_error
        replay_safe = metadata.get("supports_idempotency") is True
        profile = str(metadata.get("auth_profile") or "").strip().upper()
        if not _AUTH_PROFILE_RE.fullmatch(profile):
            return _terminal("invalid_auth_profile", "Resource auth_profile is missing or invalid")
        body = {
            "schema_version": 1,
            "phase": phase,
            "execution_id": context.execution_id,
            "request_id": context.request_id,
            "tenant_id": context.tenant_id,
            "resource": {
                "id": context.resource_id,
                "type": context.resource_type,
                "code": context.resource_code,
            },
            "action_type": context.action_type,
            "payload": operation_payload,
        }
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": context.idempotency_key
            + (":compensate" if phase == "compensate" else ""),
        }
        bearer = os.getenv(f"{profile}_BEARER_TOKEN", "")
        signing_secret = os.getenv(f"{profile}_HMAC_SECRET", "")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if signing_secret:
            headers["X-StaffDeck-Signature"] = (
                "sha256="
                + hmac.new(signing_secret.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
            )
        if not bearer and not signing_secret:
            return _terminal(
                "connector_auth_unavailable",
                f"No bearer token or HMAC secret is configured for auth profile {profile}",
            )
        return _send_json(
            self._client_factory,
            "POST",
            url,
            headers=headers,
            body=body,
            replay_safe=replay_safe,
        )


def _send_json(
    client_factory,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: Any = None,
    params: dict[str, str] | None = None,
    replay_safe: bool,
) -> ConnectorOutcome:
    try:
        with client_factory() as client:
            response = client.request(method, url, headers=headers, params=params, json=body)
    except httpx.HTTPError as exc:
        return _transport_failure(exc, replay_safe=replay_safe)
    if 200 <= response.status_code < 300:
        data = _redact(_safe_json(response))
        operation_id = _operation_id(response, data)
        return ConnectorOutcome(
            disposition="succeeded",
            external_operation_id=operation_id,
            receipt={
                "http_status": response.status_code,
                "operation_id": operation_id,
                "response": data,
            },
        )
    if response.status_code in {408, 425, 429} or response.status_code >= 500:
        if replay_safe:
            return _retryable_response(response, "dependency_transient_error")
        return ConnectorOutcome(
            disposition="unknown",
            error_code="remote_state_unknown",
            error_message=(
                f"Remote mutation returned HTTP {response.status_code} "
                "without an idempotency guarantee"
            ),
        )
    return ConnectorOutcome(
        disposition="terminal_failure",
        error_code=f"dependency_http_{response.status_code}",
        error_message=_response_error_message(response),
        receipt={"http_status": response.status_code, "response": _redact(_safe_json(response))},
    )


def _transport_failure(exc: httpx.HTTPError, *, replay_safe: bool) -> ConnectorOutcome:
    if replay_safe:
        return ConnectorOutcome(
            disposition="retryable_failure",
            error_code="dependency_transport_error",
            error_message=type(exc).__name__,
        )
    return ConnectorOutcome(
        disposition="unknown",
        error_code="remote_state_unknown",
        error_message=f"Remote mutation outcome is unknown after {type(exc).__name__}",
    )


def _retryable_response(response: httpx.Response, code: str) -> ConnectorOutcome:
    retry_after = response.headers.get("retry-after")
    try:
        retry_seconds = float(retry_after) if retry_after else None
    except ValueError:
        retry_seconds = None
    return ConnectorOutcome(
        disposition="retryable_failure",
        error_code=code,
        error_message=f"Dependency returned HTTP {response.status_code}",
        retry_after_seconds=retry_seconds,
        receipt={"http_status": response.status_code},
    )


def _terminal(code: str, message: str) -> ConnectorOutcome:
    return ConnectorOutcome(
        disposition="terminal_failure",
        error_code=code,
        error_message=message,
    )


def _sp_api_base_url(metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("sp_api_base_url") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    region = str(metadata.get("region") or "na").strip().lower()
    return {
        "na": "https://sellingpartnerapi-na.amazon.com",
        "eu": "https://sellingpartnerapi-eu.amazon.com",
        "fe": "https://sellingpartnerapi-fe.amazon.com",
    }.get(region, "https://sellingpartnerapi-na.amazon.com")


def _validate_live_url(url: str, settings: Settings) -> ConnectorOutcome | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return _terminal(
            "unsafe_connector_url", "Live connector URLs must use HTTPS without user info"
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local):
        return _terminal(
            "unsafe_connector_url", "Private and loopback connector addresses are denied"
        )
    if host not in settings.business_execution_allowed_host_set:
        return _terminal("connector_host_not_allowed", f"Connector host {host} is not allow-listed")
    return None


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except (ValueError, json.JSONDecodeError):
        text = response.text[:2000]
        return {"text": text}
    if isinstance(value, dict):
        return value
    return {"data": value}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            output[str(key)] = (
                "[REDACTED]"
                if any(part in normalized for part in _SENSITIVE_PARTS)
                else _redact(item)
            )
        return output
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:4000]
    return value


def _operation_id(response: httpx.Response, data: dict[str, Any]) -> str | None:
    for key in ("operationId", "operation_id", "requestId", "request_id", "id"):
        value = data.get(key)
        if value:
            return str(value)[:255]
    for key in ("x-amzn-requestid", "x-amz-request-id", "x-request-id"):
        value = response.headers.get(key)
        if value:
            return value[:255]
    return None


def _response_error_message(response: httpx.Response) -> str:
    data = _safe_json(response)
    for key in ("message", "error_description", "error"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value[:1000]
    return f"Dependency returned HTTP {response.status_code}"
