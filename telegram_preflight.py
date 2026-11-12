"""Read-only Telegram bot and destination preflight checks.

This verifies credentials, bot identity, destination visibility, and channel/group
posting permissions without sending a message.
"""
import argparse
import json
import os
import urllib.parse
import urllib.request


def telegram_call(token, method, params=None):
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")
    query = urllib.parse.urlencode(params or {})
    url = f"https://api.telegram.org/bot{token}/{method}"
    if query:
        url += "?" + query
    request = urllib.request.Request(url, headers={"User-Agent": "PitchIQ-Telegram-Preflight/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        description = payload.get("description", "unknown Telegram API error") if isinstance(payload, dict) else "invalid Telegram API response"
        raise RuntimeError(f"Telegram {method} failed: {description}")
    return payload.get("result")


def verify_destination(token, chat_id):
    if not isinstance(chat_id, (str, int)) or not str(chat_id).strip():
        raise RuntimeError("Telegram destination is missing.")
    bot = telegram_call(token, "getMe")
    if not isinstance(bot, dict) or not isinstance(bot.get("id"), int):
        raise RuntimeError("Telegram getMe returned an invalid bot identity.")
    chat = telegram_call(token, "getChat", {"chat_id": str(chat_id)})
    if not isinstance(chat, dict) or not chat.get("type"):
        raise RuntimeError("Telegram getChat returned an invalid destination.")
    chat_type = chat["type"]
    if chat_type in ("channel", "group", "supergroup"):
        member = telegram_call(token, "getChatMember", {
            "chat_id": str(chat_id), "user_id": bot["id"]
        })
        status = member.get("status") if isinstance(member, dict) else None
        if status in ("left", "kicked", None):
            raise RuntimeError(f"PitchIQ bot is not a member of destination {chat_id}.")
        if chat_type == "channel":
            if status not in ("administrator", "creator"):
                raise RuntimeError(f"PitchIQ bot is not an administrator of channel {chat_id}.")
            if member.get("can_post_messages") is False:
                raise RuntimeError(f"PitchIQ bot cannot post messages in channel {chat_id}.")
    print(f"Telegram preflight passed: bot @{bot.get('username', 'unknown')} can access destination {chat_id} ({chat_type}).")
    return {"bot_id": bot["id"], "chat_type": chat_type}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", default=os.environ.get("TELEGRAM_CHAT_ID"))
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    verify_destination(token, args.chat_id)


if __name__ == "__main__":
    main()
