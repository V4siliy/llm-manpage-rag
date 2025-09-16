from django.db.models import Q, F
from django.conf import settings

from search.models import Chunk, Document
from search.qdrant_service import QdrantService


class ManPageSearch:
    """Utility class for searching man-pages with vector search using Qdrant."""
    
    def __init__(self):
        self.qdrant_service = QdrantService()
    
    def search_chunks(self, query, search_type='vector', limit=20, score_threshold=0.7):
        """
        Search chunks using vector similarity search.
        
        Args:
            query (str): Search query
            search_type (str): 'vector' (only supported type now)
            limit (int): Maximum number of results
            score_threshold (float): Minimum similarity score
        
        Returns:
            QuerySet: Filtered chunks with search results
        """
        if search_type == 'vector':
            return self._vector_search(query, limit, score_threshold)
        else:
            raise ValueError("search_type must be 'vector'")
    
    def _vector_search(self, query, limit, score_threshold):
        """Perform vector similarity search using Qdrant."""
        try:
            # Search in Qdrant
            qdrant_results = self.qdrant_service.search_similar(
                query=query,
                limit=limit,
                score_threshold=score_threshold
            )
            
            if not qdrant_results:
                return Chunk.objects.none()
            
            # Get chunk IDs from Qdrant results
            chunk_ids = [result['chunk_id'] for result in qdrant_results]
            
            # Get chunks from database and preserve order
            chunks = Chunk.objects.filter(id__in=chunk_ids).select_related('document')
            
            # Create a mapping to preserve Qdrant order and scores
            chunk_map = {str(chunk.id): chunk for chunk in chunks}
            ordered_chunks = []
            
            for result in qdrant_results:
                chunk_id = result['chunk_id']
                if chunk_id in chunk_map:
                    chunk = chunk_map[chunk_id]
                    # Add similarity score as an attribute
                    chunk.similarity = result['score']
                    ordered_chunks.append(chunk)
            
            return ordered_chunks
            
        except Exception as e:
            # Fallback to text search if Qdrant fails
            return self._fallback_text_search(query, limit)
    
    def _fallback_text_search(self, query, limit):
        """Fallback text search when Qdrant is unavailable."""
        return Chunk.objects.filter(
            Q(text__icontains=query) |
            Q(section_name__icontains=query) |
            Q(document__name__icontains=query) |
            Q(document__title__icontains=query)
        ).select_related('document')[:limit]
    
    def search_by_document(self, document_name=None, section=None, version_tag=None):
        """
        Search chunks by document criteria.
        
        Args:
            document_name (str): Name of the man-page
            section (str): Section number
            version_tag (str): Version tag
        
        Returns:
            QuerySet: Filtered chunks
        """
        filters = {}
        
        if document_name:
            filters['document__name__icontains'] = document_name
        if section:
            filters['document__section'] = section
        if version_tag:
            filters['document__version_tag'] = version_tag
        
        return Chunk.objects.filter(**filters).select_related('document')
    
    def search_by_section(self, section_name):
        """
        Search chunks by section name (e.g., 'NAME', 'SYNOPSIS').
        
        Args:
            section_name (str): Section name to search for
        
        Returns:
            QuerySet: Filtered chunks
        """
        return Chunk.objects.filter(
            section_name__icontains=section_name
        ).select_related('document')
    
    def search_with_filters(self, query, filters=None, limit=20, score_threshold=0.7):
        """
        Search with additional filters using Qdrant.
        
        Args:
            query (str): Search query
            filters (dict): Additional filters to apply
            limit (int): Maximum number of results
            score_threshold (float): Minimum similarity score
        
        Returns:
            List: Search results with similarity scores
        """
        try:
            qdrant_filters = {}
            if filters:
                # Map Django model fields to Qdrant payload fields
                field_mapping = {
                    'document_name': 'document_name',
                    'document_section': 'document_section',
                    'section_name': 'section_name',
                    'version_tag': 'version_tag'
                }
                
                for key, value in filters.items():
                    if key in field_mapping:
                        qdrant_filters[field_mapping[key]] = value
            
            return self.qdrant_service.search_with_filters(
                query=query,
                filters=qdrant_filters,
                limit=limit
            )
            
        except Exception as e:
            # Fallback to database search
            queryset = Chunk.objects.select_related('document')
            if filters:
                for key, value in filters.items():
                    if hasattr(Chunk, key):
                        queryset = queryset.filter(**{key: value})
                    elif key.startswith('document_'):
                        field_name = key.replace('document_', 'document__')
                        queryset = queryset.filter(**{field_name: value})
            
            return queryset[:limit]
    
    def get_document_stats(self):
        """Get statistics about documents and chunks."""
        from django.db.models import Count
        
        total_documents = Document.objects.count()
        total_chunks = Chunk.objects.count()
        
        # Calculate average chunks per document manually
        avg_chunks_per_document = 0
        if total_documents > 0:
            avg_chunks_per_document = total_chunks / total_documents
        
        stats = {
            'total_documents': total_documents,
            'total_chunks': total_chunks,
            'avg_chunks_per_document': avg_chunks_per_document,
            'sections': Chunk.objects.values('section_name').annotate(
                count=Count('id')
            ).order_by('-count')[:10],
            'qdrant_info': self.qdrant_service.get_collection_info()
        }
        
        return stats
