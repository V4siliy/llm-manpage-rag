from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils import timezone

from .models import Document, Chunk, EvaluationQuery, EvaluationRun, EvaluationResult
from .evaluation_utils import run_evaluation


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'section', 'title', 'version_tag', 'created_at']
    list_filter = ['section', 'version_tag', 'created_at']
    search_fields = ['name', 'title']
    readonly_fields = ['id', 'created_at']
    ordering = ['name', 'section']


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ['document', 'section_name', 'anchor', 'token_count']
    list_filter = ['section_name', 'document__section', 'document__version_tag']
    search_fields = ['text', 'anchor', 'document__name']
    readonly_fields = ['id']
    ordering = ['document', 'section_name']


@admin.register(EvaluationQuery)
class EvaluationQueryAdmin(admin.ModelAdmin):
    list_display = ['query_short', 'document_id', 'target_section', 'target_anchor', 'created_at']
    list_filter = ['target_section', 'created_at']
    search_fields = ['query', 'document_id', 'target_anchor']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']
    actions = ['run_evaluation_selected', 'run_evaluation_all']
    
    def query_short(self, obj):
        return obj.query[:50] + '...' if len(obj.query) > 50 else obj.query
    query_short.short_description = 'Query'
    
    def run_evaluation_selected(self, request, queryset):
        """Run evaluation for selected queries"""
        if not queryset.exists():
            self.message_user(request, "No queries selected.", level=messages.WARNING)
            return
        
        try:
            # Create a temporary evaluation run for selected queries
            timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
            run_name = f"Admin Selected Queries - {timestamp}"
            
            # Create evaluation run
            evaluation_run = EvaluationRun.objects.create(
                name=run_name,
                search_type='vector',
                score_threshold=0.7,
                limit=20,
                embedding_model='jinaai/jina-embeddings-v2-small-en',
                status='running',
                total_queries=queryset.count()
            )
            
            # Run evaluation for selected queries only
            from .evaluation_utils import evaluate_single_query
            
            searcher = None
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
            
            for query in queryset:
                try:
                    eval_result = evaluate_single_query(query, 'vector', 0.7, 20, searcher)
                    
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
                        
                except Exception as e:
                    failed_queries += 1
                    EvaluationResult.objects.create(
                        evaluation_run=evaluation_run,
                        query=query,
                        retrieved_chunks=[],
                        error_message=str(e),
                        success=False
                    )
            
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
            
            self.message_user(
                request, 
                f"Evaluation completed successfully! Run ID: {evaluation_run.id}. "
                f"Processed {queryset.count()} queries ({successful_queries} successful, {failed_queries} failed).",
                level=messages.SUCCESS
            )
            
        except Exception as e:
            self.message_user(
                request, 
                f"Error running evaluation: {str(e)}", 
                level=messages.ERROR
            )
    
    run_evaluation_selected.short_description = "Run evaluation for selected queries"
    
    def run_evaluation_all(self, request, queryset):
        """Run evaluation for all queries"""
        try:
            timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
            run_name = f"Admin All Queries - {timestamp}"
            
            evaluation_run = run_evaluation(
                name=run_name,
                search_type='vector',
                score_threshold=0.7,
                limit=20,
                embedding_model='jinaai/jina-embeddings-v2-small-en'
            )
            
            self.message_user(
                request, 
                f"Evaluation completed successfully! Run ID: {evaluation_run.id}. "
                f"Processed {evaluation_run.total_queries} queries ({evaluation_run.successful_queries} successful, {evaluation_run.failed_queries} failed).",
                level=messages.SUCCESS
            )
            
        except Exception as e:
            self.message_user(
                request, 
                f"Error running evaluation: {str(e)}", 
                level=messages.ERROR
            )
    
    run_evaluation_all.short_description = "Run evaluation for ALL queries"


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'search_type', 'total_queries', 'successful_queries', 
                   'recall_at_5', 'ndcg_at_5', 'mrr', 'created_at']
    list_filter = ['status', 'search_type', 'created_at']
    search_fields = ['name', 'embedding_model']
    readonly_fields = ['id', 'created_at', 'completed_at']
    ordering = ['-created_at']
    actions = ['rerun_evaluation']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'status', 'search_type', 'score_threshold', 'limit', 'embedding_model')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at')
        }),
        ('Summary Statistics', {
            'fields': ('total_queries', 'successful_queries', 'failed_queries')
        }),
        ('Metrics', {
            'fields': (
                ('recall_at_1', 'recall_at_5', 'recall_at_10', 'recall_at_20'),
                ('ndcg_at_1', 'ndcg_at_5', 'ndcg_at_10', 'ndcg_at_20'),
                ('mrr',)
            )
        }),
    )
    
    def rerun_evaluation(self, request, queryset):
        """Rerun evaluation for selected runs"""
        if not queryset.exists():
            self.message_user(request, "No evaluation runs selected.", level=messages.WARNING)
            return
        
        try:
            for evaluation_run in queryset:
                # Create a new run with the same parameters
                timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
                new_run_name = f"Rerun: {evaluation_run.name} - {timestamp}"
                
                new_evaluation_run = run_evaluation(
                    name=new_run_name,
                    search_type=evaluation_run.search_type,
                    score_threshold=evaluation_run.score_threshold,
                    limit=evaluation_run.limit,
                    embedding_model=evaluation_run.embedding_model
                )
                
                self.message_user(
                    request, 
                    f"Rerun completed for '{evaluation_run.name}'. New Run ID: {new_evaluation_run.id}",
                    level=messages.SUCCESS
                )
                
        except Exception as e:
            self.message_user(
                request, 
                f"Error rerunning evaluation: {str(e)}", 
                level=messages.ERROR
            )
    
    rerun_evaluation.short_description = "Rerun evaluation with same parameters"


@admin.register(EvaluationResult)
class EvaluationResultAdmin(admin.ModelAdmin):
    list_display = ['query_short', 'evaluation_run', 'target_chunk_found', 'target_chunk_rank', 
                   'recall_at_5', 'ndcg_at_5', 'mrr', 'success']
    list_filter = ['target_chunk_found', 'success', 'evaluation_run__status', 'evaluation_run']
    search_fields = ['query__query', 'query__document_id']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']
    
    def query_short(self, obj):
        return obj.query.query[:50] + '...' if len(obj.query.query) > 50 else obj.query.query
    query_short.short_description = 'Query'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('evaluation_run', 'query', 'success', 'error_message')
        }),
        ('Search Results', {
            'fields': ('target_chunk_found', 'target_chunk_rank', 'target_chunk_score', 'retrieved_chunks')
        }),
        ('Metrics', {
            'fields': (
                ('recall_at_1', 'recall_at_5', 'recall_at_10', 'recall_at_20'),
                ('ndcg_at_1', 'ndcg_at_5', 'ndcg_at_10', 'ndcg_at_20'),
                ('mrr',)
            )
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )