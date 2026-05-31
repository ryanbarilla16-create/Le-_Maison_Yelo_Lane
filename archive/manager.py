"""
Archive manager — moves eligible old records from main DB to archive DB.
"""

import json
import os
from datetime import timedelta

from models import (
    db,
    Order,
    OrderItem,
    OrderChat,
    Review,
    Reservation,
    AuditLog,
    InventoryLog,
    Notification,
    PermissionAuditLog,
)
from archive.models import (
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
)
from utils import get_ph_time


DEFAULT_CONFIG = {
    'retention_days': {
        'orders': 180,
        'reservations': 365,
        'audit_logs': 90,
        'inventory_logs': 90,
        'notifications': 60,
        'permission_audit_logs': 90,
    },
    'eligible_order_statuses': ['COMPLETED', 'CANCELLED'],
    'eligible_reservation_statuses': ['COMPLETED', 'REJECTED', 'CANCELLED'],
    'batch_size': 200,
}


class ArchiveManager:
    def __init__(self, config_path='archive/config.json'):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return DEFAULT_CONFIG.copy()
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update({k: v for k, v in data.items() if k != 'retention_days'})
        merged['retention_days'] = {**DEFAULT_CONFIG['retention_days'], **data.get('retention_days', {})}
        return merged

    def reload_config(self):
        self.config = self._load_config()

    def _cutoff(self, key):
        days = int(self.config['retention_days'].get(key, 90))
        return get_ph_time() - timedelta(days=days)

    def get_stats(self):
        """Compare main DB vs archive DB record counts."""
        from sqlalchemy.exc import OperationalError
        
        # Helper to safely execute queries with retry logic
        def safe_query(query_fn, default=0, max_retries=3):
            for attempt in range(max_retries):
                try:
                    return query_fn()
                except OperationalError as e:
                    db.session.rollback()
                    if attempt < max_retries - 1:
                        # Reconnect and retry
                        db.session.remove()
                        continue
                    else:
                        print(f"Query failed after {max_retries} attempts: {e}")
                        return default
        
        soft_archived_orders = safe_query(
            lambda: Order.query.filter(Order.is_archived.is_(True)).count()
        )
        soft_archived_order_items = safe_query(
            lambda: (
                db.session.query(db.func.count(OrderItem.id))
                .join(Order, OrderItem.order_id == Order.id)
                .filter(Order.is_archived.is_(True))
                .scalar()
                or 0
            )
        )
        soft_archived_order_chats = safe_query(
            lambda: (
                db.session.query(db.func.count(OrderChat.id))
                .join(Order, OrderChat.order_id == Order.id)
                .filter(Order.is_archived.is_(True))
                .scalar()
                or 0
            )
        )
        soft_archived_reviews = safe_query(
            lambda: (
                db.session.query(db.func.count(Review.id))
                .join(Order, Review.order_id == Order.id)
                .filter(Order.is_archived.is_(True))
                .scalar()
                or 0
            )
        )

        return {
            'main': {
                'orders': safe_query(lambda: Order.query.filter(Order.is_archived.is_(False)).count()),
                'reservations': safe_query(lambda: Reservation.query.count()),
                'audit_logs': safe_query(lambda: AuditLog.query.count()),
                'inventory_logs': safe_query(lambda: InventoryLog.query.count()),
                'notifications': safe_query(lambda: Notification.query.count()),
                'permission_audit_logs': safe_query(lambda: PermissionAuditLog.query.count()),
            },
            'archive': {
                'orders': safe_query(lambda: ArchiveOrder.query.count()) + soft_archived_orders,
                'order_items': safe_query(lambda: ArchiveOrderItem.query.count()) + soft_archived_order_items,
                'order_chats': safe_query(lambda: ArchiveOrderChat.query.count()) + soft_archived_order_chats,
                'reviews': safe_query(lambda: ArchiveReview.query.count()) + soft_archived_reviews,
                'reservations': safe_query(lambda: ArchiveReservation.query.count()),
                'audit_logs': safe_query(lambda: ArchiveAuditLog.query.count()),
                'inventory_logs': safe_query(lambda: ArchiveInventoryLog.query.count()),
                'notifications': safe_query(lambda: ArchiveNotification.query.count()),
                'permission_audit_logs': safe_query(lambda: ArchivePermissionAuditLog.query.count()),
            },
            'eligible_now': self._count_eligible(),
            'retention_days': self.config['retention_days'],
            'recent_runs': safe_query(
                lambda: ArchiveRun.query.order_by(ArchiveRun.started_at.desc()).limit(10).all(),
                default=[]
            ),
        }

    def _count_eligible(self):
        order_cutoff = self._cutoff('orders')
        res_cutoff = self._cutoff('reservations')
        statuses = self.config['eligible_order_statuses']
        res_statuses = self.config['eligible_reservation_statuses']
        return {
            'orders': Order.query.filter(
                Order.is_archived.is_(False),
                Order.status.in_(statuses),
                Order.created_at < order_cutoff,
            ).count(),
            'reservations': Reservation.query.filter(
                Reservation.status.in_(res_statuses),
                Reservation.created_at < res_cutoff,
            ).count(),
            'audit_logs': AuditLog.query.filter(AuditLog.created_at < self._cutoff('audit_logs')).count(),
            'inventory_logs': InventoryLog.query.filter(InventoryLog.created_at < self._cutoff('inventory_logs')).count(),
            'notifications': Notification.query.filter(
                Notification.is_read.is_(True),
                Notification.created_at < self._cutoff('notifications'),
            ).count(),
            'permission_audit_logs': PermissionAuditLog.query.filter(
                PermissionAuditLog.created_at < self._cutoff('permission_audit_logs')
            ).count(),
        }

    def run(self, triggered_by='manual', user_id=None, dry_run=False):
        """
        Execute archive job. Copies eligible records to archive DB, then removes from main DB.
        Returns summary dict.
        """
        from sqlalchemy.exc import OperationalError
        
        self.reload_config()
        batch_size = int(self.config.get('batch_size', 200))

        run = ArchiveRun(
            started_at=get_ph_time(),
            status='RUNNING',
            triggered_by=triggered_by,
            user_id=user_id,
        )
        
        try:
            db.session.add(run)
            db.session.commit()
        except OperationalError as e:
            db.session.rollback()
            db.session.remove()
            # Retry once
            try:
                db.session.add(run)
                db.session.commit()
            except Exception as retry_error:
                return {
                    'success': False,
                    'error': f'Failed to create archive run: {str(retry_error)}',
                    'summary': {},
                }

        summary = {
            'orders': 0,
            'order_items': 0,
            'order_chats': 0,
            'reviews': 0,
            'reservations': 0,
            'audit_logs': 0,
            'inventory_logs': 0,
            'notifications': 0,
            'permission_audit_logs': 0,
            'dry_run': dry_run,
        }

        try:
            summary['orders'] = self._archive_orders(batch_size, dry_run)
            summary['reservations'] = self._archive_reservations(batch_size, dry_run)
            summary['audit_logs'] = self._archive_simple(
                AuditLog, ArchiveAuditLog, 'audit_logs', batch_size, dry_run,
                lambda q, cutoff: q.filter(AuditLog.created_at < cutoff),
            )
            summary['inventory_logs'] = self._archive_simple(
                InventoryLog, ArchiveInventoryLog, 'inventory_logs', batch_size, dry_run,
                lambda q, cutoff: q.filter(InventoryLog.created_at < cutoff),
            )
            summary['notifications'] = self._archive_simple(
                Notification, ArchiveNotification, 'notifications', batch_size, dry_run,
                lambda q, cutoff: q.filter(Notification.is_read.is_(True), Notification.created_at < cutoff),
            )
            summary['permission_audit_logs'] = self._archive_simple(
                PermissionAuditLog, ArchivePermissionAuditLog, 'permission_audit_logs', batch_size, dry_run,
                lambda q, cutoff: q.filter(PermissionAuditLog.created_at < cutoff),
            )

            run.status = 'SUCCESS'
            run.finished_at = get_ph_time()
            run.summary_json = json.dumps(summary)
            
            try:
                db.session.commit()
            except OperationalError:
                db.session.rollback()
                db.session.remove()
                # Retry commit
                db.session.add(run)
                db.session.commit()
                
            return {'success': True, 'summary': summary, 'run_id': run.id}

        except Exception as e:
            db.session.rollback()
            run.status = 'FAILED'
            run.finished_at = get_ph_time()
            run.error_message = str(e)
            run.summary_json = json.dumps(summary)
            
            try:
                db.session.add(run)
                db.session.commit()
            except Exception:
                # If we can't even save the error, just return it
                db.session.rollback()
                pass
                
            return {'success': False, 'error': str(e), 'summary': summary, 'run_id': run.id}

    def _archive_orders(self, batch_size, dry_run):
        cutoff = self._cutoff('orders')
        statuses = self.config['eligible_order_statuses']
        archived = 0

        while True:
            orders = (
                Order.query.filter(
                    Order.is_archived.is_(False),
                    Order.status.in_(statuses),
                    Order.created_at < cutoff,
                )
                .order_by(Order.created_at.asc())
                .limit(batch_size)
                .all()
            )
            if not orders:
                break

            if dry_run:
                archived += len(orders)
                break
            now = get_ph_time()
            for order in orders:
                order.is_archived = True
                order.archived_at = now
                archived += 1

            db.session.commit()

        return archived

    def _archive_reservations(self, batch_size, dry_run):
        cutoff = self._cutoff('reservations')
        statuses = self.config['eligible_reservation_statuses']
        archived = 0

        while True:
            rows = (
                Reservation.query.filter(Reservation.status.in_(statuses), Reservation.created_at < cutoff)
                .order_by(Reservation.created_at.asc())
                .limit(batch_size)
                .all()
            )
            if not rows:
                break

            if dry_run:
                return len(rows)

            for res in rows:
                if ArchiveReservation.query.filter_by(original_id=res.id).first():
                    db.session.delete(res)
                    continue

                db.session.add(ArchiveReservation(
                    original_id=res.id,
                    reservation_code=res.reservation_code,
                    user_id=res.user_id,
                    branch=res.branch,
                    date=res.date,
                    time=res.time,
                    guest_count=res.guest_count,
                    occasion=res.occasion,
                    booking_type=res.booking_type,
                    duration=res.duration,
                    status=res.status,
                    table_number=res.table_number,
                    cancellation_reason=res.cancellation_reason,
                    created_at=res.created_at,
                ))
                db.session.delete(res)
                archived += 1

            db.session.commit()

        return archived

    def _archive_simple(self, SourceModel, ArchiveModel, retention_key, batch_size, dry_run, filter_fn):
        cutoff = self._cutoff(retention_key)
        archived = 0

        while True:
            query = filter_fn(SourceModel.query, cutoff)
            rows = query.order_by(SourceModel.created_at.asc()).limit(batch_size).all()
            if not rows:
                break

            if dry_run:
                return len(rows)

            for row in rows:
                if ArchiveModel.query.filter_by(original_id=row.id).first():
                    db.session.delete(row)
                    continue

                payload = {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != 'id'}
                archive_row = ArchiveModel(original_id=row.id, **payload)
                db.session.add(archive_row)
                db.session.delete(row)
                archived += 1

            db.session.commit()

        return archived

    def search_archived_orders(self, page=1, per_page=30, branch=None, status=None, source='soft'):
        if source == 'legacy':
            query = ArchiveOrder.query
            if branch:
                query = query.filter(ArchiveOrder.branch == branch)
            if status:
                query = query.filter(ArchiveOrder.status == status)
            return query.order_by(ArchiveOrder.created_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )

        query = Order.query.filter(Order.is_archived.is_(True))
        if branch:
            query = query.filter(Order.branch == branch)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    def get_archived_order_detail(self, original_id, source=None):
        if source != 'legacy':
            order = Order.query.filter(Order.id == original_id, Order.is_archived.is_(True)).first()
            if order:
                return {'order': order, 'items': list(order.items), 'chats': list(order.chats), 'source': 'soft'}
            if source == 'soft':
                return None

        order = ArchiveOrder.query.filter_by(original_id=original_id).first()
        if not order:
            return None
        items = ArchiveOrderItem.query.filter_by(order_original_id=original_id).all()
        chats = ArchiveOrderChat.query.filter_by(order_original_id=original_id).all()
        return {'order': order, 'items': items, 'chats': chats, 'source': 'legacy'}

    def get_archive_storage_summary(self):
        """Grouped archived order counts by year-month."""
        from collections import Counter
        from sqlalchemy.exc import OperationalError
        
        counts = Counter()
        
        # Helper to safely execute queries
        def safe_query(query_fn, max_retries=3):
            for attempt in range(max_retries):
                try:
                    return query_fn()
                except OperationalError as e:
                    db.session.rollback()
                    if attempt < max_retries - 1:
                        db.session.remove()
                        continue
                    else:
                        print(f"Query failed after {max_retries} attempts: {e}")
                        return []
        
        rows = safe_query(
            lambda: ArchiveOrder.query.filter(ArchiveOrder.archived_at.isnot(None))
            .with_entities(ArchiveOrder.archived_at).all()
        )
        
        for (archived_at,) in rows:
            if archived_at:
                counts[archived_at.strftime('%Y-%m')] += 1

        soft_rows = safe_query(
            lambda: Order.query.filter(Order.is_archived.is_(True), Order.archived_at.isnot(None))
            .with_entities(Order.archived_at).all()
        )
        
        for (archived_at,) in soft_rows:
            if archived_at:
                counts[archived_at.strftime('%Y-%m')] += 1

        return [{'period': k, 'count': v} for k, v in sorted(counts.items())]
