import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from search.models import Document, Chunk
from search.qdrant_service import QdrantService


class Command(BaseCommand):
    help = 'Populate database with man-pages data from chunks.jsonl'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='data/chunks/chunks.jsonl',
            help='Path to the chunks.jsonl file (relative to project root)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before importing'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of chunks to process in each batch'
        )

    def handle(self, *args, **options):
        file_path = Path(options['file'])
        if not file_path.is_absolute():
            file_path = Path(__file__).resolve().parent.parent.parent.parent / file_path
        
        if not file_path.exists():
            raise CommandError(f'File not found: {file_path}')
        
        # Initialize Qdrant service
        try:
            qdrant_service = QdrantService()
            self.stdout.write(self.style.SUCCESS('Connected to Qdrant.'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Could not connect to Qdrant: {e}'))
            self.stdout.write('Continuing without vector indexing...')
            qdrant_service = None
        
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            Chunk.objects.all().delete()
            Document.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Existing data cleared.'))
        
        self.stdout.write(f'Reading data from {file_path}...')
        
        documents = {}
        chunks_to_create = []
        batch_size = options['batch_size']
        processed_count = 0
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line.strip())
                    
                    # Parse document_id to extract document info
                    # Format: "man:6.9:getent:1"
                    doc_id_parts = data['document_id'].split(':')
                    if len(doc_id_parts) != 4 or doc_id_parts[0] != 'man':
                        self.stdout.write(
                            self.style.WARNING(f'Skipping line {line_num}: invalid document_id format')
                        )
                        continue
                    
                    version_tag = doc_id_parts[1]
                    name = doc_id_parts[2]
                    section = doc_id_parts[3]
                    
                    # Create or get document
                    doc_key = (name, section, version_tag)
                    if doc_key not in documents:
                        # Extract title from the first NAME section chunk
                        title = f"{name}({section})"  # Default title
                        
                        document = Document(
                            name=name,
                            section=section,
                            title=title,
                            source_path=f"man{section}/{name}.{section}",
                            license="",  # Will be filled from source if available
                            version_tag=version_tag
                        )
                        documents[doc_key] = document
                    
                    # Create chunk
                    chunk = Chunk(
                        document=documents[doc_key],
                        section_name=data['section_name'],
                        anchor=data['anchor'],
                        text=data['text'],
                        token_count=data['token_count'],
                        embedding_model=qdrant_service.embedding_model_name if qdrant_service else 'jinaai/jina-embeddings-v2-small-en'
                    )
                    chunks_to_create.append(chunk)
                    
                    # Update document title if this is a NAME section
                    if data['section_name'] == 'NAME' and len(data['text']) > len(documents[doc_key].title):
                        documents[doc_key].title = data['text'].strip()
                    
                    processed_count += 1
                    
                    # Process in batches
                    if len(chunks_to_create) >= batch_size:
                        self._process_batch(documents, chunks_to_create, qdrant_service)
                        documents = {}
                        chunks_to_create = []
                        self.stdout.write(f'Processed {processed_count} chunks...')
                
                except json.JSONDecodeError as e:
                    self.stdout.write(
                        self.style.WARNING(f'Skipping line {line_num}: JSON decode error - {e}')
                    )
                    continue
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Skipping line {line_num}: {e}')
                    )
                    continue
        
        # Process remaining items
        if chunks_to_create:
            self._process_batch(documents, chunks_to_create, qdrant_service)
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully processed {processed_count} chunks from {processed_count} lines.')
        )

    def _process_batch(self, documents, chunks_to_create, qdrant_service):
        """Process a batch of documents and chunks."""
        with transaction.atomic():
            # Bulk create documents
            Document.objects.bulk_create(
                documents.values(),
                ignore_conflicts=True
            )
            
            # Get the created documents for foreign key relationships
            created_docs = {}
            for doc_key, doc in documents.items():
                try:
                    created_doc = Document.objects.get(
                        name=doc.name,
                        section=doc.section,
                        version_tag=doc.version_tag
                    )
                    created_docs[doc_key] = created_doc
                except Document.DoesNotExist:
                    continue
            
            # Update chunk documents with created document instances
            for chunk in chunks_to_create:
                doc_key = (chunk.document.name, chunk.document.section, chunk.document.version_tag)
                if doc_key in created_docs:
                    chunk.document = created_docs[doc_key]
            
            # Bulk create chunks
            Chunk.objects.bulk_create(chunks_to_create, ignore_conflicts=True)
            
            # Index chunks in Qdrant if service is available
            if qdrant_service:
                self._index_chunks_in_qdrant(chunks_to_create, qdrant_service)
    
    def _index_chunks_in_qdrant(self, chunks, qdrant_service):
        """Index chunks in Qdrant vector database."""
        for chunk in chunks:
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
                
                # Update chunk with Qdrant ID
                chunk.qdrant_id = qdrant_id
                chunk.save(update_fields=['qdrant_id'])
                
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Failed to index chunk {chunk.id} in Qdrant: {e}')
                )
