import asyncio
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
import structlog
from pygtrie import CharTrie
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.tag import Tag
from app.db.database import async_session_maker

logger = structlog.get_logger()


class TagSearchEngine:
    """
    High-performance in-memory tag search engine with multiple search strategies
    """

    def __init__(self):
        # In-memory data structures
        self.exact_tags: Dict[str, dict] = {}           # "blonde hair" -> tag_info
        self.alias_to_tag: Dict[str, str] = {}          # "big breasts" -> "large breasts"
        self.prefix_trie = CharTrie()                   # Fast prefix matching
        self.word_index: Dict[str, Set[str]] = defaultdict(set)  # "blonde" -> {tags containing "blonde"}
        self.popular_tags: List[Tuple[str, int]] = []   # Sorted by count for ranking
        
        # Statistics
        self.total_tags = 0
        self.total_aliases = 0
        self.loaded = False

    async def load_from_database(self, session: Optional[AsyncSession] = None) -> None:
        """
        Load all tag data from database into memory structures
        
        Args:
            session: Optional database session
        """
        if session is None:
            async with async_session_maker() as session:
                await self._load_from_database_with_session(session)
        else:
            await self._load_from_database_with_session(session)

    async def _load_from_database_with_session(self, session: AsyncSession) -> None:
        """
        Internal method to load data with existing session
        """
        logger.info("Loading tag data from database into memory")
        
        # Clear existing data
        self.clear()
        
        # Load all tags
        result = await session.execute(
            select(Tag).order_by(Tag.count.desc())
        )
        tags = result.scalars().all()
        
        for tag in tags:
            self._index_tag(tag.to_dict())
        
        # Build popularity ranking
        self.popular_tags = [
            (tag.tag, tag.count) for tag in tags
        ]
        
        self.loaded = True
        self.total_tags = len(self.exact_tags)
        
        logger.info("Tag data loaded successfully", 
                   total_tags=self.total_tags,
                   total_aliases=self.total_aliases)

    def _index_tag(self, tag_data: dict) -> None:
        """
        Index a single tag in all data structures
        
        Args:
            tag_data: Tag dictionary from database
        """
        clean_tag = tag_data['tag'].lower()
        
        # Exact lookup
        self.exact_tags[clean_tag] = tag_data
        
        # Alias mapping (all aliases point to canonical tag)
        for alias in tag_data.get('aliases', []):
            alias_clean = alias.lower()
            self.alias_to_tag[alias_clean] = tag_data['tag']
            self.total_aliases += 1
        
        # Prefix trie
        self.prefix_trie[clean_tag] = tag_data['tag']
        
        # Word indexing for intersection search
        words = clean_tag.split()
        for word in words:
            if len(word) > 1:  # Skip single characters
                self.word_index[word].add(tag_data['tag'])

    def clear(self) -> None:
        """Clear all in-memory data structures"""
        self.exact_tags.clear()
        self.alias_to_tag.clear()
        self.prefix_trie.clear()
        self.word_index.clear()
        self.popular_tags.clear()
        self.total_tags = 0
        self.total_aliases = 0
        self.loaded = False

    def normalize_query(self, query: str) -> str:
        """
        Normalize query string for consistent matching
        
        Args:
            query: Raw query string
            
        Returns:
            Normalized query string
        """
        # Convert to lowercase
        query = query.lower().strip()
        
        # Convert underscores to spaces
        query = query.replace('_', ' ')
        
        # Remove extra whitespace
        query = ' '.join(query.split())
        
        return query

    async def search_exact(self, query: str) -> Optional[str]:
        """
        Exact match search (fastest - hash lookup)
        
        Args:
            query: Normalized query string
            
        Returns:
            Exact match or None
        """
        return self.exact_tags.get(query, {}).get('tag')

    async def search_alias(self, query: str) -> Optional[str]:
        """
        Alias lookup search (fast - hash lookup)
        
        Args:
            query: Normalized query string
            
        Returns:
            Canonical tag from alias or None
        """
        return self.alias_to_tag.get(query)

    async def search_word_intersection(self, query: str, limit: int = 10) -> List[str]:
        """
        Word intersection search (medium speed - set operations)
        
        Args:
            query: Normalized query string
            limit: Maximum results to return
            
        Returns:
            List of matching tags
        """
        words = query.split()
        if not words:
            return []
        
        # Find tags containing ALL words
        matching_tags = None
        for word in words:
            word_tags = self.word_index.get(word, set())
            if matching_tags is None:
                matching_tags = word_tags.copy()
            else:
                matching_tags &= word_tags
        
        if not matching_tags:
            return []
        
        # Rank by popularity and return top results
        ranked_tags = []
        for tag_name, count in self.popular_tags:
            if tag_name in matching_tags:
                ranked_tags.append(tag_name)
                if len(ranked_tags) >= limit:
                    break
        
        return ranked_tags

    async def search_prefix(self, query: str, limit: int = 10) -> List[str]:
        """
        Prefix matching search (medium speed - trie traversal)
        
        Args:
            query: Normalized query string
            limit: Maximum results to return
            
        Returns:
            List of matching tags
        """
        try:
            # Get all tags with the prefix
            prefix_matches = list(self.prefix_trie.itervalues(prefix=query))
            
            if not prefix_matches:
                logger.debug("No prefix matches found", query=query, trie_size=len(self.prefix_trie))
                return []
            
            logger.debug("Found prefix matches", query=query, count=len(prefix_matches), matches=prefix_matches[:3])
            
            # Convert to set for faster lookup
            prefix_matches_set = set(prefix_matches)
            
            # Rank by popularity
            ranked_matches = []
            for tag_name, count in self.popular_tags:
                if tag_name in prefix_matches_set:
                    ranked_matches.append(tag_name)
                    if len(ranked_matches) >= limit:
                        break
            
            # If ranking didn't work (shouldn't happen), return first matches
            if not ranked_matches and prefix_matches:
                logger.debug("Ranking failed, returning first matches", query=query)
                return prefix_matches[:limit]
            
            logger.debug("Prefix search successful", query=query, results=len(ranked_matches))
            return ranked_matches
            
        except Exception as e:
            logger.warning("Prefix search failed", query=query, error=str(e))
            return []

    async def search_fuzzy_database(
        self, 
        query: str, 
        limit: int = 10, 
        session: Optional[AsyncSession] = None
    ) -> List[str]:
        """
        Database fuzzy search fallback (slow - PostgreSQL trigrams)
        
        Args:
            query: Normalized query string
            limit: Maximum results to return
            session: Optional database session
            
        Returns:
            List of matching tags
        """
        if session is None:
            async with async_session_maker() as session:
                return await self._search_fuzzy_database_with_session(query, limit, session)
        else:
            return await self._search_fuzzy_database_with_session(query, limit, session)

    async def _search_fuzzy_database_with_session(
        self, 
        query: str, 
        limit: int, 
        session: AsyncSession
    ) -> List[str]:
        """
        Internal method for fuzzy search with existing session
        """
        try:
            # Use PostgreSQL similarity function with trigrams
            result = await session.execute(
                select(Tag.tag)
                .where(func.similarity(Tag.tag, query) > 0.3)
                .order_by(func.similarity(Tag.tag, query).desc(), Tag.count.desc())
                .limit(limit)
            )
            
            return [row[0] for row in result.fetchall()]
            
        except Exception as e:
            logger.warning("Database fuzzy search failed", query=query, error=str(e))
            return []

    async def search_fuzzy_memory(self, query: str, limit: int = 10) -> List[str]:
        """
        In-memory fuzzy search using rapidfuzz (fallback if no database)
        
        Args:
            query: Normalized query string
            limit: Maximum results to return
            
        Returns:
            List of matching tags
        """
        if not self.exact_tags:
            return []
        
        # Calculate similarity scores for all tags
        candidates = []
        for tag_name in self.exact_tags.keys():
            score = fuzz.ratio(query, tag_name)
            if score > 60:  # Minimum similarity threshold
                candidates.append((tag_name, score))
        
        # Sort by similarity score and popularity
        candidates.sort(key=lambda x: (-x[1], -self.exact_tags[x[0]]['count']))
        
        return [self.exact_tags[tag]['tag'] for tag, _ in candidates[:limit]]

    async def search(
        self, 
        query: str, 
        limit: int = 5, 
        use_database_fallback: bool = True,
        session: Optional[AsyncSession] = None
    ) -> List[str]:
        """
        Main search method using ordered strategy (fastest to slowest)
        
        Args:
            query: Raw query string
            limit: Maximum candidates to return
            use_database_fallback: Whether to use database for fuzzy search
            session: Optional database session
            
        Returns:
            List of candidate tags
        """
        if not self.loaded:
            logger.warning("Search engine not loaded")
            return []
        
        # Normalize query
        normalized_query = self.normalize_query(query)
        if not normalized_query:
            return []
        
        # Strategy 1: Exact match (fastest)
        exact_match = await self.search_exact(normalized_query)
        if exact_match:
            return [exact_match]
        
        # Strategy 2: Alias lookup (fast)
        alias_match = await self.search_alias(normalized_query)
        if alias_match:
            return [alias_match]
        
        # Strategy 3: Word intersection (medium)
        word_matches = await self.search_word_intersection(normalized_query, limit)
        if word_matches:
            return word_matches[:limit]
        
        # Strategy 4: Prefix matching (medium)
        prefix_matches = await self.search_prefix(normalized_query, limit)
        if prefix_matches:
            return prefix_matches[:limit]
        
        # Strategy 5: Fuzzy search (slow)
        if use_database_fallback and session:
            fuzzy_matches = await self.search_fuzzy_database(normalized_query, limit, session)
            if fuzzy_matches:
                return fuzzy_matches[:limit]
        
        # Fallback: In-memory fuzzy search
        memory_fuzzy_matches = await self.search_fuzzy_memory(normalized_query, limit)
        return memory_fuzzy_matches[:limit]

    def get_stats(self) -> dict:
        """
        Get search engine statistics
        
        Returns:
            Dictionary with engine statistics
        """
        return {
            'loaded': self.loaded,
            'total_tags': self.total_tags,
            'total_aliases': self.total_aliases,
            'trie_size': len(self.prefix_trie),
            'word_index_size': len(self.word_index)
        }


# Global search engine instance
search_engine = TagSearchEngine()