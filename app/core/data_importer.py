import asyncio
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
import structlog

from app.models.tag import Tag
from app.core.csv_parser import DanbooruCSVParser
from app.db.database import async_session_maker

logger = structlog.get_logger()


class DataImporter:
    """
    Handles importing Danbooru tag data from CSV files into the database
    """

    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size
        self.parser = DanbooruCSVParser()

    async def clear_existing_data(self, session: AsyncSession) -> None:
        """
        Clear all existing tag data from database
        
        Args:
            session: Database session
        """
        logger.info("Clearing existing tag data")
        await session.execute(delete(Tag))
        await session.commit()
        logger.info("Existing tag data cleared")

    async def import_csv_file(
        self, 
        file_path: str, 
        clear_existing: bool = False,
        session: Optional[AsyncSession] = None
    ) -> int:
        """
        Import tags from a single CSV file
        
        Args:
            file_path: Path to CSV file
            clear_existing: Whether to clear existing data first
            session: Optional database session (will create if not provided)
            
        Returns:
            Number of tags imported
        """
        if session is None:
            async with async_session_maker() as session:
                return await self._import_csv_file_with_session(
                    file_path, clear_existing, session
                )
        else:
            return await self._import_csv_file_with_session(
                file_path, clear_existing, session
            )

    async def _import_csv_file_with_session(
        self, 
        file_path: str, 
        clear_existing: bool, 
        session: AsyncSession
    ) -> int:
        """
        Internal method to import CSV with existing session
        """
        if clear_existing:
            await self.clear_existing_data(session)

        logger.info("Starting CSV import", file_path=file_path)
        
        batch = []
        imported_count = 0
        skipped_count = 0
        
        try:
            for tag_data in self.parser.parse_csv_file(file_path):
                if not self.parser.validate_tag_data(tag_data):
                    skipped_count += 1
                    logger.warning("Skipping invalid tag data", tag_data=tag_data)
                    continue
                
                batch.append(tag_data)
                
                # Process batch when full
                if len(batch) >= self.batch_size:
                    batch_imported = await self._insert_batch(session, batch)
                    imported_count += batch_imported
                    batch = []
                    
                    logger.info("Batch processed", 
                               batch_size=batch_imported,
                               total_imported=imported_count)
            
            # Process remaining items
            if batch:
                batch_imported = await self._insert_batch(session, batch)
                imported_count += batch_imported
                
            await session.commit()
            
        except Exception as e:
            logger.error("Import failed", file_path=file_path, error=str(e))
            await session.rollback()
            raise
        
        logger.info("CSV import completed", 
                   file_path=file_path,
                   imported_count=imported_count,
                   skipped_count=skipped_count)
        
        return imported_count

    async def _insert_batch(self, session: AsyncSession, batch: List[dict]) -> int:
        """
        Insert a batch of tag data using PostgreSQL upsert
        
        Args:
            session: Database session
            batch: List of tag data dictionaries
            
        Returns:
            Number of records inserted/updated
        """
        if not batch:
            return 0
            
        try:
            # Use PostgreSQL INSERT ... ON CONFLICT for upsert
            stmt = insert(Tag).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=['tag'],
                set_={
                    'type': stmt.excluded.type,
                    'count': stmt.excluded.count,
                    'aliases': stmt.excluded.aliases
                }
            )
            
            result = await session.execute(stmt)
            return result.rowcount
            
        except Exception as e:
            logger.error("Batch insert failed", batch_size=len(batch), error=str(e))
            raise

    async def import_multiple_files(
        self, 
        file_paths: List[str], 
        clear_existing: bool = False
    ) -> int:
        """
        Import tags from multiple CSV files
        
        Args:
            file_paths: List of CSV file paths
            clear_existing: Whether to clear existing data first
            
        Returns:
            Total number of tags imported
        """
        total_imported = 0
        
        async with async_session_maker() as session:
            # Clear existing data only once
            if clear_existing:
                await self.clear_existing_data(session)
            
            for file_path in file_paths:
                try:
                    count = await self._import_csv_file_with_session(
                        file_path, False, session  # Don't clear for subsequent files
                    )
                    total_imported += count
                except Exception as e:
                    logger.error("Failed to import file", 
                               file_path=file_path, 
                               error=str(e))
                    # Continue with other files
                    
        logger.info("Multiple file import completed", 
                   total_files=len(file_paths),
                   total_imported=total_imported)
        
        return total_imported

    async def get_import_stats(self, session: Optional[AsyncSession] = None) -> dict:
        """
        Get statistics about imported data
        
        Args:
            session: Optional database session
            
        Returns:
            Dictionary with import statistics
        """
        if session is None:
            async with async_session_maker() as session:
                return await self._get_import_stats_with_session(session)
        else:
            return await self._get_import_stats_with_session(session)

    async def _get_import_stats_with_session(self, session: AsyncSession) -> dict:
        """
        Internal method to get stats with existing session
        """
        from sqlalchemy import func
        
        # Total count
        total_result = await session.execute(select(func.count(Tag.id)))
        total_count = total_result.scalar()
        
        # Count by type
        type_result = await session.execute(
            select(Tag.type, func.count(Tag.id)).group_by(Tag.type)
        )
        type_counts = {row[0]: row[1] for row in type_result.fetchall()}
        
        # Top tags by count
        top_tags_result = await session.execute(
            select(Tag.tag, Tag.count)
            .order_by(Tag.count.desc())
            .limit(10)
        )
        top_tags = [(row[0], row[1]) for row in top_tags_result.fetchall()]
        
        return {
            'total_tags': total_count,
            'type_distribution': type_counts,
            'top_tags': top_tags
        }


# Usage example for CLI:
async def main():
    """
    Example usage for command-line import
    """
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m app.core.data_importer <csv_file1> [csv_file2] ...")
        return
    
    file_paths = sys.argv[1:]
    importer = DataImporter()
    
    try:
        total_imported = await importer.import_multiple_files(
            file_paths, 
            clear_existing=True
        )
        print(f"Successfully imported {total_imported} tags")
        
        # Show stats
        stats = await importer.get_import_stats()
        print(f"Import statistics: {stats}")
        
    except Exception as e:
        print(f"Import failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    asyncio.run(main())