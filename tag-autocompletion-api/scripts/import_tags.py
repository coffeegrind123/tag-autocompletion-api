#!/usr/bin/env python3
"""
Script to import Danbooru tag data from CSV files
"""
import asyncio
import sys
import argparse
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.data_importer import DataImporter
from app.db.database import init_db
import structlog

logger = structlog.get_logger()


async def main():
    parser = argparse.ArgumentParser(description="Import Danbooru tag data from CSV files")
    parser.add_argument("csv_files", nargs="+", help="CSV files to import")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before import")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for import")
    
    args = parser.parse_args()
    
    # Validate CSV files exist
    for file_path in args.csv_files:
        if not Path(file_path).exists():
            print(f"Error: CSV file not found: {file_path}")
            return 1
    
    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Import data
        importer = DataImporter(batch_size=args.batch_size)
        total_imported = await importer.import_multiple_files(
            args.csv_files,
            clear_existing=args.clear
        )
        
        print(f"✅ Successfully imported {total_imported} tags")
        
        # Show statistics (non-critical - don't fail if this errors)
        try:
            stats = await importer.get_import_stats()
            print(f"📊 Import statistics:")
            print(f"   Total tags: {stats['total_tags']}")
            print(f"   Type distribution: {stats['type_distribution']}")
            print(f"   Top tags: {stats['top_tags'][:5]}")
        except Exception as e:
            logger.warning("Failed to get import statistics", error=str(e))
            print(f"⚠️  Could not retrieve statistics (import was successful)")
        
        return 0
        
    except Exception as e:
        logger.error("Import failed", error=str(e))
        print(f"❌ Import failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)