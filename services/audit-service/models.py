import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKeyConstraint
from sqlalchemy.orm import relationship
from session import Base

class Audit(Base):
    __tablename__ = "audits"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    input_type = Column(String(50), nullable=False)
    input_content = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    score_a = Column(Integer, default=0)
    score_aa = Column(Integer, default=0)
    score_aaa = Column(Integer, default=0)
    score_total = Column(Integer, default=0)
    created_at = Column(DateTime, primary_key=True, default=datetime.utcnow)
    violations = relationship(
        "AuditViolation",
        back_populates="audit",
        cascade="all, delete-orphan",
        primaryjoin="and_(AuditViolation.audit_id == Audit.id, AuditViolation.created_at == Audit.created_at)"
    )

class AuditViolation(Base):
    __tablename__ = "audit_violations"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_id = Column(String(36), nullable=False)
    criterion_id = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    level = Column(String(10), nullable=False)
    issue = Column(Text, nullable=False)
    element = Column(Text, nullable=True)
    fix = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, primary_key=True, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["audit_id", "created_at"],
            ["audits.id", "audits.created_at"],
            ondelete="CASCADE"
        ),
    )

    audit = relationship(
        "Audit",
        back_populates="violations",
        primaryjoin="and_(AuditViolation.audit_id == Audit.id, AuditViolation.created_at == Audit.created_at)"
    )
