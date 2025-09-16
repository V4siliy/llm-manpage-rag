import hashlib
import secrets
import uuid

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, name="", **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra)
        user.set_unusable_password()  # passwordless by default
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)  # staff/superuser use password
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    # For Postgres, consider CIEmailField (citext) to enforce case-insensitive uniqueness robustly.
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True)

    # Admin/permissions
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # Your extras
    upgraded_until = models.DateTimeField(null=True, blank=True)
    tg_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    # add other flags/settings as needed, e.g. JSONField for preferences

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return self.email

    @property
    def is_upgraded(self):
        return bool(self.upgraded_until and self.upgraded_until > timezone.now())


# One-time login code, stored as hash
class LoginCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_codes")
    code_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=16, default="login")  # e.g. login/verify
    attempts = models.PositiveSmallIntegerField(default=0)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "expires_at"]),
        ]

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @classmethod
    def create_for_user(cls, user, minutes=10, purpose="login"):
        # ~128 bits of entropy, URL-safe
        code = secrets.token_urlsafe(16)
        obj = cls.objects.create(
            user=user,
            code_hash=cls._hash(code),
            expires_at=timezone.now() + timezone.timedelta(minutes=minutes),
            purpose=purpose,
        )
        return code, obj.id

    def verify_and_use(self, candidate: str) -> bool:
        if self.used_at or timezone.now() > self.expires_at:
            return False
        ok = secrets.compare_digest(self.code_hash, self._hash(candidate))
        if not ok:
            self.attempts = models.F("attempts") + 1
            self.save(update_fields=["attempts"])
            return False
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
        return True


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
    search_vector = SearchVectorField(null=True, blank=True, help_text="Full-text search vector")
    
    class Meta:
        indexes = [
            models.Index(fields=['document', 'section_name']),
            models.Index(fields=['anchor']),
            models.Index(fields=['token_count']),
        ]
    
    def __str__(self):
        return f"{self.document.name}({self.document.section}) - {self.section_name} - {self.anchor[:50]}..."
