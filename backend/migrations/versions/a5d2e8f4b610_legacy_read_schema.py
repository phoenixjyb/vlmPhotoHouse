"""Add missing legacy read structures without rebuilding assets or granting access.

Revision ID: a5d2e8f4b610
Revises: f4c1a8d2e703
"""
from alembic import op
import sqlalchemy as sa

revision = 'a5d2e8f4b610'
down_revision = 'f4c1a8d2e703'
branch_labels = None
depends_on = None


def _index(bind, name, table, columns, unique=False):
    existing = next((i for i in sa.inspect(bind).get_indexes(table) if i['name'] == name), None)
    if existing:
        if existing['column_names'] != columns or bool(existing['unique']) != unique:
            raise RuntimeError('Existing index requires explicit schema review: ' + name)
        return
    op.create_index(name, table, columns, unique=unique)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        raise RuntimeError('Legacy read reconciliation currently requires SQLite')
    if bind.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is not None:
        raise RuntimeError('Existing foreign-key violations require offline review')

    if 'tags' not in sa.inspect(bind).get_table_names():
        op.create_table('tags',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(128), nullable=False),
            sa.Column('type', sa.String(32)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')))
    if 'asset_tags' not in sa.inspect(bind).get_table_names():
        op.create_table('asset_tags',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False),
            sa.Column('source', sa.String(16)), sa.Column('score', sa.Float()),
            sa.Column('model', sa.String(64)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')))
    if 'asset_tag_blocks' not in sa.inspect(bind).get_table_names():
        op.create_table('asset_tag_blocks',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tags.id', ondelete='CASCADE'), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')))
    if 'video_segments' not in sa.inspect(bind).get_table_names():
        op.create_table('video_segments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('asset_id', sa.Integer(), sa.ForeignKey('assets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('start_sec', sa.Float(), nullable=False), sa.Column('end_sec', sa.Float(), nullable=False),
            sa.Column('keyframe_path', sa.String()), sa.Column('embedding_path', sa.String()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')))

    # Existing startup-created tables are accepted only when their declared
    # columns and parent links match; never silently replace or truncate them.
    required = {
        'tags': {'id', 'name', 'type', 'created_at'},
        'asset_tags': {'id', 'asset_id', 'tag_id', 'source', 'score', 'model', 'created_at'},
        'asset_tag_blocks': {'id', 'asset_id', 'tag_id', 'created_at'},
        'video_segments': {'id', 'asset_id', 'start_sec', 'end_sec', 'keyframe_path', 'embedding_path', 'created_at'},
    }
    for table, columns in required.items():
        actual_columns = {c['name']: c for c in sa.inspect(bind).get_columns(table)}
        if not columns <= set(actual_columns):
            raise RuntimeError('Existing table requires explicit schema review: ' + table)
        if sa.inspect(bind).get_pk_constraint(table)['constrained_columns'] != ['id']:
            raise RuntimeError('Existing primary key requires explicit schema review: ' + table)
        for name in columns:
            expected_type = (sa.Integer if name in {'id', 'asset_id', 'tag_id'} else
                             sa.Float if name in {'score', 'start_sec', 'end_sec'} else
                             sa.DateTime if name == 'created_at' else sa.String)
            if not isinstance(actual_columns[name]['type'], expected_type):
                raise RuntimeError('Existing column type requires explicit schema review: ' + table + '.' + name)
            if name in {'asset_id', 'tag_id', 'name', 'start_sec', 'end_sec'} and actual_columns[name]['nullable']:
                raise RuntimeError('Existing column nullability requires explicit schema review: ' + table + '.' + name)
    for table, column, target in [('asset_tags', 'asset_id', 'assets'), ('asset_tags', 'tag_id', 'tags'),
                                  ('asset_tag_blocks', 'asset_id', 'assets'), ('asset_tag_blocks', 'tag_id', 'tags'),
                                  ('video_segments', 'asset_id', 'assets')]:
        if not any(f['constrained_columns'] == [column] and f['referred_table'] == target
                   and f['referred_columns'] == ['id'] and f.get('options', {}).get('ondelete') == 'CASCADE'
                   for f in sa.inspect(bind).get_foreign_keys(table)):
            raise RuntimeError('Existing parent link requires explicit schema review: ' + table)

    for table, name, kind in [('assets', 'duration_sec', sa.Float()), ('assets', 'fps', sa.Float()),
                              ('face_detections', 'label_source', sa.String(16)),
                              ('face_detections', 'label_score', sa.Float())]:
        actual = next((c for c in sa.inspect(bind).get_columns(table) if c['name'] == name), None)
        if actual is None:
            op.add_column(table, sa.Column(name, kind, nullable=True))
        elif not isinstance(actual['type'], type(kind)):
            raise RuntimeError('Existing read column requires explicit schema review: ' + table + '.' + name)

    for name, table, columns, unique in [
        ('ix_tags_name', 'tags', ['name'], True),
        ('idx_asset_tag_unique', 'asset_tags', ['asset_id', 'tag_id'], True),
        ('ix_asset_tags_asset_id', 'asset_tags', ['asset_id'], False),
        ('ix_asset_tags_tag_id', 'asset_tags', ['tag_id'], False),
        ('ix_asset_tags_source', 'asset_tags', ['source'], False),
        ('idx_asset_tag_block_unique', 'asset_tag_blocks', ['asset_id', 'tag_id'], True),
        ('ix_asset_tag_blocks_asset_id', 'asset_tag_blocks', ['asset_id'], False),
        ('ix_asset_tag_blocks_tag_id', 'asset_tag_blocks', ['tag_id'], False),
        ('ix_video_segments_asset_id', 'video_segments', ['asset_id'], False),
        ('ix_assets_perceptual_hash', 'assets', ['perceptual_hash'], False),
        ('ix_assets_taken_at', 'assets', ['taken_at'], False),
        ('ix_embeddings_modality', 'embeddings', ['modality'], False),
        ('ix_tasks_scheduled_at', 'tasks', ['scheduled_at'], False),
        ('ix_face_detections_label_source', 'face_detections', ['label_source'], False),
    ]:
        _index(bind, name, table, columns, unique)


def downgrade():
    raise RuntimeError('Schema downgrade requires reviewed offline backup restoration; keep access closed')
