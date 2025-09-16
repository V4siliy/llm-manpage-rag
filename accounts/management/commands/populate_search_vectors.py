from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector
from django.db import transaction

from accounts.models import Chunk


class Command(BaseCommand):
    help = 'Populate search vectors for full-text search'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of chunks to process in each batch'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        self.stdout.write('Populating search vectors...')
        
        # Get chunks that don't have search vectors yet
        chunks_without_vectors = Chunk.objects.filter(search_vector__isnull=True)
        total_chunks = chunks_without_vectors.count()
        
        if total_chunks == 0:
            self.stdout.write(self.style.SUCCESS('All chunks already have search vectors.'))
            return
        
        self.stdout.write(f'Found {total_chunks} chunks without search vectors.')
        
        processed = 0
        
        # Process in batches
        while processed < total_chunks:
            batch = chunks_without_vectors[processed:processed + batch_size]
            
            with transaction.atomic():
                for chunk in batch:
                    # Create search vector from text using 'simple' config
                    chunk.search_vector = SearchVector('text', config='simple')
                    chunk.save(update_fields=['search_vector'])
            
            processed += len(batch)
            self.stdout.write(f'Processed {processed}/{total_chunks} chunks...')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully populated search vectors for {total_chunks} chunks.')
        )
