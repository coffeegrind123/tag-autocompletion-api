#!/bin/bash
set -e

# Check if auto-import is enabled (default: true)
AUTO_IMPORT_CSV="${AUTO_IMPORT_CSV:-true}"

if [ "$AUTO_IMPORT_CSV" != "true" ]; then
    echo "ℹ️  Auto-import disabled (AUTO_IMPORT_CSV=$AUTO_IMPORT_CSV), skipping CSV import"
else
    echo "🔍 Checking if tags are already imported..."
    
    # Check tag count in database
    TAG_COUNT=$(python -c "
import asyncio
import sys
sys.path.append('.')
from app.db.database import async_session_maker
from app.models.tag import Tag
from sqlalchemy import select, func

async def get_tag_count():
    try:
        async with async_session_maker() as session:
            result = await session.execute(select(func.count(Tag.id)))
            return result.scalar()
    except Exception as e:
        print(f'Error checking database: {e}', file=sys.stderr)
        return -1

count = asyncio.run(get_tag_count())
print(count)
    ")
    
    if [ "$TAG_COUNT" -gt 0 ] 2>/dev/null; then
        echo "ℹ️  Database already contains $TAG_COUNT tags, skipping import"
    elif [ "$TAG_COUNT" -eq 0 ] 2>/dev/null; then
        echo "🔍 Database is empty, checking for CSV files to import..."
        
        # Look for CSV files in the data directory
        CSV_FILES=(data/*.csv)
        
        # Check if any CSV files exist (and it's not just the glob pattern)
        if [ -e "${CSV_FILES[0]}" ]; then
            echo "📂 Found CSV files: ${CSV_FILES[@]}"
            echo "🗄️  Starting import..."
            
            # Import all CSV files found
            python scripts/import_tags.py "${CSV_FILES[@]}" --clear
            echo "✅ CSV import completed!"
        else
            echo "ℹ️  No CSV files found in data/ directory, skipping import"
        fi
    else
        echo "⚠️  Could not check database (TAG_COUNT=$TAG_COUNT), proceeding with CSV check..."
        
        # Look for CSV files in the data directory
        CSV_FILES=(data/*.csv)
        
        # Check if any CSV files exist (and it's not just the glob pattern)
        if [ -e "${CSV_FILES[0]}" ]; then
            echo "📂 Found CSV files: ${CSV_FILES[@]}"
            echo "🗄️  Starting import..."
            
            # Import all CSV files found
            python scripts/import_tags.py "${CSV_FILES[@]}" --clear
            echo "✅ CSV import completed!"
        else
            echo "ℹ️  No CSV files found in data/ directory, skipping import"
        fi
    fi
fi

echo "🚀 Starting API server..."