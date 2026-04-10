# Vrihud Hastrekha - Complete Production Deployment Guide

## Overview

This guide covers deploying your complete palmistry application stack:
- **Frontend**: React/Next.js 
- **Backend**: FastAPI with PostgreSQL
- **Authentication**: JWT tokens
- **Database**: User accounts, readings history
- **Storage**: Image handling and caching

---

## PRE-DEPLOYMENT CHECKLIST

- [ ] All environment variables configured
- [ ] Secret key changed from default
- [ ] API keys stored securely
- [ ] Database backups configured
- [ ] SSL/HTTPS certificates ready
- [ ] Monitoring and logging setup
- [ ] Rate limiting configured
- [ ] CORS origins specified

---

## DEPLOYMENT OPTIONS

### Option 1: Heroku (Easiest for Beginners)

#### 1. Setup Heroku CLI
```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Login to Heroku
heroku login
```

#### 2. Create Heroku Apps
```bash
# Backend app
heroku create your-app-backend

# Frontend app (alternative: use Vercel instead)
heroku create your-app-frontend
```

#### 3. Add PostgreSQL Database
```bash
# Add free PostgreSQL tier
heroku addons:create heroku-postgresql:hobby-dev --app=your-app-backend
```

#### 4. Configure Environment Variables
```bash
heroku config:set \
  ANTHROPIC_API_KEY=sk-ant-... \
  SECRET_KEY=your-random-secret-key \
  CORS_ORIGINS=https://your-app-frontend.herokuapp.com \
  --app=your-app-backend
```

#### 5. Deploy Backend
```bash
# Add git remote
heroku git:remote -a your-app-backend

# Create Procfile for backend
echo "web: uvicorn main:app --host 0.0.0.0 --port \$PORT" > Procfile

# Deploy
git add Procfile requirements.txt main_enhanced.py models.py auth.py vision_ai_system_prompt.txt
git commit -m "Deploy to Heroku"
git push heroku main
```

#### 6. View Logs
```bash
heroku logs --tail --app=your-app-backend
```

#### 7. Deploy Frontend
```bash
# Build Next.js
npm run build

# Deploy to Heroku or Vercel
# For Vercel (simpler):
npm install -g vercel
vercel --prod
# Set NEXT_PUBLIC_API_URL to your Heroku backend URL
```

---

### Option 2: Railway (Modern & Affordable)

#### 1. Install Railway CLI
```bash
# macOS
brew install railway

# Linux/Windows
npm install -g @railway/cli
```

#### 2. Setup Project
```bash
# Login to Railway
railway login

# Initialize project
railway init

# Create backend service
railway add
# Select "PostgreSQL" for database
# Select "Python" for backend
```

#### 3. Configure Environment
```bash
railway variables

# Set variables:
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=your-secret-key
CORS_ORIGINS=https://your-frontend-domain.com
```

#### 4. Deploy
```bash
railway up

# Get deployment URL
railway open
```

#### 5. Frontend Deployment
```bash
# Deploy frontend to Vercel
vercel --prod
```

---

### Option 3: AWS (Scalable, Full Control)

#### Backend: Elastic Beanstalk

```bash
# Install EB CLI
pip install awsebcli

# Initialize application
eb init -p python-3.11 palmistry-api --region us-east-1

# Create environment
eb create palmistry-env

# Set environment variables
eb setenv \
  ANTHROPIC_API_KEY=sk-ant-... \
  SECRET_KEY=your-secret-key \
  DATABASE_URL=postgresql://... 

# Deploy
eb deploy

# Check status
eb status

# View logs
eb logs --all
```

#### Database: RDS PostgreSQL

```bash
# Create RDS instance via AWS Console
# Then set DATABASE_URL environment variable:
eb setenv DATABASE_URL=postgresql://username:password@database.xxxxx.us-east-1.rds.amazonaws.com:5432/palmistry
```

#### Frontend: CloudFront + S3

```bash
# Build Next.js
npm run build && npm run export

# Upload to S3
aws s3 sync out/ s3://your-bucket-name/

# CloudFront will serve from S3
# Set API endpoint in frontend environment
```

---

### Option 4: Docker Swarm / Kubernetes (Advanced)

#### Deploy with Docker Compose

```bash
# Build image
docker build -t your-registry/palmistry-api:latest .

# Push to Docker Hub / Private Registry
docker tag palmistry-api your-registry/palmistry-api:latest
docker push your-registry/palmistry-api:latest

# Deploy with Docker Compose
docker-compose -f docker-compose.yml up -d
```

#### Kubernetes Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: palmistry-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: palmistry-api
  template:
    metadata:
      labels:
        app: palmistry-api
    spec:
      containers:
      - name: palmistry-api
        image: your-registry/palmistry-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: palmistry-secrets
              key: api-key
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: palmistry-secrets
              key: database-url
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

```bash
# Deploy
kubectl apply -f deployment.yaml

# Scale
kubectl scale deployment palmistry-api --replicas=5
```

---

## PRODUCTION BEST PRACTICES

### 1. Security

```python
# In main_enhanced.py, add:

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/analyze-palm-auth")
@limiter.limit("10/minute")
async def analyze_palm_authenticated(...):
    ...
```

### 2. Database Connection Pooling

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # Verify connections before use
    echo=False
)
```

### 3. Monitoring with Sentry

```bash
pip install sentry-sdk

# In main_enhanced.py:
import sentry_sdk

sentry_sdk.init(
    dsn="your-sentry-dsn",
    traces_sample_rate=0.1,
    environment="production"
)
```

### 4. Logging

```python
import logging
from pythonjsonlogger import jsonlogger

# JSON structured logging for better parsing
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### 5. Image Caching

```python
# Cache analysis results
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def get_cached_analysis(image_hash: str):
    # Return from cache if exists
    return db.query(PalmReading).filter(
        PalmReading.image_hash == image_hash
    ).first()
```

### 6. Database Migrations

```bash
# Use Alembic for schema changes
alembic init migrations

# Create migration
alembic revision --autogenerate -m "Add user subscription"

# Apply migration
alembic upgrade head
```

### 7. Backup Strategy

```bash
# PostgreSQL backup
pg_dump -U palmistry_user palmistry > backup.sql

# Automated daily backups
0 2 * * * pg_dump -U palmistry_user palmistry | gzip > /backups/palmistry_$(date +\%Y\%m\%d).sql.gz
```

### 8. SSL/HTTPS Certificates

```bash
# Using Let's Encrypt with Certbot
sudo certbot certonly --standalone -d yourdomain.com

# Auto-renew
sudo certbot renew --quiet --no-lic-agree
```

---

## ENVIRONMENT VARIABLES TEMPLATE

Create `.env.production`:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/palmistry

# API Keys
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx
SECRET_KEY=generate-a-random-string-minimum-32-characters-long

# Server
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000

# CORS
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# API Limits
MAX_IMAGE_SIZE=10485760

# Email (for verification)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Stripe (for payments)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...

# Monitoring
SENTRY_DSN=https://...@sentry.io/...
LOG_LEVEL=info
```

---

## SCALING CONSIDERATIONS

### Database Scaling
```sql
-- Add indexes for frequently queried columns
CREATE INDEX idx_user_email ON users(email);
CREATE INDEX idx_reading_user ON palm_readings(user_id);
CREATE INDEX idx_reading_created ON palm_readings(created_at);

-- Archive old readings
DELETE FROM palm_readings 
WHERE created_at < NOW() - INTERVAL '1 year'
  AND is_favorite = false;
```

### API Scaling
```bash
# Use gunicorn with multiple workers
gunicorn --workers 8 --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 60 \
  main:app
```

### Caching Layer
```python
# Add Redis for caching
import redis
from functools import wraps
import json

cache = redis.Redis(host='redis-host', port=6379, db=0)

def cache_result(ttl=3600):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            cached = cache.get(cache_key)
            if cached:
                return json.loads(cached)
            result = await func(*args, **kwargs)
            cache.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator
```

---

## MONITORING & ALERTS

### Key Metrics to Monitor
- API response time (target: <2s)
- Error rate (target: <0.1%)
- Database connection pool usage
- API key rate limit violations
- Active users
- Cost per analysis (track Anthropic API usage)

### Set Up Alerts
```bash
# Create CloudWatch alarms (AWS)
aws cloudwatch put-metric-alarm \
  --alarm-name palmistry-api-errors \
  --alarm-description "Alert when error rate > 1%" \
  --metric-name ErrorRate \
  --namespace FastAPI \
  --statistic Average \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold
```

---

## ROLLBACK PROCEDURE

```bash
# Heroku rollback
heroku releases --app=your-app-backend
heroku rollback v123 --app=your-app-backend

# Docker rollback
docker pull your-registry/palmistry-api:previous-tag
docker-compose -f docker-compose.yml down
docker-compose -f docker-compose.yml up -d

# Kubernetes rollback
kubectl rollout history deployment palmistry-api
kubectl rollout undo deployment palmistry-api --to-revision=2
```

---

## TRAFFIC ESTIMATION & COSTS

### Anthropic API Costs
- Estimated: $0.015 per analysis (vision + text)
- 1,000 users × 2 readings/month = $30/month
- 10,000 users × 2 readings/month = $300/month

### Hosting Costs (Backend)
- Heroku: $7/month (free tier) → $50-500/month
- Railway: $5/month → $100-500/month
- AWS: $0.50-10/day depending on traffic

### Database Costs
- PostgreSQL (Heroku): Free → $50+/month
- AWS RDS: $15-100+/month

### Frontend Hosting
- Vercel: Free tier available
- Netlify: Free tier available

### Estimate for Moderate Usage
- Backend: $50-200/month
- Database: $20-50/month
- API: $100-300/month
- Frontend: Free or $20-50/month
- **Total: ~$170-600/month**

---

## SUPPORT & TROUBLESHOOTING

### Common Issues

**"Image too large" errors**
```python
# Increase size limit
MAX_IMAGE_SIZE = 20485760  # 20MB instead of 10MB
```

**Database connection timeout**
```python
# Increase pool timeout
engine = create_engine(
    DATABASE_URL,
    pool_recycle=3600,  # Recycle connections every hour
    connect_args={'connect_timeout': 10}
)
```

**High API latency**
- Add Redis caching layer
- Optimize database queries
- Increase worker processes
- Consider edge caching (CloudFront, CloudFlare)

---

## GO LIVE CHECKLIST

- [ ] Domain registered and configured
- [ ] SSL certificate installed
- [ ] Database backups enabled
- [ ] Monitoring and logging active
- [ ] Rate limiting configured
- [ ] Error tracking (Sentry) setup
- [ ] Email notifications working
- [ ] Support email configured
- [ ] Privacy policy and terms published
- [ ] Analytics tracking (optional)
- [ ] CDN configured for static assets
- [ ] API documentation updated
- [ ] Team trained on operations
- [ ] Incident response plan documented
- [ ] Launch announcement prepared

---

**Congratulations! Your palmistry application is ready for the world.** 🔮✨
