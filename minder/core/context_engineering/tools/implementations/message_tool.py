"""Cross-channel message tool — send messages via webhooks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from minder.core.paths import minder_dir

logger = logging.getLogger(__name__)


def _load_channel_config() -> dict[str, Any]:
    """Load channel configuration from settings."""
    config_paths = [
        minder_dir() / "settings.json",
        Path(".minder") / "settings.json",
    ]
    channels: dict[str, Any] = {}
    for path in config_paths:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                channels.update(data.get("channels", {}))
            except (json.JSONDecodeError, OSError):
                continue
    return channels


class MessageTool:
    """Send messages to configured channels via webhooks."""

    def execute(
        self,
        channel: str,
        target: Optional[str] = None,
        message: str = "",
        format: str = "text",
    ) -> dict[str, Any]:
        """Send a message to a channel.

        Args:
            channel: Channel type ("slack", "discord", "webhook")
            target: Channel-specific target (webhook URL, channel ID).
                   Falls back to configured default for the channel.
            message: Message content
            format: Message format ("text" or "markdown")
        """
        if not message:
            return {"success": False, "error": "message is required", "output": None}
        if not channel:
            return {"success": False, "error": "channel is required", "output": None}

        # Load channel config to get webhook URLs
        config = _load_channel_config()
        channel_config = config.get(channel, {})

        # Determine webhook URL
        webhook_url = target or channel_config.get("webhook_url", "")
        if not webhook_url:
            # No external channel is set up. Do NOT fail the turn — an unconfigured
            # channel is a usage mistake, not an outage, and hard-failing here kills
            # the agent's turn ("Couldn't finish") so it can't keep talking to the
            # user. Return a soft, successful result that redirects the agent to
            # interact in-conversation: the user is right here, so it should say the
            # message directly (and for approvals, use the on-screen decision card
            # or ask the user here) rather than routing to a channel.
            logger.info(
                "send_message: no '%s' channel configured; redirecting to in-conversation reply",
                channel,
            )
            return {
                "success": True,
                "delivered": False,
                "channel": channel,
                "output": (
                    f"No external '{channel}' channel is configured, so nothing was sent "
                    "outside this conversation — and none is needed. The user is here in the "
                    "chat: say this to them directly in your reply. If you need their approval "
                    "for an action, present the on-screen decision card or ask the user here; "
                    "do NOT retry send_message or try another channel."
                ),
                "_llm_suffix": (
                    "\n\n[SYSTEM: send_message was not delivered (no channel configured) and "
                    "must not be retried. Respond to the user directly in this conversation "
                    "instead — they will see and answer your message here.]"
                ),
            }

        try:
            import urllib.request
            import urllib.error

            # Build payload based on channel type
            if channel == "slack":
                payload = {"text": message}
                if format == "markdown":
                    payload = {
                        "blocks": [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": message},
                            }
                        ]
                    }
            elif channel == "discord":
                payload = {"content": message}
            else:
                # Generic webhook
                payload = {"text": message, "format": format}

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.status
                if 200 <= status < 300:
                    return {
                        "success": True,
                        "output": f"Message sent to {channel} (status {status})",
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Webhook returned status {status}",
                        "output": None,
                    }

        except urllib.error.HTTPError as e:
            return {
                "success": False,
                "error": f"HTTP error {e.code}: {e.reason}",
                "output": None,
            }
        except urllib.error.URLError as e:
            return {
                "success": False,
                "error": f"Connection error: {e.reason}",
                "output": None,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to send message: {e}",
                "output": None,
            }
