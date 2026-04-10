from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, JSON, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum

Base = declarative_base()

# ============================================================================
# ENUMS
# ============================================================================

class SubscriptionTier(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    PROFESSIONAL = "professional"

class ReadingStatus(str, Enum):
    COMPLETED = "completed"
    PROCESSING = "processing"
    FAILED = "failed"

# ============================================================================
# USER MODEL
# ============================================================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    
    # Subscription
    subscription_tier = Column(String(50), default="free")
    subscription_active = Column(Boolean, default=False)
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    subscription_end_date = Column(DateTime, nullable=True)
    
    # Stats
    total_readings = Column(Integer, default=0)
    readings_this_month = Column(Integer, default=0)
    average_confidence = Column(Float, default=0.0)
    
    # Account
    is_active = Column(Boolean, default=True)
    is_email_verified = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    readings = relationship("PalmReading", back_populates="user")
    saved_readings = relationship("SavedReading", back_populates="user")
    
    # Indexes
    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_created', 'created_at'),
    )

# ============================================================================
# PALM READING MODEL
# ============================================================================

class PalmReading(Base):
    __tablename__ = "palm_readings"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    
    # Image
    image_hash = Column(String(64), unique=True, nullable=True, index=True)
    image_url = Column(String(500), nullable=True)
    
    # Reading data
    title = Column(String(255))
    overview = Column(Text)
    insights = Column(JSON, nullable=True)  # List of {category, description, significance}
    life_areas = Column(JSON, nullable=True)  # {health, career, relationships, etc}
    identified_features = Column(JSON, nullable=True)  # {palmLines, mounts, yogas}
    wisdom = Column(Text, nullable=True)
    
    # Quality metrics
    confidence_score = Column(Float, default=0.0)  # 0-1
    feature_count = Column(Integer, default=0)
    yoga_count = Column(Integer, default=0)
    
    # User interaction
    is_favorite = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # List of tags
    
    # Status
    status = Column(String(50), default="completed")
    analysis_duration = Column(Float, nullable=True)  # seconds
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="readings")
    
    # Indexes
    __table_args__ = (
        Index('idx_reading_user', 'user_id'),
        Index('idx_reading_created', 'created_at'),
        Index('idx_reading_hash', 'image_hash'),
    )

# ============================================================================
# SAVED READING MODEL (Bookmarks/Favorites)
# ============================================================================

class SavedReading(Base):
    __tablename__ = "saved_readings"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    reading_id = Column(String(36), ForeignKey("palm_readings.id"), nullable=False)
    
    # Metadata
    saved_title = Column(String(255), nullable=True)
    saved_notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="saved_readings")

# ============================================================================
# INTERPRETATION MODEL (Follow-up Questions/Insights)
# ============================================================================

class Interpretation(Base):
    __tablename__ = "interpretations"
    
    id = Column(String(36), primary_key=True)
    reading_id = Column(String(36), ForeignKey("palm_readings.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    # Question and response
    question = Column(Text)
    response = Column(Text)
    
    # Metadata
    feature_focused = Column(String(100), nullable=True)  # Which line/mount was focused on
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

# ============================================================================
# ANALYTICS MODEL
# ============================================================================

class ReadingAnalytics(Base):
    __tablename__ = "reading_analytics"
    
    id = Column(String(36), primary_key=True)
    reading_id = Column(String(36), ForeignKey("palm_readings.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    # Features detected
    life_line_detected = Column(Boolean, default=False)
    head_line_detected = Column(Boolean, default=False)
    heart_line_detected = Column(Boolean, default=False)
    fate_line_detected = Column(Boolean, default=False)
    sun_line_detected = Column(Boolean, default=False)
    mercury_line_detected = Column(Boolean, default=False)
    
    # Mounts
    jupiter_mount = Column(Boolean, default=False)
    saturn_mount = Column(Boolean, default=False)
    sun_mount = Column(Boolean, default=False)
    mercury_mount = Column(Boolean, default=False)
    moon_mount = Column(Boolean, default=False)
    venus_mount = Column(Boolean, default=False)
    mars_mount = Column(Boolean, default=False)
    
    # Yogas identified (store as JSON array of yoga names)
    yogas_identified = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

# ============================================================================
# API KEY MODEL
# ============================================================================

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    key_hash = Column(String(64), unique=True, nullable=False)
    key_name = Column(String(255))
    
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

# ============================================================================
# AUDIT LOG MODEL
# ============================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    # Action details
    action = Column(String(100))  # register, login, analyze, favorite, delete, etc
    resource = Column(String(100), nullable=True)  # reading, user, etc
    resource_id = Column(String(36), nullable=True)
    
    # Result
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # IP/User agent
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_action', 'action'),
        Index('idx_audit_created', 'created_at'),
    )

# ============================================================================
# SYSTEM CONFIG MODEL
# ============================================================================

class SystemConfig(Base):
    __tablename__ = "system_config"
    
    id = Column(String(36), primary_key=True)
    
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    
    description = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================================
# USER ANALYTICS MODEL
# ============================================================================

class UserAnalytics(Base):
    __tablename__ = "user_analytics"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    
    # Usage
    total_readings = Column(Integer, default=0)
    readings_this_month = Column(Integer, default=0)
    readings_this_week = Column(Integer, default=0)
    
    # Engagement
    favorite_count = Column(Integer, default=0)
    average_confidence_score = Column(Float, default=0.0)
    
    # Subscription
    paid_tier = Column(Boolean, default=False)
    subscription_duration_days = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_reading_at = Column(DateTime, nullable=True)