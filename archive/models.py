"""
Archive database models — mirror of historical operational tables.
SQLite: separate lemaison_archive.db file.
PostgreSQL/Neon: `archive` schema on the same database (no second DB required).
"""

import os
from dotenv import load_dotenv

from config import Config

_USE_ARCHIVE_SCHEMA = getattr(Config, "ARCHIVE_USE_SCHEMA", False)
_ARCHIVE_TABLE_ARGS = {"schema": "archive"} if _USE_ARCHIVE_SCHEMA else {}

from models import db
from utils import get_ph_time


class ArchiveRun(db.Model):
    """Log of each archive job execution."""
    __bind_key__ = "archive"
    __tablename__ = "archive_run"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=get_ph_time, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="RUNNING")
    triggered_by = db.Column(db.String(50), default="manual")
    user_id = db.Column(db.Integer, nullable=True)
    summary_json = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)


class ArchiveOrder(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_order"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time, index=True)
    order_code = db.Column(db.String(50), nullable=True, index=True)
    user_id = db.Column(db.Integer, nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)
    branch = db.Column(db.String(50), nullable=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    payment_status = db.Column(db.String(20), nullable=True)
    dining_option = db.Column(db.String(20), nullable=True)
    payment_method = db.Column(db.String(20), nullable=True)
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)
    change_amount = db.Column(db.Numeric(10, 2), nullable=True)
    table_number = db.Column(db.Integer, nullable=True)
    table_status = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    delivery_address = db.Column(db.Text, nullable=True)
    delivery_status = db.Column(db.String(20), nullable=True)
    rider_id = db.Column(db.Integer, nullable=True)
    delivery_fee = db.Column(db.Numeric(10, 2), nullable=True)
    proof_of_delivery_url = db.Column(db.String(255), nullable=True)
    xendit_invoice_id = db.Column(db.String(255), nullable=True)
    xendit_invoice_url = db.Column(db.String(255), nullable=True)
    prep_start_at = db.Column(db.DateTime, nullable=True)
    prep_end_at = db.Column(db.DateTime, nullable=True)
    prep_duration = db.Column(db.Integer, nullable=True)
    estimated_cost = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, index=True)
    processed_by_id = db.Column(db.Integer, nullable=True)
    reservation_id = db.Column(db.Integer, nullable=True)


class ArchiveOrderItem(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_order_item"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    order_original_id = db.Column(db.Integer, nullable=False, index=True)
    menu_item_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_time = db.Column(db.Numeric(10, 2), nullable=False)
    cost_at_time = db.Column(db.Numeric(10, 2), nullable=True)


class ArchiveOrderChat(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_order_chat"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    order_original_id = db.Column(db.Integer, nullable=False, index=True)
    sender_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=True)


class ArchiveReview(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_review"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    user_id = db.Column(db.Integer, nullable=False)
    order_original_id = db.Column(db.Integer, nullable=True, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    photo_url = db.Column(db.String(500), nullable=True)
    is_featured_in_gallery = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True)


class ArchiveReservation(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_reservation"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    reservation_code = db.Column(db.String(50), nullable=True)
    user_id = db.Column(db.Integer, nullable=False)
    branch = db.Column(db.String(50), nullable=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    guest_count = db.Column(db.Integer, nullable=False)
    occasion = db.Column(db.String(50), nullable=True)
    booking_type = db.Column(db.String(20), nullable=False)
    duration = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False)
    table_number = db.Column(db.String(20), nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, index=True)


class ArchiveAuditLog(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_audit_log"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, index=True)


class ArchiveInventoryLog(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_inventory_log"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    ingredient_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    previous_stock = db.Column(db.Numeric(10, 2), nullable=False)
    new_stock = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, index=True)


class ArchiveNotification(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_notification"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    user_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), nullable=True)
    link = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=True, index=True)


class ArchivePermissionAuditLog(db.Model):
    __bind_key__ = "archive"
    __tablename__ = "archive_permission_audit_log"
    __table_args__ = _ARCHIVE_TABLE_ARGS

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    archived_at = db.Column(db.DateTime, default=get_ph_time)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(50), nullable=False)
    permission_name = db.Column(db.String(100), nullable=True)
    route = db.Column(db.String(255), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, index=True)


ARCHIVE_MODELS = [
    ArchiveRun,
    ArchiveOrder,
    ArchiveOrderItem,
    ArchiveOrderChat,
    ArchiveReview,
    ArchiveReservation,
    ArchiveAuditLog,
    ArchiveInventoryLog,
    ArchiveNotification,
    ArchivePermissionAuditLog,
]


def ensure_archive_tables(app):
    """Create archive storage (schema + tables) if missing."""
    from sqlalchemy import text

    with app.app_context():
        if app.config.get("ARCHIVE_USE_SCHEMA"):
            db.session.execute(text("CREATE SCHEMA IF NOT EXISTS archive"))
            db.session.commit()
        try:
            db.create_all(bind_key="archive")
            print("--- Archive storage ready ---")
        except Exception as e:
            db.session.rollback()
            print(f"--- Archive tables note: {e} ---")
