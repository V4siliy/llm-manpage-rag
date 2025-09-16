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
