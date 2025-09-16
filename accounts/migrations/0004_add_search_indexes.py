# Generated manually for PostgreSQL full-text search indexes

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_chunk_search_vector'),
    ]

    operations = [
        # Create GIN index for full-text search
        migrations.RunSQL(
            sql="CREATE INDEX idx_chunk_fts ON accounts_chunk USING GIN (search_vector);",
            reverse_sql="DROP INDEX IF EXISTS idx_chunk_fts;",
        ),
        
        # Enable pg_trgm extension for fuzzy search
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            reverse_sql="DROP EXTENSION IF EXISTS pg_trgm;",
        ),
        
        # Create GIN index for fuzzy text search
        migrations.RunSQL(
            sql="CREATE INDEX idx_chunk_text_trgm ON accounts_chunk USING GIN (text gin_trgm_ops);",
            reverse_sql="DROP INDEX IF EXISTS idx_chunk_text_trgm;",
        ),
    ]
