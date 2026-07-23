"""denormalize track_id/platform onto playback_events, relax queue_track_id to SET NULL

Revision ID: 28203e263950
Revises: f4cd03fbdb73
Create Date: 2026-07-22 12:32:45.613307

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28203e263950'
down_revision: Union[str, Sequence[str], None] = 'f4cd03fbdb73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Root cause being fixed: playback_events.queue_track_id ON DELETE CASCADE
    means every rerank (queue_tracks deleted + rebuilt on every skip/
    completion) also deletes that track's playback_events rows — so TC-9's
    >=50%-listened export filter almost never has anything to find by the
    time a session is exported. track_id/platform are stable, platform-level
    identifiers already available on QueueTrack at PlaybackEvent-creation
    time; denormalizing them here lets playback history outlive the queue
    row it was recorded against. queue_track_id itself becomes nullable with
    ON DELETE SET NULL (row survives, only the now-meaningless link to a
    since-rebuilt queue_tracks row is dropped) instead of CASCADE.
    """
    op.add_column('playback_events', sa.Column('track_id', sa.String(), nullable=True))
    op.add_column('playback_events', sa.Column('platform', sa.String(), nullable=True))

    # Backfill from the currently-existing queue_tracks row each event still
    # points to — safe only right now, before this migration's own FK change:
    # under the old ON DELETE CASCADE, a playback_events row could never
    # outlive its parent queue_tracks row, so every existing row's
    # queue_track_id is guaranteed to still resolve at this point.
    op.execute(
        """
        UPDATE playback_events pe
        SET track_id = qt.track_id, platform = qt.platform
        FROM queue_tracks qt
        WHERE pe.queue_track_id = qt.id
        """
    )

    op.alter_column('playback_events', 'track_id', nullable=False)
    op.alter_column('playback_events', 'platform', nullable=False)

    op.drop_constraint('playback_events_queue_track_id_fkey', 'playback_events', type_='foreignkey')
    op.alter_column('playback_events', 'queue_track_id', nullable=True)
    op.create_foreign_key(
        'playback_events_queue_track_id_fkey',
        'playback_events', 'queue_tracks',
        ['queue_track_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('playback_events_queue_track_id_fkey', 'playback_events', type_='foreignkey')
    op.alter_column('playback_events', 'queue_track_id', nullable=False)
    op.create_foreign_key(
        'playback_events_queue_track_id_fkey',
        'playback_events', 'queue_tracks',
        ['queue_track_id'], ['id'],
        ondelete='CASCADE',
    )
    op.drop_column('playback_events', 'platform')
    op.drop_column('playback_events', 'track_id')
