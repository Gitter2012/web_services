"""add weibo hot search table

Revision ID: weibo001
Revises:
Create Date: 2026-02-17 16:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'weibo001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add weibo_hot_searches table."""
    op.create_table(
        'weibo_hot_searches',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('board_type', sa.String(50), nullable=False,
                  comment='榜单类型: realtimehot, socialevent, entrank, sport, game'),
        sa.Column('board_name', sa.String(100), nullable=False,
                  comment='榜单中文名称'),
        sa.Column('description', sa.Text(), nullable=True,
                  comment='榜单描述'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1',
                  comment='是否激活'),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True,
                  comment='最后抓取时间'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0',
                  comment='连续错误次数'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('board_type'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        mysql_comment='微博热搜榜单配置表'
    )

    # Create index on board_type
    op.create_index('idx_weibo_hot_searches_board_type', 'weibo_hot_searches', ['board_type'], unique=False)

    # Insert initial data - only realtimehot is active by default
    # Other boards require login cookie, disabled by default
    op.execute("""
        INSERT INTO weibo_hot_searches (board_type, board_name, description, is_active) VALUES
        ('realtimehot', '热搜榜', '微博实时热搜榜单（公开接口，无需登录）', 1),
        ('socialevent', '要闻榜', '微博社会要闻榜单（需要登录Cookie）', 0),
        ('entrank', '文娱榜', '微博文娱热点榜单（需要登录Cookie）', 0),
        ('sport', '体育榜', '微博体育热点榜单（需要登录Cookie）', 0),
        ('game', '游戏榜', '微博游戏热点榜单（需要登录Cookie）', 0)
    """)


def downgrade() -> None:
    """Remove weibo_hot_searches table."""
    op.drop_index('idx_weibo_hot_searches_board_type', table_name='weibo_hot_searches')
    op.drop_table('weibo_hot_searches')
