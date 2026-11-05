import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class Venue(Base, TimestampMixin):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    events: Mapped[List["Event"]] = relationship("Event", back_populates="venue")


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), index=True, default="Concert")
    event_date: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="SCHEDULED", index=True)  # SCHEDULED, CANCELLED, COMPLETED

    # Relationships
    venue: Mapped["Venue"] = relationship("Venue", back_populates="events")
    tiers: Mapped[List["SeatTier"]] = relationship("SeatTier", back_populates="event", cascade="all, delete-orphan")
    seats: Mapped[List["Seat"]] = relationship("Seat", back_populates="event", cascade="all, delete-orphan")
    bookings: Mapped[List["Booking"]] = relationship("Booking", back_populates="event")


class SeatTier(Base, TimestampMixin):
    __tablename__ = "seat_tiers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # VIP, Premium, Standard
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="tiers")
    seats: Mapped[List["Seat"]] = relationship("Seat", back_populates="tier")

