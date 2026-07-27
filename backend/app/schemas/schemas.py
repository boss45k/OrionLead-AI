"""
Request/Response Validation Schemas
Using Marshmallow for data validation and serialization
"""

from marshmallow import Schema, fields, validate, validates, ValidationError
from datetime import datetime


class BaseSchema(Schema):
    """Base schema with common datetime fields"""
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class UserSchema(BaseSchema):
    """User validation schema"""
    id = fields.Integer(dump_only=True)
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=8), load_only=True)
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    company = fields.String(allow_none=True)
    role = fields.String(dump_only=True)          # never settable via self-registration
    is_active = fields.Boolean(dump_only=True)    # never settable via self-registration
    source = fields.String(
        validate=validate.OneOf(['web', 'mobile']),
        load_default='web',
    )


class UserProfileSchema(Schema):
    """User profile response schema (no password)"""
    id = fields.Integer()
    uuid = fields.String()
    email = fields.Email()
    full_name = fields.String()
    company = fields.String()
    role = fields.String()
    is_active = fields.Boolean()
    profile_photo_url = fields.String(allow_none=True)


class LoginSchema(Schema):
    """Login request validation"""
    email = fields.Email(required=True)
    password = fields.String(required=True)


class TokenResponseSchema(Schema):
    """JWT token response"""
    message = fields.String()
    token = fields.String()
    user = fields.Nested(UserProfileSchema)


class LeadSchema(BaseSchema):
    """Lead validation schema"""
    id = fields.Integer(dump_only=True)
    uuid = fields.String(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    email = fields.Email(allow_none=True)
    phone = fields.String(validate=validate.Length(min=7, max=20), allow_none=True)
    company = fields.String(allow_none=True)
    position = fields.String(allow_none=True)
    location = fields.String(allow_none=True)
    country = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    industry = fields.String(allow_none=True)
    website = fields.String(allow_none=True)
    linkedin_url = fields.String(allow_none=True)
    interests = fields.List(fields.String(), dump_default=[])
    product = fields.String(allow_none=True)
    qualification_score = fields.Float(validate=validate.Range(min=0, max=100), dump_default=0.0)
    status = fields.String(
        validate=validate.OneOf(['pending', 'qualified', 'contacted', 'converted']), 
        dump_default='pending'
    )
    source = fields.String(dump_default='manual')
    lead_type = fields.String(allow_none=True)
    data_points = fields.Dict(dump_default={})
    notes = fields.String(allow_none=True)
    collected_by     = fields.Integer(dump_only=True, allow_none=True)
    assigned_to      = fields.Integer(dump_only=True, allow_none=True)
    origin           = fields.String(dump_only=True, allow_none=True)
    outcome          = fields.String(dump_only=True, allow_none=True)  # from LeadOutcome table


class LeadListSchema(Schema):
    """Lead list response"""
    leads = fields.List(fields.Nested(LeadSchema))
    total = fields.Integer()
    current_page = fields.Integer()
    total_pages = fields.Integer()
    per_page = fields.Integer()


class LeadCreateSchema(LeadSchema):
    """Lead creation - exclude read-only fields"""
    class Meta:
        exclude = ('id', 'created_at', 'updated_at')


class LeadUpdateSchema(Schema):
    """Lead update - all fields optional"""
    name = fields.String(validate=validate.Length(min=2, max=100), allow_none=True)
    email = fields.Email(allow_none=True)
    phone = fields.String(validate=validate.Length(min=7, max=20), allow_none=True)
    company = fields.String(allow_none=True)
    position = fields.String(allow_none=True)
    location = fields.String(allow_none=True)
    country = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    industry = fields.String(allow_none=True)
    website = fields.String(allow_none=True)
    linkedin_url = fields.String(allow_none=True)
    interests = fields.List(fields.String(), allow_none=True)
    product = fields.String(allow_none=True)
    qualification_score = fields.Float(validate=validate.Range(min=0, max=100), allow_none=True)
    status = fields.String(
        validate=validate.OneOf([
            'pending', 'qualified', 'contacted', 'converted',
            'hot', 'warm', 'cold', 'unqualified', 'low_quality',
        ]),
        allow_none=True
    )
    lead_type = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)


class DataSourceSchema(BaseSchema):
    """Data source validation schema"""
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    url = fields.Url(required=True)
    type = fields.String(
        required=True, 
        validate=validate.OneOf(['web', 'social_media', 'directory', 'api'])
    )
    last_crawled = fields.DateTime(allow_none=True)
    status = fields.String(
        validate=validate.OneOf(['active', 'inactive', 'error']),
        dump_default='active'
    )
    config = fields.Dict(dump_default={})


class ClassificationCategorySchema(BaseSchema):
    """Classification category validation"""
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    description = fields.String(allow_none=True)
    keywords = fields.List(fields.String(), dump_default=[])


class LeadActivitySchema(BaseSchema):
    """Lead activity tracking"""
    id = fields.Integer(dump_only=True)
    lead_id = fields.Integer(required=True)
    user_id = fields.Integer(dump_only=True)
    activity_type = fields.String(
        required=True,
        validate=validate.OneOf(['call', 'email', 'meeting', 'note', 'status_changed'])
    )
    notes = fields.String(allow_none=True)


class ErrorResponseSchema(Schema):
    """Error response format"""
    error = fields.String()
    message = fields.String()
    status_code = fields.Integer()
    details = fields.Dict(allow_none=True)
    timestamp = fields.DateTime()


class SearchSchema(Schema):
    """Search query validation"""
    query = fields.String(required=True, validate=validate.Length(min=1, max=255))
    limit = fields.Integer(validate=validate.Range(min=1, max=100), dump_default=10)
    offset = fields.Integer(validate=validate.Range(min=0), dump_default=0)


class PaginationSchema(Schema):
    """Pagination parameters validation"""
    page = fields.Integer(validate=validate.Range(min=1), load_default=1)
    per_page = fields.Integer(
        validate=validate.Range(min=1, max=100),
        load_default=10
    )
    sort_by = fields.String(load_default='created_at')
    sort_order = fields.String(
        validate=validate.OneOf(['asc', 'desc']),
        load_default='desc'
    )
    
    class Meta:
        unknown = 'exclude'


class FilterSchema(Schema):
    """Lead filtering parameters"""
    status = fields.String(allow_none=True)  # supports comma-separated e.g. pending,low_quality
    source = fields.String(allow_none=True)
    search = fields.String(allow_none=True)
    location = fields.String(allow_none=True)
    country = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    industry = fields.String(allow_none=True)
    product = fields.String(allow_none=True)
    interest = fields.String(allow_none=True)
    buying_intent = fields.String(allow_none=True)
    quality_tier = fields.String(allow_none=True)
    verified_email = fields.Boolean(allow_none=True)
    min_score = fields.Float(validate=validate.Range(min=0, max=100), allow_none=True)
    max_score = fields.Float(validate=validate.Range(min=0, max=100), allow_none=True)
    date_from = fields.DateTime(allow_none=True)
    date_to = fields.DateTime(allow_none=True)

    class Meta:
        unknown = 'exclude'

