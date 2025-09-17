"""
Evaluation utilities for computing search metrics.
"""
import math
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone

from .models import EvaluationRun, EvaluationResult, EvaluationQuery, Chunk
from .search import ManPageSearch


def compute_recall_at_k(retrieved_chunk_ids: List[str], target_chunk_id: str, k: int) -> float:
    """
    Compute Recall@k metric.
    
    Args:
        retrieved_chunk_ids: List of retrieved chunk IDs in order
        target_chunk_id: ID of the target chunk that should be found
        k: Number of top results to consider
    
    Returns:
        Recall@k value (0.0 to 1.0)
    """
    if not retrieved_chunk_ids or not target_chunk_id:
        return 0.0
    
    # Check if target chunk is in top-k results
    top_k_ids = retrieved_chunk_ids[:k]
    return 1.0 if target_chunk_id in top_k_ids else 0.0


def compute_ndcg_at_k(retrieved_chunk_ids: List[str], target_chunk_id: str, k: int) -> float:
    """
    Compute nDCG@k metric.
    
    Args:
        retrieved_chunk_ids: List of retrieved chunk IDs in order
        target_chunk_id: ID of the target chunk that should be found
        k: Number of top results to consider
    
    Returns:
        nDCG@k value (0.0 to 1.0)
    """
    if not retrieved_chunk_ids or not target_chunk_id:
        return 0.0
    
    # Binary relevance: 1 if target chunk is found, 0 otherwise
    def relevance(chunk_id: str) -> float:
        return 1.0 if chunk_id == target_chunk_id else 0.0
    
    # Compute DCG@k
    dcg = 0.0
    for i, chunk_id in enumerate(retrieved_chunk_ids[:k]):
        dcg += relevance(chunk_id) / math.log2(i + 2)  # i+2 because log2(1) = 0
    
    # Compute IDCG@k (ideal DCG)
    # For binary relevance, IDCG@k = 1.0 if k >= 1, 0.0 otherwise
    idcg = 1.0 if k >= 1 else 0.0
    
    # Compute nDCG@k
    return dcg / idcg if idcg > 0 else 0.0


def compute_mrr(retrieved_chunk_ids: List[str], target_chunk_id: str) -> float:
    """
    Compute Mean Reciprocal Rank (MRR) metric.
    
    Args:
        retrieved_chunk_ids: List of retrieved chunk IDs in order
        target_chunk_id: ID of the target chunk that should be found
    
    Returns:
        MRR value (0.0 to 1.0)
    """
    if not retrieved_chunk_ids or not target_chunk_id:
        return 0.0
    
    # Find the rank of the target chunk (1-indexed)
    try:
        rank = retrieved_chunk_ids.index(target_chunk_id) + 1
        return 1.0 / rank
    except ValueError:
        # Target chunk not found
        return 0.0


def find_target_chunk(query: EvaluationQuery) -> Optional[Chunk]:
    """
    Find the target chunk for a given evaluation query.
    
    Args:
        query: EvaluationQuery object
    
    Returns:
        Chunk object if found, None otherwise
    """
    try:
        # Parse document ID to extract name, section, and version
        # Format: "man:6.9:function_name:section"
        parts = query.document_id.split(':')
        if len(parts) >= 4:
            version = parts[1]
            name = parts[2]
            section = parts[3]
            
            # Find the chunk with matching anchor
            chunk = Chunk.objects.filter(
                document__name=name,
                document__section=section,
                document__version_tag=version,
                anchor=query.target_anchor
            ).first()
            
            return chunk
    except Exception:
        pass
    
    return None


def evaluate_single_query(query: EvaluationQuery, search_type: str = 'vector', 
                         score_threshold: float = 0.7, limit: int = 20, searcher=None) -> Dict[str, Any]:
    """
    Evaluate a single query against the search system.
    
    Args:
        query: EvaluationQuery object
        search_type: Type of search to perform
        score_threshold: Score threshold for search
        limit: Maximum number of results to retrieve
    
    Returns:
        Dictionary containing evaluation results
    """
    result = {
        'success': False,
        'target_chunk_found': False,
        'target_chunk_rank': None,
        'target_chunk_score': None,
        'retrieved_chunks': [],
        'metrics': {},
        'error_message': None
    }
    
    try:
        # Find the target chunk
        target_chunk = find_target_chunk(query)
        if not target_chunk:
            result['error_message'] = f"Target chunk not found for query: {query.query}"
            return result
        
        # Perform search
        if searcher is None:
            searcher = ManPageSearch()
        chunks = searcher.search_chunks(query.query, search_type, limit, score_threshold)
        
        # Extract chunk IDs and scores
        retrieved_chunk_ids = []
        retrieved_chunks_data = []
        
        for i, chunk in enumerate(chunks):
            chunk_data = {
                'id': str(chunk.id),
                'rank': i + 1,
                'score': getattr(chunk, 'similarity', None)
            }
            retrieved_chunk_ids.append(str(chunk.id))
            retrieved_chunks_data.append(chunk_data)
        
        result['retrieved_chunks'] = retrieved_chunks_data
        
        # Check if target chunk was found
        target_chunk_id = str(target_chunk.id)
        if target_chunk_id in retrieved_chunk_ids:
            result['target_chunk_found'] = True
            result['target_chunk_rank'] = retrieved_chunk_ids.index(target_chunk_id) + 1
            
            # Find the score for the target chunk
            for chunk_data in retrieved_chunks_data:
                if chunk_data['id'] == target_chunk_id:
                    result['target_chunk_score'] = chunk_data['score']
                    break
        
        # Compute metrics
        metrics = {}
        for k in [1, 5, 10, 20]:
            metrics[f'recall_at_{k}'] = compute_recall_at_k(retrieved_chunk_ids, target_chunk_id, k)
            metrics[f'ndcg_at_{k}'] = compute_ndcg_at_k(retrieved_chunk_ids, target_chunk_id, k)
        
        metrics['mrr'] = compute_mrr(retrieved_chunk_ids, target_chunk_id)
        result['metrics'] = metrics
        result['success'] = True
        
    except Exception as e:
        result['error_message'] = str(e)
    
    return result


def run_evaluation(name: str, search_type: str = 'vector', score_threshold: float = 0.7, 
                  limit: int = 20, embedding_model: str = 'jinaai/jina-embeddings-v2-small-en') -> EvaluationRun:
    """
    Run a complete evaluation using all queries in the dataset.
    
    Args:
        name: Name/description for this evaluation run
        search_type: Type of search to perform
        score_threshold: Score threshold for search
        limit: Maximum number of results to retrieve
        embedding_model: Embedding model used
    
    Returns:
        EvaluationRun object with results
    """
    # Create evaluation run
    evaluation_run = EvaluationRun.objects.create(
        name=name,
        search_type=search_type,
        score_threshold=score_threshold,
        limit=limit,
        embedding_model=embedding_model,
        status='running'
    )
    
    try:
        # Get all evaluation queries
        queries = EvaluationQuery.objects.all()
        evaluation_run.total_queries = queries.count()
        evaluation_run.save()
        
        # Initialize searcher once to reuse
        searcher = ManPageSearch()
        
        # Process each query
        successful_queries = 0
        failed_queries = 0
        
        all_recall_at_1 = []
        all_recall_at_5 = []
        all_recall_at_10 = []
        all_recall_at_20 = []
        all_ndcg_at_1 = []
        all_ndcg_at_5 = []
        all_ndcg_at_10 = []
        all_ndcg_at_20 = []
        all_mrr = []
        
        for query in queries:
            # Evaluate the query
            eval_result = evaluate_single_query(query, search_type, score_threshold, limit, searcher)
            
            # Create evaluation result
            result = EvaluationResult.objects.create(
                evaluation_run=evaluation_run,
                query=query,
                retrieved_chunks=eval_result['retrieved_chunks'],
                target_chunk_found=eval_result['target_chunk_found'],
                target_chunk_rank=eval_result['target_chunk_rank'],
                target_chunk_score=eval_result['target_chunk_score'],
                recall_at_1=eval_result['metrics'].get('recall_at_1'),
                recall_at_5=eval_result['metrics'].get('recall_at_5'),
                recall_at_10=eval_result['metrics'].get('recall_at_10'),
                recall_at_20=eval_result['metrics'].get('recall_at_20'),
                ndcg_at_1=eval_result['metrics'].get('ndcg_at_1'),
                ndcg_at_5=eval_result['metrics'].get('ndcg_at_5'),
                ndcg_at_10=eval_result['metrics'].get('ndcg_at_10'),
                ndcg_at_20=eval_result['metrics'].get('ndcg_at_20'),
                mrr=eval_result['metrics'].get('mrr'),
                error_message=eval_result['error_message'],
                success=eval_result['success']
            )
            
            if eval_result['success']:
                successful_queries += 1
                # Collect metrics for averaging
                all_recall_at_1.append(eval_result['metrics'].get('recall_at_1', 0))
                all_recall_at_5.append(eval_result['metrics'].get('recall_at_5', 0))
                all_recall_at_10.append(eval_result['metrics'].get('recall_at_10', 0))
                all_recall_at_20.append(eval_result['metrics'].get('recall_at_20', 0))
                all_ndcg_at_1.append(eval_result['metrics'].get('ndcg_at_1', 0))
                all_ndcg_at_5.append(eval_result['metrics'].get('ndcg_at_5', 0))
                all_ndcg_at_10.append(eval_result['metrics'].get('ndcg_at_10', 0))
                all_ndcg_at_20.append(eval_result['metrics'].get('ndcg_at_20', 0))
                all_mrr.append(eval_result['metrics'].get('mrr', 0))
            else:
                failed_queries += 1
        
        # Update evaluation run with aggregated metrics
        evaluation_run.successful_queries = successful_queries
        evaluation_run.failed_queries = failed_queries
        
        if all_recall_at_1:
            evaluation_run.recall_at_1 = sum(all_recall_at_1) / len(all_recall_at_1)
            evaluation_run.recall_at_5 = sum(all_recall_at_5) / len(all_recall_at_5)
            evaluation_run.recall_at_10 = sum(all_recall_at_10) / len(all_recall_at_10)
            evaluation_run.recall_at_20 = sum(all_recall_at_20) / len(all_recall_at_20)
            evaluation_run.ndcg_at_1 = sum(all_ndcg_at_1) / len(all_ndcg_at_1)
            evaluation_run.ndcg_at_5 = sum(all_ndcg_at_5) / len(all_ndcg_at_5)
            evaluation_run.ndcg_at_10 = sum(all_ndcg_at_10) / len(all_ndcg_at_10)
            evaluation_run.ndcg_at_20 = sum(all_ndcg_at_20) / len(all_ndcg_at_20)
            evaluation_run.mrr = sum(all_mrr) / len(all_mrr)
        
        evaluation_run.status = 'completed'
        evaluation_run.completed_at = timezone.now()
        evaluation_run.save()
        
    except Exception as e:
        evaluation_run.status = 'failed'
        evaluation_run.completed_at = timezone.now()
        evaluation_run.save()
        raise e
    
    return evaluation_run


def load_evaluation_queries_from_file(file_path: str) -> int:
    """
    Load evaluation queries from a JSONL file.
    
    Args:
        file_path: Path to the JSONL file
    
    Returns:
        Number of queries loaded
    """
    import json
    
    queries_loaded = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                
                # Create or update evaluation query
                query, created = EvaluationQuery.objects.get_or_create(
                    query=data['query'],
                    defaults={
                        'expected_substrings': data['expected_substrings'],
                        'document_id': data['document_id'],
                        'target_section': data['target_section'],
                        'target_anchor': data['target_anchor'],
                    }
                )
                
                if created:
                    queries_loaded += 1
                    
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing line: {line[:100]}... Error: {e}")
                continue
    
    return queries_loaded
