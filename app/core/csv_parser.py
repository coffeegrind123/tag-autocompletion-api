import re
from typing import Dict, List, Iterator
import structlog

logger = structlog.get_logger()


class DanbooruCSVParser:
    """
    Parser for Danbooru CSV files with format: "tag type count aliases"
    Handles space-separated format with comma-delimited aliases
    """

    @staticmethod
    def process_tag_string(tag_str: str) -> str:
        """
        Process tag string: underscores -> spaces, escape parentheses
        
        Args:
            tag_str: Raw tag string from CSV
            
        Returns:
            Processed tag string
        """
        # Convert underscores to spaces
        tag_str = tag_str.replace('_', ' ')
        
        # Escape parentheses for safer handling
        tag_str = tag_str.replace('(', r'\(').replace(')', r'\)')
        
        return tag_str.strip()

    @classmethod
    def parse_csv_line(cls, line: str) -> Dict:
        """
        Parse a single CSV line with format: "tag,type,count,aliases" or "tag type count aliases"
        
        Args:
            line: Single line from CSV file
            
        Returns:
            Dictionary with parsed tag data
            
        Raises:
            ValueError: If line format is invalid
        """
        line = line.strip()
        if not line or line.startswith('tag,') or line.startswith('tag '):  # Skip header
            return None
        
        # Detect format: comma-separated CSV or space-separated
        if ',' in line and not line.startswith('"'):
            # CSV format: tag,type,count,aliases
            parts = line.split(',', 3)  # Split into max 4 parts
            if len(parts) < 3:
                raise ValueError(f"Invalid CSV format: {line}")
            
            try:
                raw_tag = parts[0].strip()
                type_val = int(parts[1].strip())
                count = int(parts[2].strip())
                
                # Parse aliases (4th column, comma-delimited within quotes or not)
                aliases_str = parts[3].strip() if len(parts) > 3 else ""
                # Remove quotes if present
                if aliases_str.startswith('"') and aliases_str.endswith('"'):
                    aliases_str = aliases_str[1:-1]
                raw_aliases = [alias.strip() for alias in aliases_str.split(',') if alias.strip()]
                
            except (ValueError, IndexError) as e:
                raise ValueError(f"Failed to parse CSV line '{line}': {e}")
        else:
            # Space-separated format: tag type count aliases
            parts = line.split(' ')
            if len(parts) < 3:
                raise ValueError(f"Invalid space-separated format: {line}")
            
            try:
                raw_tag = parts[0]
                type_val = int(parts[1])
                count = int(parts[2])
                
                # Parse aliases (everything after count, comma-delimited)
                aliases_str = ' '.join(parts[3:]) if len(parts) > 3 else ""
                raw_aliases = [alias.strip() for alias in aliases_str.split(',') if alias.strip()]
                
            except (ValueError, IndexError) as e:
                raise ValueError(f"Failed to parse space-separated line '{line}': {e}")
        
        # Process tag and aliases
        processed_tag = cls.process_tag_string(raw_tag)
        processed_aliases = [cls.process_tag_string(alias) for alias in raw_aliases]
        
        return {
            'tag': processed_tag,
            'type': type_val,
            'count': count,
            'aliases': processed_aliases
        }

    @classmethod
    def parse_csv_file(cls, file_path: str) -> Iterator[Dict]:
        """
        Parse entire CSV file and yield tag data dictionaries
        
        Args:
            file_path: Path to CSV file
            
        Yields:
            Dictionary with parsed tag data for each valid line
        """
        logger.info("Starting CSV file parsing", file_path=file_path)
        
        parsed_count = 0
        error_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    try:
                        tag_data = cls.parse_csv_line(line)
                        if tag_data:  # Skip None (header/empty lines)
                            parsed_count += 1
                            yield tag_data
                    except ValueError as e:
                        error_count += 1
                        logger.warning("Failed to parse line", 
                                     line_num=line_num, 
                                     error=str(e),
                                     line=line.strip()[:100])  # Limit line length in logs
                        
        except FileNotFoundError:
            logger.error("CSV file not found", file_path=file_path)
            raise
        except Exception as e:
            logger.error("Unexpected error parsing CSV", file_path=file_path, error=str(e))
            raise
            
        logger.info("CSV parsing completed", 
                   file_path=file_path,
                   parsed_count=parsed_count, 
                   error_count=error_count)

    @classmethod
    def validate_tag_data(cls, tag_data: Dict) -> bool:
        """
        Validate parsed tag data
        
        Args:
            tag_data: Parsed tag dictionary
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['tag', 'type', 'count', 'aliases']
        
        # Check required fields exist
        if not all(field in tag_data for field in required_fields):
            return False
            
        # Validate field types
        if not isinstance(tag_data['tag'], str) or not tag_data['tag'].strip():
            return False
            
        if not isinstance(tag_data['type'], int) or tag_data['type'] < 0:
            return False
            
        if not isinstance(tag_data['count'], int) or tag_data['count'] < 0:
            return False
            
        if not isinstance(tag_data['aliases'], list):
            return False
            
        # Validate aliases are strings
        if not all(isinstance(alias, str) for alias in tag_data['aliases']):
            return False
            
        return True


# Sample CSV data formats supported:
# CSV format: tag,type,count,aliases
# large_breasts,0,1464796,"large_breast,big_breasts,large_tits,large_boobs"
# school_uniform,0,892543,"uniform,school_clothes"
# 1girl,0,2856234,solo_girl
# 
# Space-separated format: tag type count aliases
# large_breasts 0 1464796 large_breast,big_breasts,large_tits,large_boobs
# school_uniform 0 892543 uniform,school_clothes
# 1girl 0 2856234 solo_girl,single_girl