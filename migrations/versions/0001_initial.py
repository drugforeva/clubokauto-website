"""Начальная схема: пользователи, подключения, чаты, сообщения, вложения.

Revision ID: 0001_initial
Revises: -
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Telegram ID не влезает в int4, но sqlite автоинкрементирует только INTEGER.
BIG_INT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
JSON_DICT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# Выражение совпадает с MessageRepository._text_condition: иначе планировщик
# не воспользуется индексом и поиск будет читать всю таблицу.
FTS_INDEX = (
    "CREATE INDEX ix_messages_text_fts ON messages "
    "USING gin (to_tsvector('russian', coalesce(text, '')))"
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", BIG_INT, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("is_premium", sa.Boolean(), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True
    )

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notify_deletions", sa.Boolean(), nullable=False),
        sa.Column("notify_edits", sa.Boolean(), nullable=False),
        sa.Column("notify_outgoing", sa.Boolean(), nullable=False),
        sa.Column("save_media", sa.Boolean(), nullable=False),
        sa.Column("download_media", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings")),
    )
    op.create_index(op.f("ix_settings_user_id"), "settings", ["user_id"], unique=True)

    op.create_table(
        "business_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("owner_chat_id", BIG_INT, nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("can_reply", sa.Boolean(), nullable=False),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_business_connections_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_connections")),
    )
    op.create_index(
        op.f("ix_business_connections_connection_id"),
        "business_connections",
        ["connection_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_business_connections_user_id"),
        "business_connections",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "chats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", BIG_INT, nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_chats_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chats")),
        sa.UniqueConstraint(
            "owner_id",
            "telegram_chat_id",
            name=op.f("uq_chats_owner_id_telegram_chat_id"),
        ),
    )
    op.create_index(op.f("ix_chats_owner_id"), "chats", ["owner_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.String(length=128), nullable=True),
        sa.Column("telegram_message_id", BIG_INT, nullable=False),
        sa.Column("sender_id", BIG_INT, nullable=True),
        sa.Column("sender_username", sa.String(length=64), nullable=True),
        sa.Column("sender_first_name", sa.String(length=128), nullable=True),
        sa.Column("sender_last_name", sa.String(length=128), nullable=True),
        sa.Column("is_outgoing", sa.Boolean(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("extra", JSON_DICT, nullable=True),
        sa.Column("reply_to_message_id", BIG_INT, nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("edited_at", sa.DateTime(), nullable=True),
        sa.Column("edit_count", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_messages_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_messages_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint(
            "owner_id",
            "chat_id",
            "telegram_message_id",
            name=op.f("uq_messages_owner_id_chat_id_telegram_message_id"),
        ),
    )
    op.create_index(op.f("ix_messages_owner_id"), "messages", ["owner_id"], unique=False)
    op.create_index(op.f("ix_messages_chat_id"), "messages", ["chat_id"], unique=False)
    op.create_index(
        "ix_messages_owner_sent", "messages", ["owner_id", "sent_at"], unique=False
    )
    op.create_index(
        "ix_messages_owner_type_sent",
        "messages",
        ["owner_id", "content_type", "sent_at"],
        unique=False,
    )
    op.create_index(
        "ix_messages_chat_sent", "messages", ["chat_id", "sent_at"], unique=False
    )
    op.create_index(
        "ix_messages_owner_deleted", "messages", ["owner_id", "is_deleted"], unique=False
    )

    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("file_id", sa.String(length=256), nullable=False),
        sa.Column("file_unique_id", sa.String(length=128), nullable=True),
        sa.Column("file_name", sa.String(length=256), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size", BIG_INT, nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("local_path", sa.String(length=512), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_media_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
    )
    op.create_index(op.f("ix_media_message_id"), "media", ["message_id"], unique=False)

    op.create_table(
        "edits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("edited_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_edits_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_edits")),
        sa.UniqueConstraint(
            "message_id", "version", name=op.f("uq_edits_message_id_version")
        ),
    )
    op.create_index(op.f("ix_edits_message_id"), "edits", ["message_id"], unique=False)

    op.create_table(
        "deleted_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.Integer(), nullable=True),
        sa.Column("telegram_message_id", BIG_INT, nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["chats.id"],
            name=op.f("fk_deleted_messages_chat_id_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_deleted_messages_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_deleted_messages_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deleted_messages")),
    )
    op.create_index(
        op.f("ix_deleted_messages_owner_id"),
        "deleted_messages",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deleted_messages_message_id"),
        "deleted_messages",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        "ix_deleted_messages_owner_detected",
        "deleted_messages",
        ["owner_id", "detected_at"],
        unique=False,
    )

    # GIN-индекс есть только в PostgreSQL; на sqlite поиск идёт через LIKE.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(FTS_INDEX)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_messages_text_fts")

    op.drop_index("ix_deleted_messages_owner_detected", table_name="deleted_messages")
    op.drop_index(op.f("ix_deleted_messages_message_id"), table_name="deleted_messages")
    op.drop_index(op.f("ix_deleted_messages_owner_id"), table_name="deleted_messages")
    op.drop_table("deleted_messages")

    op.drop_index(op.f("ix_edits_message_id"), table_name="edits")
    op.drop_table("edits")

    op.drop_index(op.f("ix_media_message_id"), table_name="media")
    op.drop_table("media")

    op.drop_index("ix_messages_owner_deleted", table_name="messages")
    op.drop_index("ix_messages_chat_sent", table_name="messages")
    op.drop_index("ix_messages_owner_type_sent", table_name="messages")
    op.drop_index("ix_messages_owner_sent", table_name="messages")
    op.drop_index(op.f("ix_messages_chat_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_owner_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_chats_owner_id"), table_name="chats")
    op.drop_table("chats")

    op.drop_index(
        op.f("ix_business_connections_user_id"), table_name="business_connections"
    )
    op.drop_index(
        op.f("ix_business_connections_connection_id"), table_name="business_connections"
    )
    op.drop_table("business_connections")

    op.drop_index(op.f("ix_settings_user_id"), table_name="settings")
    op.drop_table("settings")

    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
