from django.core.management.base import BaseCommand
from django.db import transaction

from search.models import Chunk
from search.qdrant_service import QdrantService


class Command(BaseCommand):
    help = 'Populate Qdrant vectors for chunks that are not yet indexed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of chunks to process in each batch'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        # Initialize Qdrant service
        try:
            qdrant_service = QdrantService()
            self.stdout.write(self.style.SUCCESS('Connected to Qdrant.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Could not connect to Qdrant: {e}'))
            return
        
        self.stdout.write('Populating Qdrant vectors...')
        
        # Get chunks that don't have Qdrant IDs yet
        chunks_without_vectors = Chunk.objects.filter(qdrant_id__isnull=True)
        total_chunks = chunks_without_vectors.count()
        
        if total_chunks == 0:
            self.stdout.write(self.style.SUCCESS('All chunks already have Qdrant vectors.'))
            return
        
        self.stdout.write(f'Found {total_chunks} chunks without Qdrant vectors.')
        
        processed = 0
        
        # Process in batches
        while processed < total_chunks:
            batch = chunks_without_vectors[processed:processed + batch_size]
            batch_size_actual = len(batch)
            
            if batch_size_actual == 0:
                break
            
            successful_in_batch = 0
            
            with transaction.atomic():
                for chunk in batch:
                    try:
                        metadata = {
                            'document_name': chunk.document.name,
                            'document_section': chunk.document.section,
                            'document_title': chunk.document.title,
                            'section_name': chunk.section_name,
                            'anchor': chunk.anchor,
                            'token_count': chunk.token_count,
                            'version_tag': chunk.document.version_tag
                        }
                        
                        qdrant_id = qdrant_service.add_chunk(
                            chunk_id=str(chunk.id),
                            text=chunk.text,
                            metadata=metadata
                        )
                        
                        chunk.qdrant_id = qdrant_id
                        chunk.save(update_fields=['qdrant_id'])
                        successful_in_batch += 1
                        
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f'Failed to index chunk {chunk.id}: {e}')
                        )
            
            processed += batch_size_actual
            self.stdout.write(f'Processed {processed}/{total_chunks} chunks... (Successfully indexed: {successful_in_batch}/{batch_size_actual} in this batch)')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully populated Qdrant vectors for {processed} chunks.')
        )
