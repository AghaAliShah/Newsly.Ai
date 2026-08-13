"""Verifies an inbound request actually came from Slack (HMAC signature check).

Without this, anyone who found the /api/slack-update URL could POST to it
directly and trigger the pipeline — worse than the read-only search
endpoint, since this one really posts to your channel and writes to your
Sheet. Slack's own verification recipe: https://api.slack.com/authentication/verifying-requests-from-slack
"""

import hashlib
import hmac
import time


def verify_slack_signature(
    signing_secret: str, timestamp: str, raw_body: bytes, provided_signature: str
) -> bool:
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False  # stale request — replay-attack protection
    except (TypeError, ValueError):
        return False

    basestring = f"v0:{timestamp}:{raw_body.decode()}".encode()
    computed = "v0=" + hmac.new(signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, provided_signature or "")
