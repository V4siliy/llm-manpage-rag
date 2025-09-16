from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity
from django.db.models import Q, F
from django.conf import settings

from accounts.models import Chunk, Document


class ManPageSearch:
    """Utility class for searching man-pages with full-text and fuzzy search."""
    
    def __init__(self):
        self.search_config = getattr(settings, 'POSTGRES_FULL_TEXT_SEARCH_CONFIG', 'simple')
    
    def search_chunks(self, query, search_type='fulltext', limit=20, min_rank=0.1):
        """
        Search chunks using full-text search or fuzzy search.
        
        Args:
            query (str): Search query
            search_type (str): 'fulltext', 'fuzzy', or 'both'
            limit (int): Maximum number of results
            min_rank (float): Minimum rank for full-text search results
        
        Returns:
            QuerySet: Filtered chunks with search results
        """
        if search_type == 'fulltext':
            return self._fulltext_search(query, limit, min_rank)
        elif search_type == 'fuzzy':
            return self._fuzzy_search(query, limit)
        elif search_type == 'both':
            # Combine both search types
            fulltext_results = self._fulltext_search(query, limit, min_rank)
            fuzzy_results = self._fuzzy_search(query, limit)
            
            # Get IDs from both result sets
            fulltext_ids = set(fulltext_results.values_list('id', flat=True))
            fuzzy_ids = set(fuzzy_results.values_list('id', flat=True))
            
            # Return combined unique results
            combined_ids = fulltext_ids.union(fuzzy_ids)
            return Chunk.objects.filter(id__in=combined_ids).select_related('document')
        else:
            raise ValueError("search_type must be 'fulltext', 'fuzzy', or 'both'")
    
    def _fulltext_search(self, query, limit, min_rank):
        """Perform full-text search using PostgreSQL search vectors."""
        search_query = SearchQuery(query, config=self.search_config)
        
        return Chunk.objects.annotate(
            rank=SearchRank(F('search_vector'), search_query)
        ).filter(
            search_vector=search_query,
            rank__gte=min_rank
        ).order_by('-rank').select_related('document')[:limit]
    
    def _fuzzy_search(self, query, limit):
        """Perform fuzzy search using trigram similarity."""
        return Chunk.objects.annotate(
            similarity=TrigramSimilarity('text', query)
        ).filter(
            similarity__gt=0.1  # Minimum similarity threshold
        ).order_by('-similarity').select_related('document')[:limit]
    
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
            ).order_by('-count')[:10]
        }
        
        return stats
