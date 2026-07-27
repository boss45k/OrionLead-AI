"""
Mobile-specific API routes.
  POST   /api/v1/mobile/register-token    — upsert an FCM device token for the current user
  DELETE /api/v1/mobile/unregister-token  — remove a specific FCM token
"""
import logging

from flask import Blueprint, g, jsonify, request

from app.routes.auth import token_required

logger = logging.getLogger(__name__)

mobile_bp = Blueprint('mobile', __name__, url_prefix='/api/v1/mobile')

_VALID_PLATFORMS = {'android', 'ios', 'web'}


@mobile_bp.route('/register-token', methods=['POST'])
@token_required
def register_device_token():
    """
    Register or refresh an FCM device token for the authenticated user.

    Body (JSON):
      token        string  required  — FCM registration token
      platform     string  optional  — 'android' | 'ios' | 'web'  (default: 'android')
      app_version  string  optional  — e.g. '1.2.3'
    """
    from app.models.models import db, DeviceToken

    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token is required'}), 400

    platform = (data.get('platform') or 'android').lower()
    if platform not in _VALID_PLATFORMS:
        return jsonify({'error': f"platform must be one of: {', '.join(sorted(_VALID_PLATFORMS))}"}), 400

    app_version = (data.get('app_version') or '')[:20] or None
    user_id = g.user_id

    try:
        existing = DeviceToken.query.filter_by(token=token).first()
        if existing:
            # Token already registered — update owner/platform in case of re-install
            existing.user_id    = user_id
            existing.platform   = platform
            existing.app_version = app_version
            db.session.commit()
            logger.info("[mobile] updated token for user %d platform=%s", user_id, platform)
            return jsonify({'status': 'updated'}), 200

        new_token = DeviceToken(
            user_id=user_id,
            token=token,
            platform=platform,
            app_version=app_version,
        )
        db.session.add(new_token)
        db.session.commit()
        logger.info("[mobile] registered new token for user %d platform=%s", user_id, platform)
        return jsonify({'status': 'registered'}), 201

    except Exception as exc:
        db.session.rollback()
        logger.warning("[mobile] register-token error for user %d: %s", user_id, exc)
        return jsonify({'error': 'Failed to register token'}), 500


@mobile_bp.route('/unregister-token', methods=['DELETE'])
@token_required
def unregister_device_token():
    """
    Remove an FCM token so this device stops receiving notifications.

    Body (JSON):
      token  string  required
    """
    from app.models.models import db, DeviceToken

    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token is required'}), 400

    user_id = g.user_id

    try:
        deleted = DeviceToken.query.filter_by(token=token, user_id=user_id).delete()
        db.session.commit()
        if deleted:
            logger.info("[mobile] unregistered token for user %d", user_id)
            return jsonify({'status': 'unregistered'}), 200
        return jsonify({'status': 'not_found'}), 404

    except Exception as exc:
        db.session.rollback()
        logger.warning("[mobile] unregister-token error for user %d: %s", user_id, exc)
        return jsonify({'error': 'Failed to unregister token'}), 500
