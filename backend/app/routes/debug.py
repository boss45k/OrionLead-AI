"""Simple test routes — disabled in production"""
import os
import logging
from flask import Blueprint, jsonify, request, abort, g
from app.routes.auth import create_token, token_required

logger = logging.getLogger(__name__)
debug_bp = Blueprint('debug', __name__, url_prefix='/api/v1/debug')


def _require_dev():
    """Block this endpoint when FLASK_ENV is not development or testing."""
    if os.getenv('FLASK_ENV', 'production') not in ('development', 'testing'):
        abort(404)


@debug_bp.route('/test-notification', methods=['POST'])
@token_required
def test_notification():
    """Send a test push notification to the authenticated user's devices."""
    from app.services.fcm_service import get_fcm_service
    from app.models.models import DeviceToken

    user_id = g.user_id
    tokens = DeviceToken.query.filter_by(user_id=user_id).all()
    if not tokens:
        return jsonify({'error': 'No device tokens registered for this user. Open the app first.'}), 404

    data = request.get_json(silent=True) or {}
    title = data.get('title', 'OrionLead Test')
    body  = data.get('body',  'Push notifications are working!')

    sent = get_fcm_service().send_to_user(user_id, title, body, {'type': 'test'})
    return jsonify({
        'sent': sent,
        'devices': len(tokens),
        'tokens': [t.token[:30] + '…' for t in tokens],
    }), 200 if sent > 0 else 500


@debug_bp.route('/test-login', methods=['POST'])
def test_login():
    """Dev-only test login endpoint. Returns 404 in production."""
    _require_dev()
    try:
        data = request.get_json(silent=True) or {}
        email = data.get('email', 'test@example.com')
        if not isinstance(email, str) or '@' not in email:
            return jsonify({'error': 'Invalid email'}), 400
        token = create_token(1, email)
        logger.debug("Debug test-login used for %s", email)
        return jsonify({
            'message': 'Test login successful',
            'token': token,
            'user': {'id': 1, 'email': email}
        }), 200
    except Exception as e:
        logger.error("Error in test login: %s", str(e))
        return jsonify({'error': 'Internal error'}), 500
