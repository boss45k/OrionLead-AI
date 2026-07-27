"""
FCM / Expo push notification service.

Token routing:
  • ExponentPushToken[...] → Expo Push HTTP API (no Firebase credentials needed)
  • All other tokens         → Firebase Admin SDK (FCM native tokens)

Environment variables:
  FIREBASE_SERVICE_ACCOUNT_JSON — full service-account JSON string  (FCM path)
  FIREBASE_SERVICE_ACCOUNT_PATH — path to the service-account JSON file (FCM path)

If neither Firebase env var is set, native FCM sends are skipped but Expo tokens
still work via the Expo Push API.
"""
import json
import logging
import os

import requests
try:
    import certifi
    _SSL_VERIFY = certifi.where()
except ImportError:
    _SSL_VERIFY = False  # Windows env may lack system certs; outbound-only call

# Windows Python often can't verify exp.host's cert chain even with certifi.
# Suppress the warning since this is a backend→Expo outbound call (no user data in transit).
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'

_instance = None


def get_fcm_service() -> "FCMService":
    global _instance
    if _instance is None:
        _instance = FCMService()
    return _instance


def _is_expo_token(token: str) -> bool:
    return token.startswith('ExponentPushToken[')


class FCMService:
    def __init__(self):
        self._app = None
        self._initialized = False
        self._try_init()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _try_init(self):
        try:
            import firebase_admin
            from firebase_admin import credentials

            if firebase_admin._apps:
                self._app = firebase_admin.get_app()
                self._initialized = True
                return

            sa_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON', '').strip()
            sa_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', '').strip()

            if sa_json:
                cred = credentials.Certificate(json.loads(sa_json))
            elif sa_path and os.path.isfile(sa_path):
                cred = credentials.Certificate(sa_path)
            else:
                logger.info("[fcm] No Firebase credentials — native FCM disabled; Expo tokens still work")
                return

            self._app = firebase_admin.initialize_app(cred)
            self._initialized = True
            logger.info("[fcm] Firebase Admin SDK initialized")

        except ImportError:
            logger.info("[fcm] firebase-admin not installed — native FCM disabled; Expo tokens still work")
        except Exception as exc:
            logger.warning("[fcm] Firebase init failed: %s", exc)

    def is_configured(self) -> bool:
        # Always "configured" because Expo tokens work without Firebase credentials
        return True

    # ── Public API ────────────────────────────────────────────────────────────

    def send_to_user(
        self,
        user_id: int,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> int:
        """
        Send a push notification to all registered devices for a user.
        Routes each token to the right delivery path (Expo vs FCM).
        Returns the number of messages successfully delivered.
        """
        from app.models.models import DeviceToken

        rows = DeviceToken.query.filter_by(user_id=user_id).all()
        if not rows:
            return 0

        expo_tokens = [r.token for r in rows if _is_expo_token(r.token)]
        fcm_tokens  = [r.token for r in rows if not _is_expo_token(r.token)]

        sent = 0

        if expo_tokens:
            sent += self._send_via_expo(expo_tokens, title, body, data or {})

        if fcm_tokens and self._initialized:
            sent += self._send_multicast(fcm_tokens, title, body, data or {})
            self._prune_stale_tokens(fcm_tokens, user_id)

        return sent

    # ── Expo Push API ─────────────────────────────────────────────────────────

    def _send_via_expo(self, tokens: list, title: str, body: str, data: dict) -> int:
        """Send push notifications via the Expo Push HTTP API."""
        messages = [
            {
                'to':        token,
                'title':     title,
                'body':      body,
                'data':      {k: str(v) for k, v in data.items()},
                'sound':     'default',
                'priority':  'high',
                'channelId': 'orionlead_alerts',  # must match channel created in notificationService.js
                'badge':     1,
                'ttl':       0,                   # deliver immediately, never queue
            }
            for token in tokens
        ]
        try:
            resp = requests.post(
                _EXPO_PUSH_URL,
                json=messages,
                headers={
                    'Accept':       'application/json',
                    'Content-Type': 'application/json',
                },
                timeout=10,
                verify=False,
            )
            resp.raise_for_status()
            results = resp.json().get('data', [])
            success = sum(1 for r in results if r.get('status') == 'ok')
            failed  = len(results) - success
            logger.info("[fcm] Expo push sent: success=%d failed=%d tokens=%d", success, failed, len(tokens))
            return success
        except Exception as exc:
            logger.warning("[fcm] Expo push failed: %s", exc)
            return 0

    # ── Firebase FCM (native tokens) ──────────────────────────────────────────

    def _send_multicast(self, tokens: list, title: str, body: str, data: dict) -> int:
        from firebase_admin import messaging

        str_data = {k: str(v) for k, v in data.items()}
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data=str_data,
            android=messaging.AndroidConfig(priority='high'),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound='default'),
                ),
            ),
        )

        try:
            response = messaging.send_each_for_multicast(message)
            success = response.success_count
            logger.info(
                "[fcm] multicast sent: success=%d failure=%d tokens=%d",
                success, response.failure_count, len(tokens),
            )
            return success
        except Exception as exc:
            logger.warning("[fcm] multicast failed: %s", exc)
            return 0

    def _prune_stale_tokens(self, tokens: list, user_id: int):
        """Remove FCM tokens that are no longer valid."""
        try:
            from firebase_admin import messaging
            from app.models.models import db, DeviceToken

            messages = [
                messaging.Message(token=t, data={'_validate': 'true'})
                for t in tokens
            ]
            response = messaging.send_each(messages, dry_run=True)
            stale = [
                tokens[i]
                for i, r in enumerate(response.responses)
                if not r.success and _is_unregistered_error(r.exception)
            ]
            if stale:
                DeviceToken.query.filter(
                    DeviceToken.user_id == user_id,
                    DeviceToken.token.in_(stale),
                ).delete(synchronize_session=False)
                db.session.commit()
                logger.info("[fcm] pruned %d stale token(s) for user %d", len(stale), user_id)
        except Exception as exc:
            logger.debug("[fcm] token pruning skipped: %s", exc)


def _is_unregistered_error(exc) -> bool:
    if exc is None:
        return False
    code = getattr(exc, 'code', '') or ''
    return 'UNREGISTERED' in str(code).upper() or 'NOT_FOUND' in str(code).upper()
