from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Count, Q
from django.utils import timezone
import json

from .search import ManPageSearch
from .rag_service import ManPageRAGService
from .models import EvaluationRun, EvaluationResult, EvaluationQuery


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


@login_required
def ask_view(request):
    """Ask questions and get answers using RAG workflow"""
    from django.conf import settings
    import json
    context = {
        'loading_messages_json': json.dumps(settings.FUNNY_LOADING_SENTENCES)
    }
    return render(request, "search/ask.html", context)


@csrf_exempt
@login_required
def ask_api(request):
    """API endpoint for asking questions with RAG"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        
        if not question:
            return JsonResponse({'error': 'Question is required'}, status=400)
        
        rag_service = ManPageRAGService()
        result = rag_service.ask_question(question)
        
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@login_required
def loading_message_api(request):
    """API endpoint to get random loading messages"""
    try:
        rag_service = ManPageRAGService()
        message = rag_service.get_random_loading_message()
        return JsonResponse({'message': message})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Admin-only evaluation views
@staff_member_required
def evaluation_dashboard(request):
    """Dashboard showing all evaluation runs and their metrics"""
    evaluation_runs = EvaluationRun.objects.all().order_by('-created_at')
    
    # Get summary statistics
    total_runs = evaluation_runs.count()
    completed_runs = evaluation_runs.filter(status='completed').count()
    running_runs = evaluation_runs.filter(status='running').count()
    failed_runs = evaluation_runs.filter(status='failed').count()
    
    # Get latest metrics if any completed runs exist
    latest_metrics = None
    if completed_runs > 0:
        latest_run = evaluation_runs.filter(status='completed').first()
        latest_metrics = {
            'recall_at_5': latest_run.recall_at_5,
            'ndcg_at_5': latest_run.ndcg_at_5,
            'mrr': latest_run.mrr,
            'total_queries': latest_run.total_queries,
            'successful_queries': latest_run.successful_queries,
        }
    
    context = {
        'evaluation_runs': evaluation_runs,
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'running_runs': running_runs,
        'failed_runs': failed_runs,
        'latest_metrics': latest_metrics,
    }
    
    return render(request, "search/evaluation_dashboard.html", context)


@staff_member_required
def evaluation_run_detail(request, run_id):
    """Detailed view of a specific evaluation run"""
    evaluation_run = get_object_or_404(EvaluationRun, id=run_id)
    results = evaluation_run.results.all().order_by('-created_at')
    
    # Calculate additional statistics
    results_stats = results.aggregate(
        avg_recall_at_5=Avg('recall_at_5'),
        avg_ndcg_at_5=Avg('ndcg_at_5'),
        avg_mrr=Avg('mrr'),
        total_results=Count('id'),
        successful_results=Count('id', filter=Q(success=True)),
        found_results=Count('id', filter=Q(target_chunk_found=True)),
    )
    
    # Get distribution of ranks for found chunks
    rank_distribution = {}
    for result in results.filter(target_chunk_found=True):
        rank = result.target_chunk_rank
        if rank:
            rank_range = f"{(rank-1)//5*5 + 1}-{((rank-1)//5 + 1)*5}"
            rank_distribution[rank_range] = rank_distribution.get(rank_range, 0) + 1
    
    # Calculate success rate percentage
    success_rate = None
    if evaluation_run.total_queries > 0:
        success_rate = (evaluation_run.successful_queries / evaluation_run.total_queries) * 100
    
    context = {
        'evaluation_run': evaluation_run,
        'results': results,
        'results_stats': results_stats,
        'rank_distribution': rank_distribution,
        'success_rate': success_rate,
    }
    
    return render(request, "search/evaluation_run_detail.html", context)


@staff_member_required
def evaluation_comparison(request):
    """Compare metrics across different evaluation runs"""
    evaluation_runs = EvaluationRun.objects.filter(status='completed').order_by('-created_at')
    
    # Prepare data for charts
    chart_data = {
        'labels': [],
        'recall_at_5': [],
        'ndcg_at_5': [],
        'mrr': [],
        'success_rate': [],
    }
    
    for run in evaluation_runs:
        chart_data['labels'].append(f"{run.name} ({run.created_at.strftime('%Y-%m-%d')})")
        chart_data['recall_at_5'].append(float(run.recall_at_5) if run.recall_at_5 else 0)
        chart_data['ndcg_at_5'].append(float(run.ndcg_at_5) if run.ndcg_at_5 else 0)
        chart_data['mrr'].append(float(run.mrr) if run.mrr else 0)
        success_rate = (run.successful_queries / run.total_queries * 100) if run.total_queries > 0 else 0
        chart_data['success_rate'].append(success_rate)
    
    context = {
        'evaluation_runs': evaluation_runs,
        'chart_data': json.dumps(chart_data),
    }
    
    return render(request, "search/evaluation_comparison.html", context)


@staff_member_required
def evaluation_api(request):
    """API endpoint for evaluation data"""
    if request.method == 'GET':
        run_id = request.GET.get('run_id')
        
        if run_id:
            # Get specific run data
            evaluation_run = get_object_or_404(EvaluationRun, id=run_id)
            results = evaluation_run.results.all()
            
            data = {
                'run': {
                    'id': str(evaluation_run.id),
                    'name': evaluation_run.name,
                    'status': evaluation_run.status,
                    'search_type': evaluation_run.search_type,
                    'score_threshold': evaluation_run.score_threshold,
                    'limit': evaluation_run.limit,
                    'embedding_model': evaluation_run.embedding_model,
                    'created_at': evaluation_run.created_at.isoformat(),
                    'completed_at': evaluation_run.completed_at.isoformat() if evaluation_run.completed_at else None,
                    'metrics': {
                        'recall_at_1': evaluation_run.recall_at_1,
                        'recall_at_5': evaluation_run.recall_at_5,
                        'recall_at_10': evaluation_run.recall_at_10,
                        'recall_at_20': evaluation_run.recall_at_20,
                        'ndcg_at_1': evaluation_run.ndcg_at_1,
                        'ndcg_at_5': evaluation_run.ndcg_at_5,
                        'ndcg_at_10': evaluation_run.ndcg_at_10,
                        'ndcg_at_20': evaluation_run.ndcg_at_20,
                        'mrr': evaluation_run.mrr,
                    },
                    'stats': {
                        'total_queries': evaluation_run.total_queries,
                        'successful_queries': evaluation_run.successful_queries,
                        'failed_queries': evaluation_run.failed_queries,
                    }
                },
                'results': []
            }
            
            for result in results:
                data['results'].append({
                    'id': str(result.id),
                    'query': result.query.query,
                    'document_id': result.query.document_id,
                    'target_section': result.query.target_section,
                    'target_anchor': result.query.target_anchor,
                    'target_chunk_found': result.target_chunk_found,
                    'target_chunk_rank': result.target_chunk_rank,
                    'target_chunk_score': result.target_chunk_score,
                    'success': result.success,
                    'error_message': result.error_message,
                    'metrics': {
                        'recall_at_5': result.recall_at_5,
                        'ndcg_at_5': result.ndcg_at_5,
                        'mrr': result.mrr,
                    }
                })
            
            return JsonResponse(data)
        
        else:
            # Get all runs summary
            runs = EvaluationRun.objects.all().order_by('-created_at')
            data = {
                'runs': []
            }
            
            for run in runs:
                data['runs'].append({
                    'id': str(run.id),
                    'name': run.name,
                    'status': run.status,
                    'search_type': run.search_type,
                    'created_at': run.created_at.isoformat(),
                    'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                    'metrics': {
                        'recall_at_5': run.recall_at_5,
                        'ndcg_at_5': run.ndcg_at_5,
                        'mrr': run.mrr,
                    },
                    'stats': {
                        'total_queries': run.total_queries,
                        'successful_queries': run.successful_queries,
                        'failed_queries': run.failed_queries,
                    }
                })
            
            return JsonResponse(data)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)