from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, LoginCode


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'name', 'is_active', 'is_staff', 'date_joined', 'is_upgraded')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('email', 'name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Extra fields', {'fields': ('upgraded_until', 'tg_user_id')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2'),
        }),
    )


@admin.register(LoginCode)
class LoginCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'purpose', 'created_at', 'expires_at', 'used_at', 'attempts')
    list_filter = ('purpose', 'created_at', 'used_at')
    search_fields = ('user__email', 'ip')
    readonly_fields = ('code_hash', 'created_at', 'user_agent_hash')
    ordering = ('-created_at',)
    
    def has_add_permission(self, request):
        return False  # Login codes should only be created programmatically
