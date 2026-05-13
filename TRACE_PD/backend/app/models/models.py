import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Float,
    Text, DateTime, ForeignKey, BigInteger, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.session import Base


class User(Base):
    __tablename__ = "users"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email      = Column(String, unique=True, nullable=False)
    username   = Column(String, nullable=False)
    hashed_pw  = Column(String, nullable=False)
    timezone   = Column(String, default="UTC")
    consent    = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    logs          = relationship("Log",         back_populates="user", cascade="all, delete")
    loops         = relationship("Loop",        back_populates="user", cascade="all, delete")
    fixes         = relationship("Fix",         back_populates="user", cascade="all, delete")
    breakpoints   = relationship("Breakpoint",  back_populates="user", cascade="all, delete")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete")


class Log(Base):
    __tablename__ = "logs"
    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id       = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    timestamp     = Column(DateTime, nullable=False, default=datetime.utcnow)
    activity_type = Column(String, nullable=False)
    duration      = Column(Integer, nullable=False)
    mood          = Column(Integer)
    focus_score   = Column(Integer)
    notes         = Column(Text)
    details       = Column(JSON, default=dict)
    created_at    = Column(DateTime, default=datetime.utcnow)
    user          = relationship("User", back_populates="logs")


class Loop(Base):
    __tablename__ = "loops"
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    trigger_desc    = Column(Text, nullable=False)
    trigger_time    = Column(String)
    action_desc     = Column(Text, nullable=False)
    outcome_desc    = Column(Text, nullable=False)
    confidence      = Column(Float, default=0.0)
    occurrences     = Column(Integer, default=1)
    status          = Column(String, default="active")
    causal_estimate = Column(Text)
    detected_at     = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user  = relationship("User", back_populates="loops")
    fixes = relationship("Fix",  back_populates="loop", cascade="all, delete")


class Fix(Base):
    __tablename__ = "fixes"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    loop_id    = Column(Integer, ForeignKey("loops.id", ondelete="CASCADE"))
    suggestion = Column(Text, nullable=False)
    effort     = Column(String, default="Medium")
    impact     = Column(String, default="Medium")
    applied    = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="fixes")
    loop = relationship("Loop", back_populates="fixes")


class Breakpoint(Base):
    __tablename__ = "breakpoints"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name           = Column(String, nullable=False)
    condition_type = Column(String, nullable=False)
    threshold      = Column(Float, nullable=False)
    action_msg     = Column(Text)
    active         = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="breakpoints")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    role        = Column(String, nullable=False)
    content     = Column(Text, nullable=False)
    tokens_used = Column(Integer, default=0)
    model_used  = Column(String)
    created_at  = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="chat_messages")
