import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    audits = relationship(
        "Audit", back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Audit(Base):
    __tablename__ = "audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    input_type = Column(String(50), nullable=False)  # "code" or "url"
    input_content = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    score_a = Column(Integer, default=0)
    score_aa = Column(Integer, default=0)
    score_aaa = Column(Integer, default=0)
    score_total = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audits")
    violations = relationship(
        "AuditViolation", back_populates="audit", cascade="all, delete-orphan"
    )


class AuditViolation(Base):
    __tablename__ = "audit_violations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_id = Column(String(36), ForeignKey("audits.id", ondelete="CASCADE"), nullable=False)
    criterion_id = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    level = Column(String(10), nullable=False)
    issue = Column(Text, nullable=False)
    element = Column(Text, nullable=True)
    fix = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)

    audit = relationship("Audit", back_populates="violations")
