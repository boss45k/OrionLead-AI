# Project Setup & Documentation

## Quick Start Guide

### 1. Environment Setup

Copy the environment template and configure:
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
- Database credentials
- API keys (Facebook, LinkedIn, etc.)
- Email settings
- AI model paths

### 2. Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
python run.py
```

Backend will run on `http://localhost:5000`

### 3. Frontend Setup (React Web)

```bash
cd web
npm install
npm start
```

Web app will run on `http://localhost:3000`

### 4. Mobile Setup (React Native)

```bash
cd mobile
npm install
npm start
# Then press 'a' for Android or 'i' for iOS
```

### 5. Database Setup

```bash
mysql -u root -p < database/migrations/001_initial_schema.sql
mysql -u root -p ai_lead_db < database/seeds/sample_data.sql
```

## Project Structure

```
AI-Lead-Collection-System/
├── web/                    # React web application
│   ├── src/
│   │   ├── components/     # Reusable components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API services
│   │   ├── styles/         # CSS files
│   │   └── utils/          # Utility functions
│   ├── public/
│   └── package.json
├── mobile/                 # React Native mobile app
│   ├── src/
│   │   ├── screens/        # Screen components
│   │   ├── components/     # Reusable components
│   │   ├── services/       # API services
│   │   └── utils/          # Utility functions
│   └── package.json
├── backend/                # Python Flask API
│   ├── app/
│   │   ├── models/         # Database models
│   │   ├── routes/         # API routes
│   │   ├── services/       # Business logic
│   │   └── utils/          # Helper utilities
│   ├── config/             # Configuration files
│   ├── requirements.txt
│   └── run.py
├── database/               # MySQL setup
│   ├── migrations/         # Database schemas
│   ├── seeds/              # Sample data
│   └── README.md
├── docs/                   # Documentation
└── .env.example            # Environment template

```

## Key Features

### Web Dashboard (React)
- User authentication
- Lead management and filtering
- Real-time analytics and reporting
- Data visualization with charts
- Responsive design

### Mobile App (React Native)
- Cross-platform support
- Lead browsing and management
- Push notifications
- Offline capabilities
- Mobile-optimized UI

### Backend API (Python)
- RESTful API endpoints
- JWT authentication
- Database ORM with SQLAlchemy
- Web scraping capabilities
- AI-powered lead classification
- Comprehensive error handling

### Database (MySQL)
- Optimized schema with indexes
- Full-text search support
- Activity logging
- Data source tracking
- Classification system

## Technologies Used

- **Frontend**: React 18, React Router, Ant Design, Axios
- **Mobile**: React Native, React Navigation
- **Backend**: Flask, SQLAlchemy, JWT
- **Database**: MySQL, SQLAlchemy ORM
- **AI/ML**: scikit-learn, TensorFlow, NLTK
- **Web Scraping**: BeautifulSoup, Selenium
- **Additional**: Redis, Celery for background tasks

## Configuration Guide

### Database Configuration
Edit `.env`:
```
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/ai_lead_db
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=password
```

### API Configuration
```
API_PORT=5000
API_HOST=0.0.0.0
SECRET_KEY=your-secret-key
```

### Frontend Configuration
Web app connects to backend via:
```
REACT_APP_API_URL=http://localhost:5000
```

## Development Workflow

1. Create a feature branch
2. Make changes to relevant components
3. Test locally before committing
4. Push to repository
5. Create pull request for review

## Building for Production

### Web
```bash
cd web
npm run build
```

### Mobile
```bash
cd mobile
# Android
npx react-native run-android --variant=release

# iOS
npx react-native run-ios --configuration Release
```

### Backend
- Use production configuration in `.env`
- Set `FLASK_ENV=production`
- Use a production WSGI server like Gunicorn:
  ```bash
  gunicorn wsgi:app
  ```

## Troubleshooting

### Database Connection Issues
- Verify MySQL is running
- Check credentials in `.env`
- Ensure database is created

### API Connection Errors
- Backend must be running on port 5000
- Check API_URL in frontend `.env`
- Verify JWT token in localStorage

### React Native Issues
- Clear Android/iOS build cache
- Reinstall node_modules
- Check platform-specific requirements

## Support & Documentation

- API Documentation: [backend/README.md](backend/README.md)
- Database Setup: [database/README.md](database/README.md)
- Contributing: [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)

## License

MIT License - See LICENSE file for details
