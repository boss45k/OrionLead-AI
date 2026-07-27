# Type Hints Implementation Guide

## Overview

The OrionLead AI uses comprehensive type hints to improve code quality, enable IDE support, and catch errors early. Type hints document what types your functions expect and return.

## Benefits

✅ **IDE Support** - Autocomplete, inline documentation, error detection  
✅ **Static Analysis** - Use mypy to find type errors before runtime  
✅ **Documentation** - Types serve as inline documentation  
✅ **Refactoring** - Rename safely with fewer hidden errors  
✅ **Maintainability** - Easier to understand code intent  

## Basic Type Hints

### Function Arguments and Returns

```python
# Without type hints (unclear)
def get_lead(lead_id):
    # What type is lead_id?
    # What does this return?
    pass

# With type hints (clear)
from app.utils.types import LeadId, LeadData, Optional

def get_lead(lead_id: LeadId) -> Optional[LeadData]:
    """Get lead by ID"""
    pass
```

### Variables

```python
from typing import List, Dict
from app.utils.types import LeadData, Score

# Simple types
name: str = "John Doe"
age: int = 30
salary: float = 50000.0
is_active: bool = True

# Complex types
leads: List[LeadData] = []
scores_by_lead: Dict[int, Score] = {1: 85.5, 2: 72.0}
optional_email: Optional[str] = None
```

## Common Type Patterns

### Optional Values (Can Be None)

```python
from typing import Optional

def get_user_email(user_id: int) -> Optional[str]:
    """Returns email if found, None otherwise"""
    user = User.query.get(user_id)
    return user.email if user else None

# Usage
email = get_user_email(123)  # str or None
if email:
    send_email(email)  # Safe - known to be str here
```

### Lists and Collections

```python
from typing import List, Set, Dict, Tuple

# Simple list
def get_all_leads() -> List[LeadData]:
    pass

# Dictionary with typed keys and values
def score_mapping() -> Dict[int, float]:
    pass

# Tuple with fixed size and types
def get_coordinates() -> Tuple[float, float]:
    return (40.7128, -74.0060)

# Set of unique items
tags: Set[str] = {"python", "ai", "leads"}
```

### Union Types (Multiple Possible Types)

```python
from typing import Union

# Function can accept string or int
def find_lead(identifier: Union[str, int]) -> Optional[LeadData]:
    """Find lead by name or ID"""
    if isinstance(identifier, int):
        return LeadData.query.get(identifier)
    else:
        return LeadData.query.filter_by(name=identifier).first()

# Usage
find_lead(123)      # int - search by ID
find_lead("John")   # str - search by name
```

### Literal Types (Specific Values Only)

```python
from typing import Literal

Status = Literal["active", "inactive", "pending"]

def set_status(user_id: int, status: Status) -> bool:
    """Set user status to one of the allowed values"""
    if status not in ["active", "inactive", "pending"]:
        raise ValueError(f"Invalid status: {status}")
    # ...
    pass

# Usage
set_status(123, "active")      # ✓ Valid
set_status(123, "archived")    # ✗ Type error - not a valid status
```

## Pre-defined Types

The application provides custom type aliases for clarity:

```python
from app.utils.types import (
    UserId,              # int - User ID
    LeadId,              # int - Lead ID
    Score,               # float - Qualification score (0-100)
    Email,               # str - Email address
    Token,               # str - JWT token
    RequestId,           # str - Request identifier
    LeadStatus,          # Enum - "new" | "qualified" | "converted" | etc
    QualificationTier,   # Enum - "excellent" | "good" | "fair" | "poor" | "reject"
)

def qualify_lead(lead_id: LeadId, criteria: Optional[Dict]) -> Score:
    """Returns qualification score (0-100)"""
    pass

def authenticate(email: Email, password: str) -> Token:
    """Returns JWT token"""
    pass
```

## Data Classes

```python
from dataclasses import dataclass
from app.utils.types import LeadData, UserProfile

# Usage in functions
def create_user(email: str, name: str) -> UserProfile:
    """Create user and return profile"""
    pass

def get_lead_details(lead_id: int) -> Optional[LeadData]:
    """Get complete lead information"""
    user = Lead.query.get(lead_id)
    if not user:
        return None
    
    return LeadData(
        id=user.id,
        name=user.name,
        email=user.email,
        # ... other fields
    )
```

## Type Checking with mypy

### Installation

```bash
pip install mypy
```

### Configuration (.mypy.ini)

```ini
[mypy]
python_version = 3.9
warn_return_any = True
warn_unused_configs = True
ignore_missing_imports = True

[mypy-sqlalchemy.*]
ignore_errors = True

[mypy-celery.*]
ignore_errors = True
```

### Running Type Checks

```bash
# Check entire backend
mypy backend/

# Check specific file
mypy backend/app/routes/auth.py

# Check with detailed output
mypy backend/ --show-error-codes --show-error-context

# Generate report
mypy backend/ --html ./mypy-report
```

### Example Output

```
backend/app/routes/leads.py:45: error: Argument 1 to "get_lead" has incompatible type "str"; expected "LeadId" (which is "int")
backend/app/services/service.py:120: error: "LeadData" has no attribute "score" (only "qualification_score")
backend/app/models/models.py:78: error: Incompatible return value type (got "None", expected "str")
```

## Real-World Examples

### Example 1: Authentication Route

```python
from typing import Dict, Any
from flask import request, jsonify
from app.utils.types import Email, Token, UserProfile

def login() -> tuple[Dict[str, Any], int]:
    """
    Endpoint to authenticate user
    Returns: (response_dict, status_code)
    """
    json_data: Dict[str, Any] = request.get_json() or {}
    
    email: Email = json_data.get('email')
    password: str = json_data.get('password')
    
    # Validate input
    if not email or not password:
        return {'error': 'Email and password required'}, 400
    
    # Authenticate
    user: Optional[UserProfile] = authenticate_user(email, password)
    if not user:
        return {'error': 'Invalid credentials'}, 401
    
    # Generate token
    token: Token = create_jwt_token(user.id, user.email)
    
    return {
        'status': 'success',
        'token': token,
        'user': user.to_dict()
    }, 200
```

### Example 2: Lead Qualification

```python
from typing import List, Optional
from app.utils.types import LeadId, QualificationResult, QualificationCriteria

def qualify_lead(
    lead_id: LeadId,
    criteria: Optional[QualificationCriteria] = None
) -> QualificationResult:
    """Qualify single lead"""
    lead = Lead.query.get(lead_id)
    if not lead:
        raise NotFoundError("Lead", lead_id)
    
    # Run qualification
    score: float = run_ml_model(lead)
    result: QualificationResult = QualificationResult(
        lead_id=lead_id,
        score=score,
        qualified=score >= 70.0,
        # ... other fields
    )
    
    return result

def qualify_leads_batch(
    lead_ids: List[LeadId],
    criteria: Optional[QualificationCriteria] = None
) -> List[QualificationResult]:
    """Qualify multiple leads"""
    results: List[QualificationResult] = []
    
    for lead_id in lead_ids:
        try:
            result: QualificationResult = qualify_lead(lead_id, criteria)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to qualify lead {lead_id}: {str(e)}")
    
    return results
```

### Example 3: Database Query with Type Safety

```python
from typing import List, Optional, Dict, Any
from app.utils.types import LeadData, PaginatedResponse, LeadFilterOptions

def list_leads(
    page: int = 1,
    per_page: int = 20,
    filters: Optional[LeadFilterOptions] = None
) -> PaginatedResponse[LeadData]:
    """List leads with pagination and filtering"""
    
    query = Lead.query
    
    # Apply filters
    if filters:
        if filters.status:
            query = query.filter_by(status=filters.status)
        if filters.company:
            query = query.filter_by(company=filters.company)
        if filters.min_score:
            query = query.filter(Lead.qualification_score >= filters.min_score)
    
    # Get total count
    total: int = query.count()
    
    # Paginate
    leads: List[Lead] = query.paginate(page, per_page).items
    
    # Convert to data models
    lead_data: List[LeadData] = [
        LeadData(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            # ... map other fields
        )
        for lead in leads
    ]
    
    return PaginatedResponse(
        items=lead_data,
        pagination=PaginationInfo(
            page=page,
            per_page=per_page,
            total=total,
            pages=(total + per_page - 1) // per_page,
        ),
        total=total
    )
```

## Advanced Patterns

### Generic Types

```python
from typing import TypeVar, Generic, List

T = TypeVar('T')  # Generic type variable

class Repository(Generic[T]):
    """Generic repository for any model"""
    
    def get(self, item_id: int) -> Optional[T]:
        pass
    
    def list(self) -> List[T]:
        pass

# Usage
class LeadRepository(Repository[LeadData]):
    def get(self, item_id: int) -> Optional[LeadData]:
        pass
```

### Callable Types

```python
from typing import Callable

# Function that takes a Lead and returns a Score
ScoreFunction = Callable[[Lead], float]

def run_scoring(leads: List[Lead], scorer: ScoreFunction) -> List[float]:
    """Apply scoring function to leads"""
    return [scorer(lead) for lead in leads]

# Usage
def my_scorer(lead: Lead) -> float:
    return lead.qualification_score

scores = run_scoring(my_leads, my_scorer)
```

### Protocol Types (Structural Typing)

```python
from typing import Protocol

class SerializableModel(Protocol):
    """Any object that can be serialized to dict"""
    
    def to_dict(self) -> Dict[str, Any]: ...
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SerializableModel': ...

# Any class implementing these methods satisfies the protocol
def save_model(model: SerializableModel) -> None:
    data: Dict[str, Any] = model.to_dict()
    # Save to database
```

## Common Mistakes & Fixes

### ❌ Missing Return Type
```python
def get_user(user_id):  # Type checker doesn't know what this returns
    return User.query.get(user_id)
```

### ✅ Add Return Type
```python
def get_user(user_id: int) -> Optional[UserProfile]:
    return User.query.get(user_id)
```

---

### ❌ Too Generic
```python
def process_data(data):  # What type is data?
    return do_something(data)
```

### ✅ Be Specific
```python
def process_lead(lead: LeadData) -> QualificationResult:
    return calculate_score(lead)
```

---

### ❌ Using `Any` Too Much
```python
def handle_response(response: Any) -> Any:  # Defeats type checking
    pass
```

### ✅ Use Appropriate Types
```python
def handle_response(response: Dict[str, Any]) -> ApiResponse:
    pass
```

## Type Hints Checklist

- [ ] All function arguments have type hints
- [ ] All function returns have type hints
- [ ] Class variables have type hints
- [ ] Optional fields use `Optional[T]` or `T | None`
- [ ] Collections specify item types: `List[T]`, `Dict[K, V]`
- [ ] Enumerations use defined Literal or Enum types
- [ ] Complex types use provided data classes
- [ ] mypy passes with no errors/warnings
- [ ] Type hints serve as inline documentation

## Further Reading

- [PEP 484 - Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [Python typing Module](https://docs.python.org/3/library/typing.html)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [Type Hints Best Practices](https://github.com/RomeiLy/pytype-hints-cheatsheet)
