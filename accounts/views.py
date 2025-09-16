from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import LoginCode
from .services import send_login_code, TooManyRequests


def login_request(request):
    """Display login form and handle login code requests"""
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if not email:
            messages.error(request, "Please enter your email address.")
            return render(request, "accounts/login.html")
        
        try:
            send_login_code(email, request)
            messages.success(request, "If that email exists, we sent you a sign-in link.")
        except TooManyRequests as e:
            messages.error(request, str(e))
        
        return render(request, "accounts/login.html")
    
    return render(request, "accounts/login.html")


@require_http_methods(["GET", "POST"])
def login_token(request):
    # We prevent one-click auto-login to avoid link preview scanners consuming tokens.
    if request.method == "GET":
        code_id = request.GET.get("id")
        code = request.GET.get("code")
        if not code_id or not code:
            messages.error(request, "Invalid login link.")
            return redirect("accounts:login")
        return render(request, "accounts/confirm_login.html", {"id": code_id, "code": code})

    # POST to actually consume the token
    code_id = request.POST.get("id")
    code = request.POST.get("code")
    lc = get_object_or_404(LoginCode, id=code_id)
    if lc.expires_at < timezone.now():
        messages.error(request, "This login link has expired.")
        return redirect("accounts:login")

    if not lc.verify_and_use(code):
        # Optional: block after N attempts
        messages.error(request, "Invalid login code.")
        return redirect("accounts:login")

    user = lc.user
    # Log user in. We can use the default ModelBackend; no password is checked here.
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    # Optional: set session age shorter for passwordless
    request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days "remember me", or session-only if you prefer
    messages.success(request, f"Welcome back, {user.name or user.email}!")
    return redirect("home")


def logout_view(request):
    """Handle user logout"""
    from django.contrib.auth import logout
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")


def profile_view(request):
    """Display user profile"""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    
    return render(request, "accounts/profile.html", {"user": request.user})