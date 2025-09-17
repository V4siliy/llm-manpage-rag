"""
Management command to run evaluations and load evaluation data.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
import os

from search.models import EvaluationQuery
from search.evaluation_utils import run_evaluation, load_evaluation_queries_from_file


class Command(BaseCommand):
    help = 'Run evaluations and manage evaluation data'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['load', 'run', 'list'],
            help='Action to perform: load queries, run evaluation, or list runs'
        )
        
        parser.add_argument(
            '--file',
            type=str,
            help='Path to evaluation JSONL file (for load action)'
        )
        
        parser.add_argument(
            '--name',
            type=str,
            help='Name for the evaluation run'
        )
        
        parser.add_argument(
            '--search-type',
            type=str,
            default='vector',
            choices=['vector', 'hybrid'],
            help='Type of search to use'
        )
        
        parser.add_argument(
            '--score-threshold',
            type=float,
            default=0.7,
            help='Score threshold for search'
        )
        
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Maximum number of results to retrieve'
        )
        
        parser.add_argument(
            '--embedding-model',
            type=str,
            default='jinaai/jina-embeddings-v2-small-en',
            help='Embedding model to use'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'load':
            self.load_queries(options)
        elif action == 'run':
            self.run_evaluation(options)
        elif action == 'list':
            self.list_runs()

    def load_queries(self, options):
        """Load evaluation queries from JSONL file"""
        file_path = options['file']
        
        if not file_path:
            # Default to the eval.jsonl file in the data directory
            file_path = 'data/eval/eval.jsonl'
        
        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")
        
        self.stdout.write(f"Loading evaluation queries from: {file_path}")
        
        try:
            queries_loaded = load_evaluation_queries_from_file(file_path)
            self.stdout.write(
                self.style.SUCCESS(f"Successfully loaded {queries_loaded} evaluation queries")
            )
        except Exception as e:
            raise CommandError(f"Error loading queries: {e}")

    def run_evaluation(self, options):
        """Run a complete evaluation"""
        name = options['name']
        if not name:
            timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
            name = f"Evaluation_{timestamp}"
        
        self.stdout.write(f"Starting evaluation: {name}")
        self.stdout.write(f"Search type: {options['search_type']}")
        self.stdout.write(f"Score threshold: {options['score_threshold']}")
        self.stdout.write(f"Limit: {options['limit']}")
        self.stdout.write(f"Embedding model: {options['embedding_model']}")
        
        # Check if we have any queries loaded
        query_count = EvaluationQuery.objects.count()
        if query_count == 0:
            raise CommandError(
                "No evaluation queries found. Please run 'load' action first to load queries."
            )
        
        self.stdout.write(f"Found {query_count} evaluation queries")
        
        try:
            evaluation_run = run_evaluation(
                name=name,
                search_type=options['search_type'],
                score_threshold=options['score_threshold'],
                limit=options['limit'],
                embedding_model=options['embedding_model']
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Evaluation completed successfully!")
            )
            self.stdout.write(f"Run ID: {evaluation_run.id}")
            self.stdout.write(f"Status: {evaluation_run.status}")
            self.stdout.write(f"Total queries: {evaluation_run.total_queries}")
            self.stdout.write(f"Successful queries: {evaluation_run.successful_queries}")
            self.stdout.write(f"Failed queries: {evaluation_run.failed_queries}")
            
            if evaluation_run.status == 'completed':
                self.stdout.write("\nMetrics:")
                self.stdout.write(f"  Recall@1:  {evaluation_run.recall_at_1:.4f}")
                self.stdout.write(f"  Recall@5:  {evaluation_run.recall_at_5:.4f}")
                self.stdout.write(f"  Recall@10: {evaluation_run.recall_at_10:.4f}")
                self.stdout.write(f"  Recall@20: {evaluation_run.recall_at_20:.4f}")
                self.stdout.write(f"  nDCG@1:    {evaluation_run.ndcg_at_1:.4f}")
                self.stdout.write(f"  nDCG@5:    {evaluation_run.ndcg_at_5:.4f}")
                self.stdout.write(f"  nDCG@10:   {evaluation_run.ndcg_at_10:.4f}")
                self.stdout.write(f"  nDCG@20:   {evaluation_run.ndcg_at_20:.4f}")
                self.stdout.write(f"  MRR:       {evaluation_run.mrr:.4f}")
            
        except Exception as e:
            raise CommandError(f"Error running evaluation: {e}")

    def list_runs(self):
        """List all evaluation runs"""
        from search.models import EvaluationRun
        
        runs = EvaluationRun.objects.all().order_by('-created_at')
        
        if not runs.exists():
            self.stdout.write("No evaluation runs found.")
            return
        
        self.stdout.write("Evaluation Runs:")
        self.stdout.write("-" * 80)
        
        for run in runs:
            status_color = self.style.SUCCESS if run.status == 'completed' else \
                          self.style.WARNING if run.status == 'running' else \
                          self.style.ERROR
            
            self.stdout.write(f"ID: {run.id}")
            self.stdout.write(f"Name: {run.name}")
            self.stdout.write(f"Status: {status_color(run.status)}")
            self.stdout.write(f"Created: {run.created_at}")
            
            if run.status == 'completed':
                self.stdout.write(f"Completed: {run.completed_at}")
                self.stdout.write(f"Queries: {run.successful_queries}/{run.total_queries}")
                self.stdout.write(f"Recall@5: {run.recall_at_5:.4f}")
                self.stdout.write(f"nDCG@5: {run.ndcg_at_5:.4f}")
                self.stdout.write(f"MRR: {run.mrr:.4f}")
            
            self.stdout.write("-" * 80)
