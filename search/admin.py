from django.contrib import admin

from .models import Document, Chunk


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