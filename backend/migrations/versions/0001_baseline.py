"""Schema inicial do BookRoomLog (livros, categorias e pódio do Anuário)

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-10-25 17:12:51.680697
"""
from alembic import op
import sqlalchemy as sa


revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('authors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('authors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_authors_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_authors_name'), ['name'], unique=True)

    op.create_table('genres',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('color', sa.String(length=20), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('genres', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_genres_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_genres_name'), ['name'], unique=True)

    op.create_table('publishers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('publishers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_publishers_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_publishers_name'), ['name'], unique=True)

    op.create_table('series',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_series_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_series_name'), ['name'], unique=True)

    op.create_table('books',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('publisher_id', sa.Integer(), nullable=True),
    sa.Column('series_id', sa.Integer(), nullable=True),
    sa.Column('series_number', sa.Float(), nullable=True),
    sa.Column('status', sa.Enum('QUERO_LER', 'PROXIMO', 'LENDO', 'LIDO', name='bookstatus'), nullable=False),
    sa.Column('cover_image', sa.String(length=300), nullable=True),
    sa.Column('next_position', sa.Integer(), nullable=True),
    sa.Column('progress', sa.Integer(), nullable=True),
    sa.Column('pages', sa.Integer(), nullable=True),
    sa.Column('format', sa.Enum('EBOOK', 'FISICO', 'AUDIOBOOK', name='bookformat'), nullable=False),
    sa.Column('language', sa.String(length=40), nullable=True),
    sa.Column('isbn', sa.String(length=20), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('finish_date', sa.Date(), nullable=True),
    sa.Column('completion_year', sa.Integer(), nullable=True),
    sa.Column('reread_of_id', sa.Integer(), nullable=True),
    sa.Column('read_number', sa.Integer(), nullable=False),
    sa.Column('is_favorite', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['publisher_id'], ['publishers.id'], ),
    sa.ForeignKeyConstraint(['reread_of_id'], ['books.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['series_id'], ['series.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_books_completion_year'), ['completion_year'], unique=False)
        batch_op.create_index(batch_op.f('ix_books_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_books_isbn'), ['isbn'], unique=False)
        batch_op.create_index(batch_op.f('ix_books_next_position'), ['next_position'], unique=False)
        batch_op.create_index(batch_op.f('ix_books_reread_of_id'), ['reread_of_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_books_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_books_title'), ['title'], unique=False)

    op.create_table('book_authors',
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['authors.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('book_id', 'author_id')
    )
    op.create_table('book_genres',
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('genre_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['genre_id'], ['genres.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('book_id', 'genre_id')
    )
    op.create_table('yearbook_picks',
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('year', 'position')
    )


def downgrade() -> None:
    op.drop_table('yearbook_picks')
    op.drop_table('book_genres')
    op.drop_table('book_authors')
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_books_title'))
        batch_op.drop_index(batch_op.f('ix_books_status'))
        batch_op.drop_index(batch_op.f('ix_books_reread_of_id'))
        batch_op.drop_index(batch_op.f('ix_books_next_position'))
        batch_op.drop_index(batch_op.f('ix_books_isbn'))
        batch_op.drop_index(batch_op.f('ix_books_id'))
        batch_op.drop_index(batch_op.f('ix_books_completion_year'))

    op.drop_table('books')
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_series_name'))
        batch_op.drop_index(batch_op.f('ix_series_id'))

    op.drop_table('series')
    with op.batch_alter_table('publishers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_publishers_name'))
        batch_op.drop_index(batch_op.f('ix_publishers_id'))

    op.drop_table('publishers')
    with op.batch_alter_table('genres', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_genres_name'))
        batch_op.drop_index(batch_op.f('ix_genres_id'))

    op.drop_table('genres')
    with op.batch_alter_table('authors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_authors_name'))
        batch_op.drop_index(batch_op.f('ix_authors_id'))

    op.drop_table('authors')
