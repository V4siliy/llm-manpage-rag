import hashlib

from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import User, LoginCode


class TooManyRequests(Exception):
    pass


def get_client_ip(request):
    # Keep it simple; if behind proxy, use X-Forwarded-For with care
    return request.META.get("REMOTE_ADDR")


def send_login_code(email: str, request=None):
    email = User.objects.normalize_email(email)
    user, _ = User.objects.get_or_create(email=email, defaults={"name": ""})

    now = timezone.now()
    # Simple throttling: 1 request per 30s, max 5 active login codes in last hour
    recent_block = user.login_codes.filter(created_at__gt=now - timezone.timedelta(seconds=30)).exists()
    if recent_block:
        raise TooManyRequests("Please wait before requesting another code.")
    hourly = user.login_codes.filter(created_at__gt=now - timezone.timedelta(hours=1)).count()
    if hourly >= 5:
        raise TooManyRequests("Too many login emails. Try later.")

    code, code_id = LoginCode.create_for_user(user, minutes=10, purpose="login")

    # Persist request metadata
    if request is not None:
        try:
            lc = user.login_codes.get(id=code_id)
            lc.ip = get_client_ip(request)
            ua = request.META.get("HTTP_USER_AGENT", "")
            lc.user_agent_hash = hashlib.sha256(ua.encode("utf-8")).hexdigest()
            lc.save(update_fields=["ip", "user_agent_hash"])
        except LoginCode.DoesNotExist:
            pass

    # Prefer magic link plus numeric fallback (optional)
    path = reverse("accounts:login-token")
    # Include record id to locate without revealing hash; security relies on the random code
    link = f"{request.build_absolute_uri(path)}?id={code_id}&code={code}" if request else f"/login-token?id={code_id}&code={code}"

    subject = "Your sign-in link"
    body = f"Click to sign in:\n{link}\n\nThis link expires in 10 minutes.\nIf you didn't request it, you can ignore this email."
    send_mail(subject, body, None, [user.email])

    return {"sent": True}
