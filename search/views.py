from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json

from .search import ManPageSearch


@login_required
def search_view(request):
    """Search man-pages with vector similarity search"""
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'vector')
    limit = int(request.GET.get('limit', 20))
    score_threshold = float(request.GET.get('threshold', 0.7))
    
    results = []
    stats = None
    
    if query:
        searcher = ManPageSearch()
        chunks = searcher.search_chunks(query, search_type, limit, score_threshold)
        
        # Convert to serializable format
        results = []
        for chunk in chunks:
            results.append({
                'id': str(chunk.id),
                'document_name': chunk.document.name,
                'document_section': chunk.document.section,
                'document_title': chunk.document.title,
                'section_name': chunk.section_name,
                'anchor': chunk.anchor,
                'text': chunk.text[:500] + '...' if len(chunk.text) > 500 else chunk.text,
                'token_count': chunk.token_count,
                'similarity': getattr(chunk, 'similarity', None),
                'qdrant_id': chunk.qdrant_id,
            })
        
        stats = searcher.get_document_stats()
    
    context = {
        'query': query,
        'search_type': search_type,
        'results': results,
        'stats': stats,
        'score_threshold': score_threshold,
    }
    
    return render(request, "search/search.html", context)


@csrf_exempt
@login_required
def search_api(request):
    """API endpoint for search functionality"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        query = data.get('query', '').strip()
        search_type = data.get('type', 'vector')
        limit = int(data.get('limit', 20))
        score_threshold = float(data.get('threshold', 0.7))
        
        if not query:
            return JsonResponse({'error': 'Query is required'}, status=400)
        
        searcher = ManPageSearch()
        chunks = searcher.search_chunks(query, search_type, limit, score_threshold)
        
        results = []
        for chunk in chunks:
            results.append({
                'id': str(chunk.id),
                'document_name': chunk.document.name,
                'document_section': chunk.document.section,
                'document_title': chunk.document.title,
                'section_name': chunk.section_name,
                'anchor': chunk.anchor,
                'text': chunk.text,
                'token_count': chunk.token_count,
                'similarity': getattr(chunk, 'similarity', None),
                'qdrant_id': chunk.qdrant_id,
            })
        
        return JsonResponse({
            'results': results,
            'total': len(results),
            'query': query,
            'search_type': search_type,
            'score_threshold': score_threshold
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)