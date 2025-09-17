import uuid

from django.db import models


class Document(models.Model):
    """Represents a man-page document."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Name of the man-page (e.g., 'getent')")
    section = models.CharField(max_length=10, help_text="Man page section (e.g., '1', '2', '3')")
    title = models.CharField(max_length=1000, help_text="Full title of the man-page")
    source_path = models.CharField(max_length=1000, help_text="Path to the original source file")
    license = models.CharField(max_length=100, blank=True, help_text="License information")
    created_at = models.DateTimeField(auto_now_add=True)
    version_tag = models.CharField(max_length=50, help_text="Version tag (e.g., '6.9')")
    
    class Meta:
        unique_together = ['name', 'section', 'version_tag']
        indexes = [
            models.Index(fields=['name', 'section']),
            models.Index(fields=['version_tag']),
        ]
    
    def __str__(self):
        return f"{self.name}({self.section}) - {self.title}"


class Chunk(models.Model):
    """Represents a chunk of text from a man-page document."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    section_name = models.CharField(max_length=100, help_text="Section name (e.g., 'NAME', 'SYNOPSIS')")
    anchor = models.CharField(max_length=200, help_text="Anchor identifier for the chunk")
    text = models.TextField(help_text="The actual text content of the chunk")
    token_count = models.PositiveIntegerField(help_text="Number of tokens in the text")
    qdrant_id = models.CharField(max_length=100, null=True, blank=True, help_text="Qdrant vector ID")
    embedding_model = models.CharField(max_length=50, default='jinaai/jina-embeddings-v2-small-en', help_text="Embedding model used")
    
    class Meta:
        indexes = [
            models.Index(fields=['document', 'section_name']),
            models.Index(fields=['anchor']),
            models.Index(fields=['token_count']),
            models.Index(fields=['qdrant_id']),
        ]
    
    def __str__(self):
        return f"{self.document.name}({self.document.section}) - {self.section_name} - {self.anchor[:50]}..."


class EvaluationQuery(models.Model):
    """Represents a single evaluation query from the eval dataset."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.TextField(help_text="The evaluation query text")
    expected_substrings = models.JSONField(help_text="List of expected substrings that should be found")
    document_id = models.CharField(max_length=200, help_text="Target document ID from eval data")
    target_section = models.CharField(max_length=100, help_text="Target section name")
    target_anchor = models.CharField(max_length=200, help_text="Target anchor identifier")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['document_id']),
            models.Index(fields=['target_section']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Query: {self.query[:50]}... -> {self.document_id}"


class EvaluationRun(models.Model):
    """Represents a complete evaluation run with results and metrics."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Name/description of this evaluation run")
    search_type = models.CharField(max_length=50, default='vector', help_text="Type of search used")
    score_threshold = models.FloatField(default=0.7, help_text="Score threshold used for search")
    limit = models.PositiveIntegerField(default=20, help_text="Maximum number of results returned")
    embedding_model = models.CharField(max_length=100, help_text="Embedding model used")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], default='running')
    
    # Metrics
    recall_at_1 = models.FloatField(null=True, blank=True)
    recall_at_5 = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_20 = models.FloatField(null=True, blank=True)
    ndcg_at_1 = models.FloatField(null=True, blank=True)
    ndcg_at_5 = models.FloatField(null=True, blank=True)
    ndcg_at_10 = models.FloatField(null=True, blank=True)
    ndcg_at_20 = models.FloatField(null=True, blank=True)
    mrr = models.FloatField(null=True, blank=True)
    
    # Summary stats
    total_queries = models.PositiveIntegerField(default=0)
    successful_queries = models.PositiveIntegerField(default=0)
    failed_queries = models.PositiveIntegerField(default=0)
    
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['search_type']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Evaluation Run: {self.name} ({self.status})"


class EvaluationResult(models.Model):
    """Represents the result of a single query evaluation."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation_run = models.ForeignKey(EvaluationRun, on_delete=models.CASCADE, related_name='results')
    query = models.ForeignKey(EvaluationQuery, on_delete=models.CASCADE, related_name='results')
    
    # Search results
    retrieved_chunks = models.JSONField(help_text="List of retrieved chunk IDs with scores")
    target_chunk_found = models.BooleanField(default=False)
    target_chunk_rank = models.PositiveIntegerField(null=True, blank=True)
    target_chunk_score = models.FloatField(null=True, blank=True)
    
    # Metrics for this query
    recall_at_1 = models.FloatField(null=True, blank=True)
    recall_at_5 = models.FloatField(null=True, blank=True)
    recall_at_10 = models.FloatField(null=True, blank=True)
    recall_at_20 = models.FloatField(null=True, blank=True)
    ndcg_at_1 = models.FloatField(null=True, blank=True)
    ndcg_at_5 = models.FloatField(null=True, blank=True)
    ndcg_at_10 = models.FloatField(null=True, blank=True)
    ndcg_at_20 = models.FloatField(null=True, blank=True)
    mrr = models.FloatField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(blank=True, null=True, help_text="Error message if evaluation failed")
    success = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['evaluation_run', 'query']),
            models.Index(fields=['target_chunk_found']),
            models.Index(fields=['success']),
        ]
        unique_together = ['evaluation_run', 'query']
    
    def __str__(self):
        return f"Result: {self.query.query[:30]}... -> Found: {self.target_chunk_found}"
