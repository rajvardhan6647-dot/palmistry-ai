# VRIHUD HASTREKHA - BACKEND ARCHITECTURE GUIDE

## OVERVIEW

The backend is built with **FastAPI**, a modern Python web framework that's production-ready and fast.

**Key Technologies:**
- FastAPI (web framework)
- SQLAlchemy (database ORM)
- PostgreSQL (production database)
- SQLite (development database)
- JWT (authentication)
- bcrypt (password hashing)
- Claude Vision API (AI analysis)
- Stripe (payment processing)

---

## PROJECT STRUCTURE

---

## MAIN FILES EXPLAINED

### main_enhanced.py

The main FastAPI application with all endpoints.

**Key Components:**

1. **Database Setup**
```python
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./palmistry.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
```

2. **CORS Configuration**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

3. **Authentication Endpoints**
- POST /auth/register - Create new user
- POST /auth/login - Authenticate user
- POST /auth/refresh - Refresh JWT token

4. **User Management**
- GET /users/me - Get current user profile
- PUT /users/me - Update profile
- POST /users/change-password - Change password

5. **Palm Analysis**
- POST /api/analyze-palm-auth - Analyze palm (authenticated)

6. **Reading Management**
- GET /readings - List user's readings
- GET /readings/{id} - Get specific reading
- POST /readings/{id}/favorite - Toggle favorite
- DELETE /readings/{id} - Delete reading

7. **Analytics**
- GET /stats - Get user statistics

8. **Health Check**
- GET /health - System health status

---

### models.py

SQLAlchemy database models defining the schema.

**Main Models:**

1. **User**
```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    subscription_tier = Column(String(50), default="free")
    total_readings = Column(Integer, default=0)
    readings_this_month = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
```

2. **PalmReading**
```python
class PalmReading(Base):
    __tablename__ = "palm_readings"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    image_hash = Column(String(64), unique=True)
    title = Column(String(255))
    overview = Column(String(2000))
    insights = Column(JSON)
    life_areas = Column(JSON)
    confidence_score = Column(Float)
    is_favorite = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

3. **SavedReading**
- User's bookmarked/pinned readings

4. **Interpretation**
- Follow-up questions about readings

5. **Analytics**
- Statistics per reading and per user

6. **APIKey**
- API keys for professional users

7. **AuditLog**
- Audit trail of all actions

---

### auth.py

Authentication and security logic.

**Key Functions:**

1. **Password Hashing**
```python
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

2. **JWT Token Generation**
```python
def create_access_token(user_id, email, username, subscription_tier):
    # Creates JWT access token (24 hour expiry)
    
def create_refresh_token(user_id, email, username, subscription_tier):
    # Creates refresh token (30 day expiry)
```

3. **Token Verification**
```python
def verify_access_token(token: str) -> Optional[TokenData]:
    # Verifies and decodes JWT token
    
def verify_refresh_token(token: str) -> Optional[TokenData]:
    # Verifies refresh token
```

4. **FastAPI Dependencies**
```python
async def get_current_user(credentials) -> TokenData:
    # Use in routes: 
    # @app.get("/api/endpoint")
    # async def protected_endpoint(current_user = Depends(get_current_user)):
```

---

### stripe_integration.py

Payment and subscription handling.

**Key Functions:**

1. **Customer Management**
```python
def get_or_create_stripe_customer(user_id, email, name) -> str:
    # Gets or creates Stripe customer
```

2. **Subscription Creation**
```python
def create_checkout_session(user_id, email, name, plan, return_url):
    # Creates Stripe checkout session
```

3. **Subscription Management**
```python
def retrieve_subscription(stripe_customer_id):
    # Gets current subscription
    
def cancel_subscription(stripe_customer_id, at_period_end=True):
    # Cancels subscription
    
def update_subscription_plan(stripe_customer_id, new_plan):
    # Upgrades/downgrades plan
```

4. **Webhook Handling**
```python
def process_webhook(payload, sig_header):
    # Handles Stripe webhooks
```

---

## DATABASE SCHEMA

### Users Table

---

## SECURITY IMPLEMENTATION

### Password Security
- Passwords hashed with bcrypt (never stored plain text)
- Minimum 8 characters, uppercase, lowercase, number, special char

### JWT Tokens
- Access tokens: 24 hour expiry
- Refresh tokens: 30 day expiry
- Tokens contain: user_id, email, username, subscription_tier

### CORS Protection
- Restricted to specific origins
- Credentials allowed only on same origin
- Methods restricted to GET, POST, PUT, DELETE

### Rate Limiting
- Framework ready (slowapi)
- Can limit per-user or globally
- Currently not enforced but configurable

### Audit Logging
- All actions logged (register, login, analyze, favorite, etc.)
- Includes timestamp, user_id, action, resource
- Useful for compliance and debugging

---

## PERFORMANCE CONSIDERATIONS

### Database Indexing
```python
# Automatically indexed (primary keys)
users.id
palm_readings.id

# Foreign keys (auto-indexed)
palm_readings.user_id

# Manual indexes recommended
users.email
users.username
palm_readings.created_at
```

### Caching Strategy
```python
# Image hash caching
@lru_cache(maxsize=1000)
def get_cached_analysis(image_hash):
    # Returns cached result if image was analyzed before
```

### Connection Pooling
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # Number of connections
    max_overflow=40,     # Extra connections if needed
    pool_recycle=3600    # Recycle connections hourly
)
```

---

## ERROR HANDLING

### HTTP Status Codes Used
- 200 OK - Successful request
- 201 Created - Resource created
- 400 Bad Request - Invalid input
- 401 Unauthorized - Not authenticated
- 403 Forbidden - No permission
- 404 Not Found - Resource not found
- 413 Payload Too Large - Image too large
- 500 Internal Server Error - Server error

### Error Response Format
```json
{
  "detail": "Error message describing what went wrong"
}
```

### Logging
```python
import logging
logger = logging.getLogger(__name__)

logger.info("User registered: {email}")
logger.error("Analysis failed: {error}")
logger.warning("High API usage detected")
```

---

## DEPLOYMENT

### Local Development
```bash
python main_enhanced.py
# Runs on http://localhost:8000
```

### Docker
```bash
docker build -t palmistry-api .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=... \
  -e SECRET_KEY=... \
  palmistry-api
```

### Heroku
```bash
git push heroku main
# Automatically builds and deploys
```

### AWS Elastic Beanstalk
```bash
eb deploy
# Deploys current version
```

---

## MONITORING

### Health Endpoint
```bash
GET /health
# Returns: { status: "healthy", service: "...", version: "..." }
```

### Logging
- All requests logged
- Errors logged with full traceback
- Database queries logged (in debug mode)

### Metrics to Monitor
- API response time (target: <2s)
- Error rate (target: <0.5%)
- Database connections
- API key usage
- User registration rate

---

## EXTENDING THE BACKEND

### Adding New Endpoint
```python
@app.post("/api/new-endpoint")
async def new_endpoint(
    request: RequestModel,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Your logic here
    return { "result": "..." }
```

### Adding New Database Model
```python
class NewModel(Base):
    __tablename__ = "new_models"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    # ... other fields
```

### Adding Validation
```python
class RequestModel(BaseModel):
    email: EmailStr
    password: str
    
    @validator('password')
    def password_strong(cls, v):
        if len(v) < 8:
            raise ValueError('Must be at least 8 characters')
        return v
```

---

## TROUBLESHOOTING

### Common Issues

**"No module named 'fastapi'"**
```bash
pip install -r requirements.txt
```

**"Connection refused" (database)**
```bash
# Start PostgreSQL
brew services start postgresql@15
# Or use SQLite (default)
```

**"CORS error"**
```python
# Update CORS_ORIGINS in .env
# Or hardcode in main_enhanced.py
```

**"401 Unauthorized"**
```python
# Check token is being sent in Authorization header
# Format: Authorization: Bearer {token}
```

---

**This backend handles everything your palmistry app needs!** 🔮