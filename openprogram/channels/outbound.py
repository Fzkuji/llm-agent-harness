"""Stateless "send-to-channel" API.

Problem this solves: the channels worker process polls inbound; the
Web UI / CLI chat reply path needs to be able to send OUTBOUND
without going through that worker. We can't do simple IPC because
the worker may be running under a different profile, be restarting,
etc. So instead every outbound path is a pure HTTP call — the caller
just needs the bot token / credentials, which all live on disk and
any process can read.

Public entry point:

    send_to_channel(platform, user_id, text) -> bool

Each platform's sender reads its own credentials from
``~/.agentic/config.json`` (bot tokens stored under ``api_keys``) or
``~/.agentic/wechat/<bot>.json`` (WeChat QR login credentials).

Returns True on a successful send, False + logs on failure; callers
typically just care that a reply went out and don't need to block on
the transport.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Optional


_MAX_MSG_CHARS = 1800


# --------------------------------------------------------------------------
# Public dispatch
# --------------------------------------------------------------------------

def send_to_channel(platform: str, user_id: str, text: str) -> bool:
    """Deliver ``text`` to (platform, user_id).

    Chunks at ~1800 chars so every platform's per-message limits are
    respected, and sends chunks sequentially. Returns True iff every
    chunk landed. Errors print a single line but don't raise, since
    the caller usually can't do anything useful with the exception.
    """
    if not text:
        return True
    sender = _SENDERS.get(platform)
    if sender is None:
        print(f"[outbound] unknown platform {platform!r}")
        return False
    ok = True
    for chunk in _chunk(text, _MAX_MSG_CHARS):
        if not sender(user_id, chunk):
            ok = False
    return ok


def _chunk(text: str, limit: int) -> list[str]:
    if not text:
        return [""]
    return [text[i:i + limit] for i in range(0, len(text), limit)]


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

def _send_telegram(chat_id: str, text: str) -> bool:
    token = _bot_token("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[outbound.telegram] no TELEGRAM_BOT_TOKEN in config / env")
        return False
    import requests
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(chat_id) if chat_id.lstrip("-").isdigit()
                  else chat_id, "text": text},
            timeout=10,
        )
        if not r.ok:
            print(f"[outbound.telegram] HTTP {r.status_code}: "
                  f"{r.text[:200]}")
            return False
        data = r.json()
        if not data.get("ok"):
            print(f"[outbound.telegram] {data.get('description','?')[:200]}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[outbound.telegram] {type(e).__name__}: {e}")
        return False


# --------------------------------------------------------------------------
# Discord — raw HTTP so we don't need an asyncio client just to send.
# Inbound user ids are stored as "<channel_id>_<user_id>" so we split
# here; the channel_id is the only piece the Create Message API needs.
# --------------------------------------------------------------------------

def _send_discord(scoped_user_id: str, text: str) -> bool:
    token = _bot_token("DISCORD_BOT_TOKEN")
    if not token:
        print("[outbound.discord] no DISCORD_BOT_TOKEN in config / env")
        return False
    channel_id, _, _user = scoped_user_id.partition("_")
    if not channel_id:
        print(f"[outbound.discord] malformed user id {scoped_user_id!r}")
        return False
    import requests
    try:
        r = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
                "User-Agent": "OpenProgram (https://github.com/Fzkuji/OpenProgram, 0.1)",
            },
            json={"content": text},
            timeout=10,
        )
        if not r.ok:
            print(f"[outbound.discord] HTTP {r.status_code}: "
                  f"{r.text[:200]}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[outbound.discord] {type(e).__name__}: {e}")
        return False


# --------------------------------------------------------------------------
# Slack — same "<channel_id>_<user_id>" scheme as Discord.
# --------------------------------------------------------------------------

def _send_slack(scoped_user_id: str, text: str) -> bool:
    token = _bot_token("SLACK_BOT_TOKEN")
    if not token:
        print("[outbound.slack] no SLACK_BOT_TOKEN in config / env")
        return False
    channel_id, _, _user = scoped_user_id.partition("_")
    if not channel_id:
        print(f"[outbound.slack] malformed user id {scoped_user_id!r}")
        return False
    import requests
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"channel": channel_id, "text": text},
            timeout=10,
        )
        data = r.json() if r.ok else {}
        if not data.get("ok"):
            err = data.get("error") or r.text[:200]
            print(f"[outbound.slack] {err}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[outbound.slack] {type(e).__name__}: {e}")
        return False


# --------------------------------------------------------------------------
# WeChat — Tencent iLink bot sendmessage endpoint.
# --------------------------------------------------------------------------

def _send_wechat(user_id: str, text: str) -> bool:
    creds = _load_wechat_creds()
    if creds is None:
        print("[outbound.wechat] no saved credentials — scan a QR first")
        return False
    import requests
    bot_token = creds.get("bot_token") or ""
    bot_id = creds.get("ilink_bot_id") or ""
    base = creds.get("baseurl") or "https://ilinkai.weixin.qq.com"
    if not bot_token or not bot_id:
        print("[outbound.wechat] credentials incomplete")
        return False
    # Stable-ish X-WECHAT-UIN per process (iLink ties sessions to it;
    # doesn't matter that it's different between worker and webui).
    from openprogram.channels.wechat import _make_wechat_uin
    try:
        r = requests.post(
            f"{base}/ilink/bot/sendmessage",
            headers={
                "Content-Type": "application/json",
                "AuthorizationType": "ilink_bot_token",
                "Authorization": f"Bearer {bot_token}",
                "X-WECHAT-UIN": _make_wechat_uin(),
            },
            json={
                "msg": {
                    "from_user_id": bot_id,
                    "to_user_id": user_id,
                    "client_id": uuid.uuid4().hex,
                    "message_type": 2,    # Bot
                    "message_state": 2,   # Finish
                    "item_list": [{"type": 1, "text_item": {"text": text}}],
                    "context_token": "",
                },
                "base_info": {},
            },
            timeout=15,
        )
        data = r.json() if r.ok else {}
        if data.get("ret", 0) != 0:
            print(f"[outbound.wechat] {data.get('errmsg','?')[:200]}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[outbound.wechat] {type(e).__name__}: {e}")
        return False


_SENDERS = {
    "telegram": _send_telegram,
    "discord":  _send_discord,
    "slack":    _send_slack,
    "wechat":   _send_wechat,
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _bot_token(env_name: str) -> Optional[str]:
    """Read a bot token from config.api_keys then the environment."""
    try:
        from openprogram.setup_wizard import _read_config
        cfg = _read_config()
        fromcfg = (cfg.get("api_keys") or {}).get(env_name)
        if fromcfg:
            return fromcfg
    except Exception:
        pass
    return os.environ.get(env_name) or None


def _load_wechat_creds() -> Optional[dict]:
    """Reuse the worker's credential-finding logic so both paths read
    the same JSON file."""
    try:
        from openprogram.channels.wechat import _find_saved_creds
        return _find_saved_creds()
    except Exception:
        return None
