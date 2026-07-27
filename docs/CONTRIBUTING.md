# Contributing Guidelines

## Getting Started

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write/update tests
5. Submit a pull request

## Code Standards

### Python (Backend)
- Follow PEP 8 style guide
- Use type hints where possible
- Add docstrings to functions
- Write unit tests for new features

Example:
```python
def get_lead(lead_id: int) -> Lead:
    """
    Retrieve a lead by ID.
    
    Args:
        lead_id: The unique identifier of the lead
        
    Returns:
        Lead object or None if not found
    """
    return Lead.query.get(lead_id)
```

### JavaScript/React (Frontend)
- Use functional components
- Use hooks for state management
- Follow Airbnb style guide
- Add meaningful comments
- Use PropTypes or TypeScript

Example:
```javascript
function LeadCard({ lead, onSelect }) {
  return (
    <Card onClick={() => onSelect(lead)}>
      <h3>{lead.name}</h3>
      <p>{lead.email}</p>
    </Card>
  );
}

LeadCard.propTypes = {
  lead: PropTypes.object.isRequired,
  onSelect: PropTypes.func.isRequired,
};
```

## Commit Messages

Use clear, descriptive commit messages:
- `feat: Add lead filtering by status`
- `fix: Correct email validation regex`
- `docs: Update API documentation`
- `refactor: Simplify lead classification logic`
- `test: Add tests for lead creation`

## Testing

### Backend
```bash
pytest tests/
```

### Frontend
```bash
npm test
```

## Pull Request Process

1. Update documentation if needed
2. Add tests for new features
3. Ensure all tests pass
4. Request code review
5. Address review comments
6. Merge when approved

## Reporting Issues

Include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Screenshots if applicable
- Environment details (OS, versions, etc.)

## Code Review Guidelines

- Be respectful and constructive
- Focus on code quality and maintainability
- Suggest improvements with examples
- Approve changes that meet standards
