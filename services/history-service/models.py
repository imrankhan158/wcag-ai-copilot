import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase


class AuditBase(DeclarativeBase):
    pass


class ConversationBase(DeclarativeBase):
    pass


class Audit(AuditBase):
    __tablename__ = "audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    input_type = Column(String(50), nullable=False)  # "code" or "url"
    input_content = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    score_a = Column(Integer, default=0)
    score_aa = Column(Integer, default=0)
    score_aaa = Column(Integer, default=0)
    score_total = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    violations = relationship(
        "AuditViolation", back_populates="audit", cascade="all, delete-orphan"
    )


class AuditViolation(AuditBase):
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


class Conversation(ConversationBase):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(ConversationBase):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(50), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
