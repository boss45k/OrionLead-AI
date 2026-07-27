# API Documentation

## Base URL
```
http://localhost:5000/api
```

## Authentication

All endpoints except `/auth/register` and `/auth/login` require JWT authentication.

Include the token in the Authorization header:
```
Authorization: Bearer {token}
```

## Endpoints

### Authentication

#### Register User
```
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "John Doe",
  "company": "Tech Corp"
}

Response (201):
{
  "message": "User registered successfully",
  "user": {
    "id": 1,
    "email": "user@example.com"
  }
}
```

#### Login
```
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}

Response (200):
{
  "message": "Login successful",
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

#### Get Profile
```
GET /auth/profile
Authorization: Bearer {token}

Response (200):
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe",
    "company": "Tech Corp",
    "role": "user"
  }
}
```

### Leads

#### Get All Leads
```
GET /leads?page=1&per_page=20&status=qualified
Authorization: Bearer {token}

Response (200):
{
  "leads": [
    {
      "id": 1,
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "+1-555-0101",
      "company": "Tech Corp",
      "interests": ["electronics"],
      "score": 95,
      "status": "qualified",
      "source": "website",
      "created_at": "2026-03-28T10:30:00"
    }
  ],
  "total": 100,
  "pages": 5,
  "current_page": 1
}
```

#### Get Single Lead
```
GET /leads/1
Authorization: Bearer {token}

Response (200):
{
  "lead": {
    "id": 1,
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1-555-0101",
    "company": "Tech Corp",
    "position": "CTO",
    "interests": ["electronics", "smart devices"],
    "score": 95,
    "status": "qualified",
    "source": "website",
    "notes": "High-value lead",
    "created_at": "2026-03-28T10:30:00",
    "updated_at": "2026-03-28T10:30:00"
  }
}
```

#### Create Lead
```
POST /leads
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Jane Smith",
  "email": "jane@example.com",
  "phone": "+1-555-0102",
  "company": "Design Studio",
  "position": "Creative Director",
  "interests": ["electronics", "laptop"],
  "source": "website",
  "status": "pending"
}

Response (201):
{
  "message": "Lead created successfully",
  "lead": {
    "id": 2
  }
}
```

#### Update Lead
```
PUT /leads/1
Authorization: Bearer {token}
Content-Type: application/json

{
  "status": "qualified",
  "qualification_score": 92,
  "notes": "Updated information"
}

Response (200):
{
  "message": "Lead updated successfully"
}
```

#### Delete Lead
```
DELETE /leads/1
Authorization: Bearer {token}

Response (200):
{
  "message": "Lead deleted successfully"
}
```

#### Search Leads
```
GET /leads/search?q=john
Authorization: Bearer {token}

Response (200):
{
  "leads": [
    {
      "id": 1,
      "name": "John Doe",
      "email": "john@example.com",
      "company": "Tech Corp"
    }
  ]
}
```

## Error Responses

### 400 Bad Request
```json
{
  "message": "Invalid request data"
}
```

### 401 Unauthorized
```json
{
  "message": "Invalid credentials" / "Token is missing" / "Token is expired"
}
```

### 404 Not Found
```json
{
  "message": "Lead not found"
}
```

### 409 Conflict
```json
{
  "message": "User already exists"
}
```

### 500 Internal Server Error
```json
{
  "message": "Internal server error"
}
```

## Status Codes

- `200`: OK
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `404`: Not Found
- `409`: Conflict
- `500`: Internal Server Error

## Rate Limiting

API rate limits: 1000 requests per hour per user

Headers in response:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1648458000
```

## Pagination

Use `page` and `per_page` query parameters:
- Default page size: 20
- Max page size: 100
- Pages start from 1
