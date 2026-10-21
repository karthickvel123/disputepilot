"""Initial database schema for DisputePilot (Postgres / SQLite compatible).

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-21 15:30:00.000000

Includes merchant_id on all domain tables to support multi-merchant provenance
and single-tenant data isolation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('merchant_id', sa.String(length=64), server_default='default_merchant', nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('role', sa.String(length=32), server_default='reviewer', nullable=False),
        sa.Column('full_name', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('last_login', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_users_username'),
    )
    op.create_index('idx_users_merchant', 'users', ['merchant_id'])

    # 2. dispute_events (webhook events)
    op.create_table(
        'dispute_events',
        sa.Column('event_id', sa.String(length=128), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), server_default='default_merchant', nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('dispute_id', sa.String(length=64), nullable=True),
        sa.Column('payment_id', sa.String(length=64), nullable=True),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('received_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('idx_dispute_events_received', 'dispute_events', ['received_at'])
    op.create_index('idx_dispute_events_dispute', 'dispute_events', ['dispute_id'])
    op.create_index('idx_dispute_events_merchant', 'dispute_events', ['merchant_id'])

    # 3. approval_tokens
    op.create_table(
        'approval_tokens',
        sa.Column('token', sa.String(length=128), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), server_default='default_merchant', nullable=False),
        sa.Column('dispute_id', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('approver', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('used', sa.Integer(), server_default='0', nullable=False),
        sa.Column('metadata', sa.Text(), server_default='{}', nullable=False),
        sa.PrimaryKeyConstraint('token'),
    )
    op.create_index('idx_approval_dispute', 'approval_tokens', ['dispute_id'])
    op.create_index('idx_approval_used', 'approval_tokens', ['used'])
    op.create_index('idx_approval_merchant', 'approval_tokens', ['merchant_id'])

    # 4. evidence_documents (evidence locker)
    op.create_table(
        'evidence_documents',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), server_default='default_merchant', nullable=False),
        sa.Column('dispute_id', sa.String(length=64), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('file_name', sa.String(length=256), nullable=False),
        sa.Column('mime', sa.String(length=64), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('uploaded_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('razorpay_doc_id', sa.String(length=64), nullable=True),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_evidence_dispute', 'evidence_documents', ['dispute_id'])
    op.create_index('idx_evidence_sha256', 'evidence_documents', ['sha256'])
    op.create_index('idx_evidence_merchant', 'evidence_documents', ['merchant_id'])

    # 5. audit_events (tamper-evident hash chain)
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('merchant_id', sa.String(length=64), server_default='default_merchant', nullable=False),
        sa.Column('case_id', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.BigInteger(), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=False),
        sa.Column('hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_case_id', 'audit_events', ['case_id'])
    op.create_index('idx_audit_timestamp', 'audit_events', ['timestamp'])
    op.create_index('idx_audit_merchant', 'audit_events', ['merchant_id'])

    # 6. comments
    op.create_table(
        'comments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('merchant_id', sa.String(length=64), server_default='default_merchant', nullable=False),
        sa.Column('case_id', sa.String(length=64), nullable=False),
        sa.Column('author', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_comments_case_id', 'comments', ['case_id'])
    op.create_index('idx_comments_merchant', 'comments', ['merchant_id'])


def downgrade() -> None:
    op.drop_table('comments')
    op.drop_table('audit_events')
    op.drop_table('evidence_documents')
    op.drop_table('approval_tokens')
    op.drop_table('dispute_events')
    op.drop_table('users')
