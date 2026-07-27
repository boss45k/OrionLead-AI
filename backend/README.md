# Backend API Documentation

## Endpoints

### Authentication

#### Register
- **POST** `/api/auth/register`
- Body: `{ "email": "user@example.com", "password": "password", "full_name": "John Doe", "company": "Company" }`

#### Login
- **POST** `/api/auth/login`
- Body: `{ "email": "user@example.com", "password": "password" }`
- Returns: JWT token

#### Get Profile
- **GET** `/api/auth/profile`
- Headers: `Authorization: Bearer {token}`

### Leads

#### Get All Leads
- **GET** `/api/leads?page=1&per_page=20&status=qualified`
- Headers: `Authorization: Bearer {token}`

#### Get Single Lead
- **GET** `/api/leads/{id}`
- Headers: `Authorization: Bearer {token}`

#### Create Lead
- **POST** `/api/leads`
- Headers: `Authorization: Bearer {token}`
- Body: Lead data

#### Update Lead
- **PUT** `/api/leads/{id}`
- Headers: `Authorization: Bearer {token}`
- Body: Updated lead data

#### Delete Lead
- **DELETE** `/api/leads/{id}`
- Headers: `Authorization: Bearer {token}`

#### Search Leads
- **GET** `/api/leads/search?q=search_term`
- Headers: `Authorization: Bearer {token}`

## Response Format

Success responses:
```json
{
  "message": "Operation successful",
  "data": {}
}
```

Error responses:
```json
{
  "message": "Error description"
}
```
