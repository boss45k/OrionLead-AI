"""
Authentication routes
Handles user registration, login, and profile management
"""

from flask import Blueprint, jsonify, request, g
from werkzeug.security import generate_password_hash, check_password_hash
from marshmallow import ValidationError as MarshmallowValidationError
from typing import Dict, Any, cast, Optional
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
import os
import logging

from app.models.models import db, User
from app.schemas.schemas import (
    UserSchema,
    LoginSchema,
    UserProfileSchema,
)
from app.services.email_service import generate_otp, send_otp_email, _mask_email, OTP_EXPIRY_MIN
from app.exceptions import (
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    TokenExpiredError,
    InvalidTokenError,
    NotFoundError,
    DuplicateError,
    DatabaseError,
)
from app.utils.error_handler import handle_exceptions
from app.utils.rate_limiter import get_limiter
from app.utils.metrics import track_authentication, track_error

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


def _serialize_user(user: 'User') -> dict:
    """Serialize a User ORM object and always include profile_photo_url."""
    from flask import request as _req
    data: dict = cast(dict, UserProfileSchema().dump(user))
    data['profile_photo_url'] = (
        f"{_req.host_url}api/v1/auth/avatar/{user.profile_photo}"
        if user.profile_photo else None
    )
    return data


def _company_admin_exists(company: Optional[str]) -> bool:
    """True if an active sub_admin (company admin) already exists for this company."""
    if not company or not company.strip():
        return False
    norm = company.strip().lower()
    return db.session.query(User.id).filter(
        db.func.lower(db.func.trim(User.company)) == norm,
        User.role == 'sub_admin',
        User.is_active == True,  # noqa: E712
    ).first() is not None


def _company_exists(company: Optional[str], exclude_user_id: Optional[int] = None) -> bool:
    """True if at least one OTHER user is already on record under this company name.

    A blank company, or a brand-new company nobody else is registered under yet,
    returns False — those registrants activate immediately after OTP verification
    instead of waiting on an approver.
    """
    if not company or not company.strip():
        return False
    norm = company.strip().lower()
    q = db.session.query(User.id).filter(db.func.lower(db.func.trim(User.company)) == norm)
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.first() is not None


limiter = get_limiter()

# ── JWT config ─────────────────────────────────────────────────────────────────
# Read once at import time so every request is not paying an env-lookup.
# Values are intentionally weak defaults that trigger the production validator.
_JWT_SECRET: str    = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-dev-only-change-in-production')
_JWT_ALGORITHM: str = os.getenv('JWT_ALGORITHM',  'HS256')
_JWT_EXPIRY_H: int  = int(os.getenv('JWT_EXPIRATION_HOURS', '24'))


def create_token(user_id, email, role='user', user_uuid=None):
    """
    Create JWT token for user

    Args:
        user_id: User database ID
        email: User email address
        role: User role (admin, manager, user)
        user_uuid: Canonical UUID shared across MySQL and Supabase

    Returns:
        JWT token string

    Raises:
        ValidationError: If token creation fails
    """
    secret_key = _JWT_SECRET
    algorithm = _JWT_ALGORITHM
    expiration_hours = _JWT_EXPIRY_H

    try:
        payload = {
            'user_id': user_id,
            'uuid': user_uuid,
            'email': email,
            'role': role,
            'exp': datetime.now(timezone.utc) + timedelta(hours=expiration_hours),
            'iat': datetime.now(timezone.utc)
        }
        
        token = jwt.encode(payload, secret_key, algorithm=algorithm)
        return token
    
    except Exception as e:
        logger.error(f"Token creation failed: {str(e)}")
        raise ValidationError("Failed to create authentication token")


def token_required(f):
    """
    Decorator to validate JWT token or user API key in request.
    Accepts:
      - Authorization: Bearer <jwt>
      - X-API-Key: sk_user_<key>
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        from app.models.models import User

        # ── API Key path ──────────────────────────────────────────────────────
        raw_api_key = request.headers.get('X-API-Key', '').strip()
        if raw_api_key:
            user = User.query.filter_by(api_key=raw_api_key, is_active=True).first()
            if not user:
                logger.warning(f"Invalid API key attempt from {request.remote_addr}")
                raise InvalidTokenError("Invalid API key")
            g.user_id = user.id
            g.email   = user.email
            g.role    = user.role or 'user'
            g.company = (user.company or '').strip()
            return f(*args, **kwargs)

        # ── JWT Bearer path ───────────────────────────────────────────────────
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                raise InvalidTokenError("Invalid Authorization header format. Use: Bearer {token}")

        if not token:
            raise AuthenticationError("Authentication token is missing")

        try:
            data = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
            user_id = data['user_id']

        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired token attempt from {request.remote_addr}")
            raise TokenExpiredError()

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token attempt from {request.remote_addr}: {str(e)}")
            raise InvalidTokenError()

        # Re-read role and active status from DB on every request so that
        # role changes (e.g. admin → user) and account deactivations take
        # effect immediately without waiting for the token to expire.
        user = User.query.filter_by(id=user_id, is_active=True).first()
        if not user:
            raise AuthenticationError("Account not found or deactivated")

        g.user_id = user.id
        g.email   = user.email
        g.role    = user.role or 'user'
        g.company = (user.company or '').strip()

        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """
    Require admin role. Must be stacked after @token_required.
    Returns 403 (not 401) — the caller is authenticated but not authorised.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if getattr(g, 'role', None) != 'admin':
            raise AuthorizationError("Admin access required")
        return f(*args, **kwargs)
    return decorated


def manager_or_admin_required(f):
    """
    Require manager or admin role. Must be stacked after @token_required.
    Returns 403 (not 401) — the caller is authenticated but not authorised.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if getattr(g, 'role', None) not in ('manager', 'admin'):
            raise AuthorizationError("Manager or admin access required")
        return f(*args, **kwargs)
    return decorated


def company_admin_or_admin_required(f):
    """
    Allow system admin OR sub_admin (company admin). Must be stacked after @token_required.
    sub_admin can only manage users inside their own company.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if getattr(g, 'role', None) not in ('admin', 'sub_admin'):
            raise AuthorizationError("Admin or Company Admin access required")
        return f(*args, **kwargs)
    return decorated


def mobile_user_required(f):
    """
    Require the user to have registered via the mobile app (source='mobile').
    Admins and managers bypass this check (they may use both web and mobile).
    Must be stacked after @token_required.
    Returns 403 — authenticated but not allowed to sync.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if getattr(g, 'role', None) in ('admin', 'manager'):
            return f(*args, **kwargs)
        user = User.query.get(g.user_id)
        if not user or user.source != 'mobile':
            raise AuthorizationError("Sync is only available for mobile-registered accounts")
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/register', methods=['POST'])
@limiter.limit(lambda: "5 per hour" if os.getenv('FLASK_ENV') == 'production' else "30 per hour")
@handle_exceptions
def register():
    """
    Register a new user account
    ---
    tags:
      - Authentication
    summary: Register a new user
    description: Create a new user account with email, password, and profile information
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - email
              - password
              - full_name
            properties:
              email:
                type: string
                format: email
                example: user@example.com
              password:
                type: string
                minLength: 8
                example: SecurePassword123!
              full_name:
                type: string
                minLength: 2
                example: John Doe
              company:
                type: string
                nullable: true
                example: Acme Corp
    responses:
      201:
        description: User registered successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [success]
                data:
                  $ref: '#/components/schemas/User'
                request_id:
                  type: string
                  format: uuid
      400:
        description: Validation error - invalid input data
      409:
        description: Duplicate error - email already registered
      429:
        description: Rate limit exceeded (5 per hour)
    """
    # Validate request format and data
    try:
        json_data = request.get_json()
        if not json_data:
            raise ValidationError("Request body must be JSON")
        
        schema = UserSchema()
        data: Dict[str, Any] = schema.load(json_data)  # type: ignore[assignment]
    
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid user data", details=details_dict)
    
    # Check if email already exists
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        track_authentication("registration_failed")
        raise DuplicateError("Email", data['email'])
    
    try:
        source = data.get('source', 'web')
        # Create new user — inactive until email is verified (or admin approves if email fails)
        user = User(
            email=data['email'],
            password_hash=generate_password_hash(data['password']),
            full_name=data['full_name'],
            company=data.get('company'),
            role='user',
            is_active=False,
            source=source,
            sync_status='pending' if source == 'mobile' else 'synced',
        )

        db.session.add(user)
        db.session.commit()

        # Generate OTP for email verification
        code = generate_otp()
        user.otp_code       = code
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MIN)
        user.otp_attempts   = 0
        user.email_verified = False
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {str(e)}")
        track_authentication("registration_failed")
        track_error("registration_error")
        raise DatabaseError("Failed to register user")

    # Send OTP email — failure does not cancel registration; account falls back to admin approval
    otp_sent = send_otp_email(user.email, code, user.full_name)

    logger.info(f"New user registered: {user.email} (otp_sent={otp_sent})")
    track_authentication("registration_success")

    # Sync to Supabase synchronously — ensures mobile sees the UUID immediately.
    try:
        from app.services.sync_service import get_sync_service
        get_sync_service().sync_users_to_supabase([user.id])
    except Exception as _sync_err:
        logger.warning(f"Post-register Supabase sync failed (non-fatal): {_sync_err}")

    # Blank/brand-new companies (nobody else registered under that name yet)
    # activate straight after OTP verification. Only a company name that
    # already exists in the system routes the account to an approver —
    # that company's own admin if one exists, otherwise a system administrator.
    needs_approval = _company_exists(user.company, exclude_user_id=user.id)
    approver = 'your company administrator' if _company_admin_exists(user.company) else 'a system administrator'

    if otp_sent:
        if needs_approval:
            message = (
                'Account created. Please check your email for a verification code. '
                f'After verifying, {approver} will need to approve your account before you can sign in.'
            )
        else:
            message = 'Account created. Please check your email for a verification code to activate your account.'
        return jsonify({
            'status':  'verify_email',
            'message': message,
            'email':   _mask_email(user.email),
        }), 201
    else:
        return jsonify({
            'status':  'pending_approval',
            'message': f'Account created, but we could not deliver the verification email. '
                       f'{approver.capitalize()} will review and activate your account.',
            'email':   _mask_email(user.email),
        }), 201


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute")  # Prevent brute-force attacks
@handle_exceptions
def login():
    """
    Authenticate user and generate JWT token
    ---
    tags:
      - Authentication
    summary: User login
    description: Authenticate with email and password to receive a JWT token
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - email
              - password
            properties:
              email:
                type: string
                format: email
                example: user@example.com
              password:
                type: string
                example: SecurePassword123!
    responses:
      200:
        description: Login successful
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [success]
                token:
                  type: string
                  description: JWT authentication token
                user:
                  $ref: '#/components/schemas/User'
                request_id:
                  type: string
                  format: uuid
      400:
        description: Validation error - invalid input
      401:
        description: Authentication failed - invalid credentials or inactive account
      404:
        description: User not found
      429:
        description: Rate limit exceeded (10 per minute)
    """
    # Validate login credentials
    try:
        json_data = request.get_json()
        if not json_data:
            raise ValidationError("Request body must be JSON")
        
        schema = LoginSchema()
        data: Dict[str, Any] = schema.load(json_data)  # type: ignore[assignment]
    
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid login data", details=details_dict)
    
    # Find user by email.
    # Deliberately return the same error for "no such email" and "wrong password"
    # so that response codes cannot be used to enumerate valid email addresses.
    user = User.query.filter_by(email=data['email']).first()

    if not user:
        logger.warning(f"Login attempt for unknown email from {request.remote_addr}")
        track_authentication(status="login_failed")
        raise AuthenticationError("Invalid credentials")
    
    # Verify password — same message as the "no user" branch above (no enumeration).
    if not check_password_hash(user.password_hash, data['password']):
        logger.warning(f"Wrong password for {data['email']} from {request.remote_addr}")
        track_authentication(status="login_failed")
        raise AuthenticationError("Invalid credentials")
    
    # Check email verification first
    if not user.email_verified:
        logger.warning(f"Login attempt on unverified account: {data['email']}")
        track_authentication(status="login_failed")
        if user.otp_code:
            # OTP was sent — user just hasn't verified yet
            raise AuthenticationError("Please verify your email address. Check your inbox for a verification code.")
        else:
            # Email delivery failed at registration — account needs admin activation
            raise AuthenticationError("Your account is pending admin approval. Please contact your administrator.")

    # Check if user is active / approved
    if not user.is_active:
        track_authentication(status="login_failed")
        if user.approved_at:
            # Was approved before, then deactivated by an admin
            logger.warning(f"Login attempt on deactivated account: {data['email']}")
            raise AuthenticationError("Your account has been deactivated. Please contact your administrator.")
        else:
            # Never approved yet — awaiting the company admin (if one exists) or a system admin
            logger.warning(f"Login attempt on pending account: {data['email']}")
            approver = 'your company administrator' if _company_admin_exists(user.company) else 'a system administrator'
            raise AuthenticationError(f"Your account is pending approval from {approver}. Please contact them to activate your account.")
    
    try:
        # Generate authentication token — include UUID for cross-DB identity
        token = create_token(user.id, user.email, user.role or 'user', user.uuid)

        logger.info(f"User logged in: {user.email} (role: {user.role})")
        track_authentication(status="login_success")

        # Sync to Supabase synchronously — keeps users_sync.user_uuid aligned.
        # Failure is non-fatal (mobile can call POST /sync/user as fallback).
        try:
            from app.services.sync_service import get_sync_service
            get_sync_service().sync_users_to_supabase([user.id])
        except Exception as _sync_err:
            logger.warning(f"Post-login Supabase sync failed (non-fatal): {_sync_err}")

        # Response with token and user info
        user_data = _serialize_user(user)

        # First-ever login (vs. a returning session) — greeted differently on the frontend.
        is_first_login = False
        try:
            from app.routes.settings import _get_user_settings as _gus, _set_user_settings as _sus
            if not _gus(user.id).get('_has_logged_in'):
                is_first_login = True
                _sus(user.id, {'_has_logged_in': True})
        except Exception as _fl_err:
            logger.debug(f'[auth] first-login flag skipped: {_fl_err}')

        # Daily digest — fire-and-forget on first login of the day
        try:
            from app.routes.settings import _get_user_settings as _gs, _set_user_settings as _ss
            from app.services.email_service import send_daily_digest as _sdg
            from app.models.models import Lead as _Lead
            from sqlalchemy import func as _func
            import threading as _t
            from datetime import datetime as _ddt, timezone as _ttz
            _dp = _gs(user.id)
            if _dp.get('notify_daily_digest'):
                _today = _ddt.now(_ttz.utc).strftime('%Y-%m-%d')
                if _dp.get('_last_digest_date') != _today:
                    _ts   = _ddt.now(_ttz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    _tot  = _Lead.query.filter_by(collected_by=user.id).count()
                    _new  = _Lead.query.filter(_Lead.collected_by == user.id, _Lead.created_at >= _ts).count()
                    _hot  = _Lead.query.filter(_Lead.collected_by == user.id, _Lead.qualification_score >= 80).count()
                    _avg  = db.session.query(_func.avg(_Lead.qualification_score)).filter(
                        _Lead.collected_by == user.id, _Lead.qualification_score > 0
                    ).scalar() or 0
                    _em, _uid2, _td = user.email, user.id, _today
                    _tt, _tn, _th, _ta = int(_tot), int(_new), int(_hot), float(_avg)
                    def _send_digest():
                        try:
                            _sdg(_em, _tt, _tn, _th, _ta)
                            _ss(_uid2, {'_last_digest_date': _td})
                        except Exception:
                            pass
                    _t.Thread(target=_send_digest, daemon=True).start()
        except Exception as _de:
            logger.debug(f'[auth] daily digest skipped: {_de}')

        return jsonify({
            'status': 'success',
            'message': 'Login successful',
            'token': token,
            'user': user_data,
            'is_first_login': is_first_login,
        }), 200

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        track_authentication("login_failed")
        track_error("login_error")
        raise ValidationError("Failed to generate authentication token")


@auth_bp.route('/verify-email', methods=['POST'])
@limiter.limit("10 per hour")
@handle_exceptions
def verify_email():
    """
    Verify email address with OTP code sent during registration.
    Body: { email, code }
    """
    data  = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    code  = str(data.get('code', '')).strip()

    if not email or not code:
        raise ValidationError("email and code are required")

    user = User.query.filter_by(email=email).first()
    if not user:
        raise AuthenticationError("Invalid email or code")

    if user.email_verified:
        return jsonify({'status': 'success', 'message': 'Email already verified'}), 200

    MAX_ATTEMPTS = 5
    if user.otp_attempts >= MAX_ATTEMPTS:
        raise AuthenticationError("Too many incorrect attempts. Please request a new code.")

    if not user.otp_code or not user.otp_expires_at:
        raise AuthenticationError("No verification code found. Please request a new one.")

    now = datetime.now(timezone.utc)
    expires = user.otp_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if now > expires:
        raise AuthenticationError("Verification code has expired. Please request a new one.")

    if user.otp_code != code:
        user.otp_attempts = (user.otp_attempts or 0) + 1
        db.session.commit()
        remaining = MAX_ATTEMPTS - user.otp_attempts
        raise AuthenticationError(f"Incorrect code. {remaining} attempt(s) remaining.")

    # Success — mark verified and clear OTP.
    # A blank company, or a brand-new company nobody else is registered under
    # yet, activates immediately. Only a company name that already exists in
    # the system holds the account for approval — that company's own admin if
    # one exists, otherwise a system administrator.
    user.email_verified = True
    user.otp_code       = None
    user.otp_expires_at = None
    user.otp_attempts   = 0

    needs_approval = _company_exists(user.company, exclude_user_id=user.id)
    if not needs_approval:
        user.is_active = True
        if not user.approved_at:
            user.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    if needs_approval:
        logger.info(f"Email verified, pending admin approval: {email}")
        track_authentication("email_verification_success")
        approver = 'your company administrator' if _company_admin_exists(user.company) else 'a system administrator'
        return jsonify({
            'status':  'pending_approval',
            'message': f'Email verified. Your account is now awaiting approval from {approver}.',
        }), 200

    logger.info(f"Email verified and account activated: {email}")
    track_authentication("email_verification_success")
    return jsonify({'status': 'success', 'message': 'Email verified. You can now sign in.'}), 200


@auth_bp.route('/resend-otp', methods=['POST'])
@limiter.limit("3 per hour")
@handle_exceptions
def resend_otp():
    """
    Resend OTP verification email.
    Body: { email }
    """
    data  = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()

    if not email:
        raise ValidationError("email is required")

    user = User.query.filter_by(email=email).first()
    if not user:
        # Don't reveal whether the email exists
        return jsonify({'status': 'success', 'message': 'If that email is registered, a new code has been sent.'}), 200

    if user.email_verified:
        return jsonify({'status': 'success', 'message': 'Email already verified'}), 200

    code = generate_otp()
    user.otp_code       = code
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MIN)
    user.otp_attempts   = 0
    db.session.commit()

    send_otp_email(user.email, code, user.full_name)

    logger.info(f"OTP resent to: {email}")
    return jsonify({
        'status':  'success',
        'message': 'A new verification code has been sent to your email.',
        'email':   _mask_email(email),
    }), 200


@auth_bp.route('/google', methods=['POST'])
@handle_exceptions
def google_auth():
    """
    Authenticate or register via Google OAuth.
    Accepts either:
      - { credential: id_token }  (from GSI library)
      - { code: authorization_code, redirect_uri: '...' }  (from redirect flow)
    Backend verifies with Google, creates user if needed, returns JWT.
    """
    import requests as http_requests

    json_data = request.get_json()
    if not json_data:
        raise ValidationError("Request body is required")

    code = json_data.get('code')
    credential = json_data.get('credential')

    if not code and not credential:
        raise ValidationError("Google credential or authorization code is required")

    try:
        import urllib3
        # SSL verification disabled only in development (Windows SSL chain issues with Google APIs).
        ssl_verify = os.environ.get('FLASK_ENV', 'production') != 'development'
        if not ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        if code:
            # Authorization code flow: exchange code for tokens
            redirect_uri = json_data.get('redirect_uri', '')
            token_resp = http_requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code': code,
                    'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
                    'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code',
                },
                timeout=10,
                verify=ssl_verify,
            )
            if token_resp.status_code != 200:
                logger.error(f"Google token exchange failed: {token_resp.text}")
                raise AuthenticationError("Failed to exchange Google authorization code")

            tokens = token_resp.json()
            id_token_value = tokens.get('id_token', '')

            # Verify the id_token from the exchange
            google_resp = http_requests.get(
                'https://oauth2.googleapis.com/tokeninfo',
                params={'id_token': id_token_value},
                timeout=10,
                verify=ssl_verify,
            )
            if google_resp.status_code != 200:
                raise AuthenticationError("Invalid Google credential")

            google_data = google_resp.json()
        else:
            # Direct id_token verification (GSI flow)
            google_resp = http_requests.get(
                'https://oauth2.googleapis.com/tokeninfo',
                params={'id_token': credential},
                timeout=10,
                verify=ssl_verify,
            )
            if google_resp.status_code != 200:
                raise AuthenticationError("Invalid Google credential")

            google_data = google_resp.json()
    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f"Google token verification failed: {type(e).__name__}: {e}")
        dev_mode = os.environ.get('FLASK_ENV') == 'development'
        detail = f" ({type(e).__name__}: {e})" if dev_mode else ""
        raise AuthenticationError(f"Failed to verify Google credential{detail}")

    # Validate the token belongs to our app (optional: check 'aud' field)
    email = google_data.get('email')
    if not email or google_data.get('email_verified') != 'true':
        raise AuthenticationError("Google account email not verified")

    full_name = google_data.get('name', email.split('@')[0])

    # Find or create user
    user = User.query.filter_by(email=email).first()

    if not user:
        # Auto-register and activate Google users (Google verifies the email)
        user = User(
            email=email,
            password_hash=generate_password_hash(os.urandom(32).hex()),  # random password
            full_name=full_name,
            company=google_data.get('hd', ''),  # Google Workspace domain
            role='user',
            is_active=True,
            email_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        logger.info(f"New Google user registered and activated: {email}")
        track_authentication("google_registration_success")
    elif not user.email_verified:
        # Existing user who registered with email/password but never verified —
        # Google ownership proves the email, so grant verification now.
        user.email_verified = True
        user.otp_code       = None
        user.otp_expires_at = None
        db.session.commit()
        logger.info(f"Email verified via Google for existing user: {email}")

    if not user.is_active:
        raise AuthenticationError("Your account has been deactivated. Please contact your administrator.")

    # Generate JWT
    token = create_token(user.id, user.email, user.role or 'user')
    logger.info(f"Google login: {user.email}")
    track_authentication("google_login_success")

    user_data = _serialize_user(user)

    return jsonify({
        'status': 'success',
        'message': 'Login successful',
        'token': token,
        'user': user_data,
    }), 200


@auth_bp.route('/refresh', methods=['POST'])
@handle_exceptions
def refresh_token():
    """
    Refresh JWT token — accepts both valid and recently-expired tokens.
    ---
    tags:
      - Authentication
    summary: Refresh authentication token
    description: >
      Issues a new JWT using the current token.
      Accepts tokens that expired within the last 7 days (grace period) so
      the mobile app can silently refresh without forcing a re-login.
      Tokens older than 7 days are rejected and require a fresh login.
    security:
      - bearerAuth: []
    responses:
      200:
        description: Token refreshed successfully
      401:
        description: Token too old or invalid — must login again
    """
    from app.models.models import User

    _REFRESH_GRACE_DAYS = int(os.getenv('JWT_REFRESH_GRACE_DAYS', '7'))

    # ── Extract raw token ──────────────────────────────────────────────────────
    token = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1].strip()

    if not token:
        raise AuthenticationError("Authentication token is missing")

    # ── Decode allowing expired tokens (leeway = grace window) ────────────────
    try:
        data = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            options={"verify_exp": False},   # skip expiry check here — we do it manually
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[refresh] Invalid token from {request.remote_addr}: {e}")
        raise InvalidTokenError("Invalid token — please log in again")

    user_id = data.get('user_id')
    if not user_id:
        raise InvalidTokenError("Token payload missing user_id")

    # ── Enforce grace period ───────────────────────────────────────────────────
    exp = data.get('exp')
    if exp is not None:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        expired_at = datetime.fromtimestamp(exp, tz=timezone.utc)
        if now > expired_at + timedelta(days=_REFRESH_GRACE_DAYS):
            logger.warning(
                f"[refresh] Token too old (expired {(now - expired_at).days}d ago) "
                f"from {request.remote_addr}"
            )
            raise TokenExpiredError(
                "Session expired — please log in again"
            )

    # ── Verify user is still active ───────────────────────────────────────────
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("Account not found or deactivated")

    # ── Issue new token ────────────────────────────────────────────────────────
    new_token = create_token(user_id, user.email, user.role or 'user', user.uuid if hasattr(user, 'uuid') else None)
    expiration_hours = _JWT_EXPIRY_H

    logger.info(f"[refresh] Token refreshed for user: {user.email}")
    track_authentication(status="token_refreshed")

    return jsonify({
        'status':     'success',
        'token':      new_token,
        'expires_in': expiration_hours * 3600,
    }), 200


@auth_bp.route('/profile', methods=['GET'])
@token_required
@handle_exceptions
def get_profile():
    """
    Get authenticated user's profile
    
    Headers:
        Authorization: Bearer {token}
    
    Returns:
        200: User profile data
        401: Token invalid/expired
        404: User not found
        500: Server error
    """
    try:
        # User ID is set by token_required decorator
        user = db.session.get(User, g.user_id)
        
        if not user:
            logger.warning(f"Profile request for non-existent user ID: {g.user_id}")
            raise NotFoundError("User", g.user_id)
        
        return jsonify({
            'status': 'success',
            'message': 'Profile retrieved successfully',
            'user': _serialize_user(user),
        }), 200

    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        raise DatabaseError("Failed to retrieve user profile")


@auth_bp.route('/profile', methods=['PUT'])
@token_required
@handle_exceptions
def update_profile():
    """Update authenticated user's profile (full_name, company)"""
    try:
        user = db.session.get(User, g.user_id)
        if not user:
            raise NotFoundError("User", g.user_id)

        data = request.get_json(silent=True) or {}
        if 'full_name' in data and str(data['full_name']).strip():
            user.full_name = str(data['full_name']).strip()
        if 'company' in data:
            user.company = str(data['company']).strip() if data['company'] else None

        db.session.commit()

        # Sync updated profile to Supabase (non-fatal)
        try:
            from app.services.sync_service import get_sync_service
            get_sync_service().sync_users_to_supabase([user.id])
        except Exception as _e:
            logger.warning(f"Post-profile-update Supabase sync failed (non-fatal): {_e}")

        return jsonify({
            'status': 'success',
            'message': 'Profile updated successfully',
            'user': _serialize_user(user),
        }), 200

    except Exception as e:
        logger.error(f"Update profile error: {e}")
        db.session.rollback()
        raise DatabaseError("Failed to update profile")


@auth_bp.route('/profile/photo', methods=['PUT'])
@token_required
@handle_exceptions
def upload_profile_photo():
    """Upload / replace the current user's profile photo (multipart/form-data, field: photo)."""
    from pathlib import Path as _Path
    from PIL import Image as _Image
    import io as _io
    import uuid as _uuid_mod

    ALLOWED = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    AVATAR_DIR = _Path(__file__).resolve().parent.parent.parent / 'uploads' / 'avatars'
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    if 'photo' not in request.files:
        return jsonify({'status': 'error', 'message': 'No photo field in request'}), 400

    file = request.files['photo']
    if file.content_type not in ALLOWED:
        return jsonify({'status': 'error', 'message': 'Unsupported image type'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Delete old photo file if any
    if user.profile_photo:
        old_path = AVATAR_DIR / user.profile_photo
        if old_path.exists():
            old_path.unlink(missing_ok=True)

    # Resize to 256×256 square (centre-crop then resize)
    img = _Image.open(file.stream).convert('RGB')
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    img  = img.crop((left, top, left + side, top + side)).resize((256, 256), _Image.Resampling.LANCZOS)

    filename = f"{g.user_id}_{_uuid_mod.uuid4().hex[:8]}.jpg"
    img.save(AVATAR_DIR / filename, 'JPEG', quality=88, optimize=True)

    user.profile_photo = filename
    user.bump_version()
    db.session.commit()

    photo_url = f"{request.host_url}api/v1/auth/avatar/{filename}"
    return jsonify({'status': 'success', 'profile_photo_url': photo_url}), 200


@auth_bp.route('/profile/photo', methods=['DELETE'])
@token_required
@handle_exceptions
def delete_profile_photo():
    """Remove the current user's profile photo."""
    from pathlib import Path as _Path
    AVATAR_DIR = _Path(__file__).resolve().parent.parent.parent / 'uploads' / 'avatars'

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    if user.profile_photo:
        old_path = AVATAR_DIR / user.profile_photo
        if old_path.exists():
            old_path.unlink(missing_ok=True)
        user.profile_photo = None
        user.bump_version()
        db.session.commit()

    return jsonify({'status': 'success', 'message': 'Photo removed'}), 200


@auth_bp.route('/avatar/<filename>', methods=['GET'])
def serve_avatar(filename: str):
    """Serve a user avatar image (no auth — URLs are unguessable UUIDs)."""
    from pathlib import Path as _Path
    from flask import send_from_directory
    AVATAR_DIR = _Path(__file__).resolve().parent.parent.parent / 'uploads' / 'avatars'
    if not filename.endswith('.jpg') or '/' in filename or '..' in filename:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    return send_from_directory(str(AVATAR_DIR), filename)


@auth_bp.route('/change-password', methods=['POST'])
@token_required
@handle_exceptions
def change_password():
    """Change the authenticated user's password."""
    user = db.session.get(User, g.user_id)
    if not user:
        raise NotFoundError("User", g.user_id)

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password     = data.get('new_password', '')

    if not current_password or not new_password:
        raise ValidationError("current_password and new_password are required")

    if not check_password_hash(user.password_hash, current_password):
        raise AuthenticationError("Current password is incorrect")

    if len(new_password) < 8:
        raise ValidationError("New password must be at least 8 characters")

    if current_password == new_password:
        raise ValidationError("New password must differ from the current password")

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    logger.info(f"Password changed for user: {user.email}")

    return jsonify({'status': 'success', 'message': 'Password changed successfully'}), 200


@auth_bp.route('/logout', methods=['POST'])
@token_required
@handle_exceptions
def logout():
    """
    Logout user (client-side token deletion)
    Token is invalidated by not being stored server-side (stateless auth)
    
    Returns:
        200: Logout successful
    """
    logger.info(f"User logged out: {g.email}")
    
    return jsonify({
        'status': 'success',
        'message': 'Logout successful. Please delete the token on client side.',
    }), 200


# ─── Admin Routes ─────────────────────────────────────────────

@auth_bp.route('/admin/users', methods=['GET'])
@token_required
@company_admin_or_admin_required
@handle_exceptions
def admin_list_users():
    """List users. System admin sees all; sub_admin sees only their company."""
    if g.role == 'admin':
        users = User.query.order_by(User.created_at.desc()).all()
    else:
        company = g.company.lower()
        if not company:
            return jsonify({'status': 'success', 'users': [], 'total': 0,
                            'company_scope': True, 'company': ''}), 200
        users = User.query.filter(
            db.func.lower(db.func.trim(User.company)) == company
        ).order_by(User.created_at.desc()).all()

    return jsonify({
        'status': 'success',
        'users': [_serialize_user(u) for u in users],
        'total': len(users),
        'company_scope': g.role == 'sub_admin',
        'company': g.company if g.role == 'sub_admin' else None,
    }), 200


@auth_bp.route('/admin/users', methods=['POST'])
@token_required
@admin_required   # only system admin can create users
@handle_exceptions
def admin_create_user():
    """Create a new user (system admin only)."""
    json_data = request.get_json()
    if not json_data:
        raise ValidationError("Request body must be JSON")

    schema = UserSchema()
    try:
        from marshmallow import EXCLUDE as _EXCLUDE
        data = cast(dict, schema.load(json_data, unknown=_EXCLUDE))
    except MarshmallowValidationError as e:
        details_dict = dict(e.messages) if isinstance(e.messages, dict) else {}
        raise ValidationError("Invalid user data", details=details_dict)

    existing = User.query.filter_by(email=data['email']).first()
    if existing:
        raise DuplicateError("Email", data['email'])

    # Read role from raw json_data (not schema-loaded `data`) because UserSchema
    # marks `role` as dump_only to block self-registration role injection — but
    # admin creation must be able to set any valid role.
    requested_role = json_data.get('role', 'user')
    if requested_role not in ('admin', 'sub_admin', 'manager', 'user'):
        requested_role = 'user'

    # sub_admin must have a company
    company = data.get('company') or json_data.get('company')
    if requested_role == 'sub_admin' and not company:
        raise ValidationError("Company name is required when creating a Company Admin (sub_admin)")

    user = User(
        email=data['email'],
        password_hash=generate_password_hash(data['password']),
        full_name=data['full_name'],
        company=company,
        role=requested_role,
        is_active=True,
        email_verified=True,   # admin bypasses email verification
        approved_at=datetime.now(timezone.utc),
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'User created successfully',
        'user': _serialize_user(user),
    }), 201


@auth_bp.route('/admin/users/<int:user_id>', methods=['PUT'])
@token_required
@company_admin_or_admin_required
@handle_exceptions
def admin_update_user(user_id):
    """Update a user.
    System admin: full control (role, company, name, password, active).
    sub_admin: can only toggle is_active for users in their own company
               (cannot touch admins or other sub_admins).
    """
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("User", user_id)

    json_data = request.get_json()
    if not json_data:
        raise ValidationError("Request body must be JSON")

    if g.role == 'sub_admin':
        # Scope check: target user must be in same company
        caller_co = g.company.strip().lower()
        target_co = (user.company or '').strip().lower()
        if not caller_co or caller_co != target_co:
            raise AuthorizationError("You can only manage users in your own company")
        # Cannot manage admins or other sub_admins
        if user.role in ('admin', 'sub_admin'):
            raise AuthorizationError("Company Admins cannot manage admin-level accounts")
        # Can only toggle active status
        if 'is_active' in json_data:
            user.is_active = bool(json_data['is_active'])
            if user.is_active:
                if not user.email_verified:
                    user.email_verified = True
                    user.otp_code       = None
                    user.otp_expires_at = None
                if not user.approved_at:
                    user.approved_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'User updated', 'user': _serialize_user(user)}), 200

    # ── System admin: full control ────────────────────────────────────────────
    if 'full_name' in json_data:
        user.full_name = json_data['full_name']
    if 'company' in json_data:
        user.company = json_data['company']
    if 'role' in json_data and json_data['role'] in ('admin', 'sub_admin', 'manager', 'user'):
        # sub_admin role requires a company
        if json_data['role'] == 'sub_admin' and not (user.company or json_data.get('company')):
            raise ValidationError("Company name is required to assign Company Admin role")
        user.role = json_data['role']
    if 'is_active' in json_data:
        user.is_active = bool(json_data['is_active'])
        if user.is_active:
            if not user.email_verified:
                user.email_verified = True
                user.otp_code       = None
                user.otp_expires_at = None
            if not user.approved_at:
                user.approved_at = datetime.now(timezone.utc)
    if 'password' in json_data and len(json_data['password']) >= 8:
        user.password_hash = generate_password_hash(json_data['password'])

    db.session.commit()
    return jsonify({'status': 'success', 'message': 'User updated successfully', 'user': _serialize_user(user)}), 200


@auth_bp.route('/admin/users/<int:user_id>', methods=['DELETE'])
@token_required
@admin_required
@handle_exceptions
def admin_delete_user(user_id):
    """Delete a user (admin only). Cannot delete self."""
    if user_id == g.user_id:
        raise ValidationError("Cannot delete your own account")
    
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("User", user_id)
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': f'User {user.email} deleted successfully',
    }), 200


@auth_bp.route('/admin/stats', methods=['GET'])
@token_required
@company_admin_or_admin_required
@handle_exceptions
def admin_stats():
    """Admin dashboard stats. System admin: global. sub_admin: company-scoped."""
    from app.models.models import Lead

    if g.role == 'admin':
        total_users     = User.query.count()
        active_users    = User.query.filter_by(is_active=True).count()
        pending_users   = User.query.filter_by(is_active=False).count()
        admin_count     = User.query.filter_by(role='admin').count()
        total_leads     = Lead.query.count()
        qualified_leads = Lead.query.filter(Lead.qualification_score > 50).count()
    else:
        company = g.company.strip().lower()
        co_user_ids = [r.id for r in User.query.filter(
            db.func.lower(db.func.trim(User.company)) == company
        ).with_entities(User.id).all()] if company else []

        total_users     = len(co_user_ids)
        active_users    = User.query.filter(User.id.in_(co_user_ids), User.is_active == True).count() if co_user_ids else 0
        pending_users   = User.query.filter(User.id.in_(co_user_ids), User.is_active == False).count() if co_user_ids else 0
        admin_count     = 0
        total_leads     = Lead.query.filter(Lead.collected_by.in_(co_user_ids)).count() if co_user_ids else 0
        qualified_leads = Lead.query.filter(Lead.collected_by.in_(co_user_ids), Lead.qualification_score > 50).count() if co_user_ids else 0

    return jsonify({
        'status': 'success',
        'stats': {
            'total_users':     total_users,
            'active_users':    active_users,
            'pending_users':   pending_users,
            'admin_count':     admin_count,
            'total_leads':     total_leads,
            'qualified_leads': qualified_leads,
        },
        'company_scope': g.role == 'sub_admin',
        'company':       g.company if g.role == 'sub_admin' else None,
    }), 200


@auth_bp.route('/admin/bootstrap', methods=['POST'])
@token_required
@handle_exceptions
def bootstrap_first_admin():
    """
    Promote the calling user to admin.
    Only works when ZERO admin accounts exist — used to recover from a
    locked-out state (e.g. the first deployment or a role migration issue).
    Once any admin exists this endpoint returns 403.
    """
    existing_admins = User.query.filter_by(role='admin').count()
    if existing_admins > 0:
        raise AuthorizationError(
            "An admin account already exists. Ask that administrator to manage roles."
        )

    user = db.session.get(User, g.user_id)
    if not user:
        raise NotFoundError("User", g.user_id)

    user.role = 'admin'
    user.is_active = True  # activate if the account was still pending
    if not user.approved_at:
        user.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    logger.info(f"Bootstrap: {user.email} claimed first-admin role")

    return jsonify({
        'status': 'success',
        'message': 'You are now the system administrator. Please log in again to receive an updated token.',
        'user': _serialize_user(user),
    }), 200
