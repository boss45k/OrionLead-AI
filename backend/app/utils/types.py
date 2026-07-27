"""
Type Hints Module
Provides type definitions and hints for the application

This module helps with:
- IDE autocompletion and type checking
- Static type analysis (mypy)
- Runtime type validation
- Better code documentation
"""

from typing import (
    Any, Dict, List, Optional, Tuple, Union,
    Callable, TypeVar, Generic, Protocol, Literal
)
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# ============ Scalar Types ============
UserId = int
LeadId = int
Score = float  # 0-100
Email = str
Token = str
RequestId = str


# ============ Enumerations ============
class LeadStatus(str, Enum):
    """Valid lead status values"""
    NEW = "new"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    REJECTED = "rejected"


class UserRole(str, Enum):
    """Valid user roles"""
    USER = "user"
    ADMIN = "admin"
    ANALYST = "analyst"


class QualificationTier(str, Enum):
    """Lead qualification tiers based on score"""
    EXCELLENT = "excellent"  # 80-100
    GOOD = "good"             # 60-79
    FAIR = "fair"             # 40-59
    POOR = "poor"             # 20-39
    REJECT = "reject"         # 0-19


# ============ Data Classes / DTOs ============
@dataclass
class UserProfile:
    """User profile information"""
    id: UserId
    email: Email
    full_name: str
    company: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class LeadData:
    """Lead information"""
    id: LeadId
    name: str
    email: Optional[Email]
    phone: Optional[str]
    company: Optional[str]
    position: Optional[str]
    qualification_score: Score
    status: LeadStatus
    created_at: datetime
    updated_at: datetime
    data_points: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


@dataclass
class QualificationResult:
    """Result of lead qualification"""
    lead_id: LeadId
    score: Score
    qualified: bool
    tier: QualificationTier
    reasoning: str
    factors: Dict[str, float]  # Factor breakdown
    confidence: float  # 0-1
    model_version: str


@dataclass
class ApiResponse:
    """Standard API response"""
    status: Literal["success", "error"]
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
    request_id: Optional[RequestId] = None
    timestamp: Optional[datetime] = None


@dataclass
class PaginationInfo:
    """Pagination metadata"""
    page: int
    per_page: int
    total: int
    pages: int
    has_next: bool
    has_prev: bool


@dataclass
class PaginatedResponse:
    """Generic paginated response"""
    items: List[Any]
    pagination: PaginationInfo
    total: int


# ============ Query Request Types ============
@dataclass
class LeadFilterOptions:
    """Filtering options for lead queries"""
    status: Optional[LeadStatus] = None
    company: Optional[str] = None
    min_score: Optional[Score] = None
    max_score: Optional[Score] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    search_query: Optional[str] = None


@dataclass
class QualificationCriteria:
    """Criteria for lead qualification"""
    min_budget: Optional[int] = None
    max_budget: Optional[int] = None
    required_industries: Optional[List[str]] = None
    excluded_industries: Optional[List[str]] = None
    company_size: Optional[Literal["startup", "small", "medium", "large", "enterprise"]] = None
    location_required: Optional[bool] = None
    custom_rules: Optional[Dict[str, Any]] = None


# ============ Service Method Signatures ============
class AuthServiceInterface(Protocol):
    """Type hints for authentication service"""
    
    def register_user(self, email: str, password: str, full_name: str,
                     company: Optional[str] = None) -> UserProfile: ...
    
    def login_user(self, email: str, password: str) -> Tuple[UserProfile, Token]: ...
    
    def validate_token(self, token: Token) -> UserProfile: ...
    
    def refresh_token(self, old_token: Token) -> Token: ...


class LeadServiceInterface(Protocol):
    """Type hints for lead service"""
    
    def get_lead(self, lead_id: LeadId) -> Optional[LeadData]: ...
    
    def list_leads(self, page: int = 1, per_page: int = 20,
                  filters: Optional[LeadFilterOptions] = None) -> PaginatedResponse: ...
    
    def create_lead(self, name: str, email: Optional[str] = None,
                   company: Optional[str] = None, **kwargs) -> LeadData: ...
    
    def update_lead(self, lead_id: LeadId, **updates) -> LeadData: ...
    
    def delete_lead(self, lead_id: LeadId) -> bool: ...


class QualificationServiceInterface(Protocol):
    """Type hints for qualification service"""
    
    def qualify_lead(self, lead_id: LeadId,
                    criteria: Optional[QualificationCriteria] = None) -> QualificationResult: ...
    
    def qualify_leads_batch(self, lead_ids: List[LeadId],
                           criteria: Optional[QualificationCriteria] = None) -> List[QualificationResult]: ...
    
    def requalify_lead(self, lead_id: LeadId) -> QualificationResult: ...
    
    def get_qualification_history(self, lead_id: LeadId) -> List[QualificationResult]: ...


# ============ Common TypeVars ============
T = TypeVar('T')  # Generic type
ServiceT = TypeVar('ServiceT')  # Generic service type (no specific bound)


# ============ Callable Types ============
ErrorHandler = Callable[[Exception, Dict[str, Any]], Any]
ValidationFunc = Callable[[Any], bool]
TransformFunc = Callable[[Any], Any]


# ============ Union Types for API ============
JsonValue = Union[str, int, float, bool, None, List['JsonValue'], Dict[str, 'JsonValue']]
JsonObject = Dict[str, JsonValue]


# ============ Database Query Result Types ============
DbQueryResult = Union[Any, List[Any], None]
QueryExecutor = Callable[[str], DbQueryResult]


# ============ Error Types ============
@dataclass
class ApiError:
    """API error information"""
    code: str  # Error code identifier
    message: str
    status_code: int
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[RequestId] = None


# ============ Caching Types ============
CacheKey = str
CacheValue = Any
CacheFunction = Callable[..., CacheValue]


# ============ Async Types ============
class AsyncTask(Generic[T]):
    """Async task that resolves to type T"""
    
    def get_result(self) -> T: ...
    
    def is_complete(self) -> bool: ...
    
    def cancel(self) -> bool: ...


# ============ Configuration Types ============
@dataclass
class AppConfig:
    """Application configuration"""
    environment: Literal["development", "staging", "production"]
    debug: bool
    database_url: str
    redis_url: Optional[str]
    jwt_secret: str
    jwt_algorithm: str
    jwt_expiration_hours: int
    max_workers: int
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


# ============ Utility Functions ============
def get_type_alias_name(alias: Any) -> str:
    """Get human-readable name for type alias"""
    if hasattr(alias, '__name__'):
        return alias.__name__
    elif hasattr(alias, '__origin__'):
        return str(alias.__origin__)
    return str(alias)


def is_valid_email(email: str) -> bool:
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_score(score: Score) -> bool:
    """Validate qualification score is 0-100"""
    return isinstance(score, (int, float)) and 0 <= score <= 100


def parse_score_to_tier(score: Score) -> QualificationTier:
    """Convert score to qualification tier"""
    if score >= 80:
        return QualificationTier.EXCELLENT
    elif score >= 60:
        return QualificationTier.GOOD
    elif score >= 40:
        return QualificationTier.FAIR
    elif score >= 20:
        return QualificationTier.POOR
    else:
        return QualificationTier.REJECT
