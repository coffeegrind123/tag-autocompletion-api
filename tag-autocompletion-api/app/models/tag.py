from sqlalchemy import Column, Integer, String, ARRAY, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

Base = declarative_base()


class Tag(Base):
    """
    Danbooru tag model with PostgreSQL-specific optimizations
    """
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    tag = Column(String, nullable=False, unique=True)  # Canonical tag name (spaces, not underscores)
    type = Column(Integer, nullable=False)  # Danbooru category (0=general, 1=artist, etc.)
    count = Column(Integer, nullable=False)  # Usage frequency for ranking
    aliases = Column(PG_ARRAY(String), nullable=True, default=[])  # Alternative names/spellings

    # Performance indexes
    __table_args__ = (
        # Trigram index for fuzzy search (requires pg_trgm extension)
        Index('idx_tag_gist', 'tag', postgresql_using='gist', postgresql_ops={'tag': 'gist_trgm_ops'}),
        # GIN index for array aliases
        Index('idx_aliases_gin', 'aliases', postgresql_using='gin'),
        # Index for popularity ranking
        Index('idx_count', 'count'),
        # Unique constraint already handled by unique=True on tag column
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, tag='{self.tag}', type={self.type}, count={self.count})>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'tag': self.tag,
            'type': self.type,
            'count': self.count,
            'aliases': self.aliases or []
        }

    @classmethod
    def from_csv_data(cls, tag_data: dict):
        """Create Tag instance from parsed CSV data"""
        return cls(
            tag=tag_data['tag'],
            type=tag_data['type'],
            count=tag_data['count'],
            aliases=tag_data['aliases']
        )