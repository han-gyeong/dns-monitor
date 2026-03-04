from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class MonitoredDomain(Base):
    __tablename__ = "monitored_domain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    check_interval_sec: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    snapshots = relationship("DNSSnapshot", back_populates="domain", cascade="all, delete-orphan")
    events = relationship("ChangeEvent", back_populates="domain", cascade="all, delete-orphan")


class DNSSnapshot(Base):
    __tablename__ = "dns_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("monitored_domain.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    domain = relationship("MonitoredDomain", back_populates="snapshots")
    mx_records = relationship("MXRecord", back_populates="snapshot", cascade="all, delete-orphan")
    mx_a_records = relationship("MXARecord", back_populates="snapshot", cascade="all, delete-orphan")


class MXRecord(Base):
    __tablename__ = "mx_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("dns_snapshot.id"), index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    exchange: Mapped[str] = mapped_column(String(255), nullable=False)

    snapshot = relationship("DNSSnapshot", back_populates="mx_records")


class MXARecord(Base):
    __tablename__ = "mx_a_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("dns_snapshot.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(255), nullable=False)
    ipv4: Mapped[str] = mapped_column(String(45), nullable=False)

    snapshot = relationship("DNSSnapshot", back_populates="mx_a_records")


class ChangeEvent(Base):
    __tablename__ = "change_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("monitored_domain.id"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)

    domain = relationship("MonitoredDomain", back_populates="events")
    notifications = relationship("NotificationLog", back_populates="event", cascade="all, delete-orphan")


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("change_event.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30), default="email")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    event = relationship("ChangeEvent", back_populates="notifications")
