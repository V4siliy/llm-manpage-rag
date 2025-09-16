from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from .models import LoginCode, Document, Chunk
from .services import send_login_code, TooManyRequests
from .search import ManPageSearch


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


def search_view(request):
    """Search man-pages with full-text and fuzzy search"""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'fulltext')
    limit = int(request.GET.get('limit', 20))
    
    results = []
    stats = None
    
    if query:
        searcher = ManPageSearch()
        chunks = searcher.search_chunks(query, search_type, limit)
        
        # Convert to serializable format
        results = []
        for chunk in chunks:
            results.append({
                'id': str(chunk.id),
                'document_name': chunk.document.name,
                'document_section': chunk.document.section,
                'document_title': chunk.document.title,
                'section_name': chunk.section_name,
                'anchor': chunk.anchor,
                'text': chunk.text[:500] + '...' if len(chunk.text) > 500 else chunk.text,
                'token_count': chunk.token_count,
                'rank': getattr(chunk, 'rank', None),
                'similarity': getattr(chunk, 'similarity', None),
            })
        
        stats = searcher.get_document_stats()
    
    context = {
        'query': query,
        'search_type': search_type,
        'results': results,
        'stats': stats,
    }
    
    return render(request, "accounts/search.html", context)


@csrf_exempt
def search_api(request):
    """API endpoint for search functionality"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        query = data.get('query', '').strip()
        search_type = data.get('type', 'fulltext')
        limit = int(data.get('limit', 20))
        
        if not query:
            return JsonResponse({'error': 'Query is required'}, status=400)
        
        searcher = ManPageSearch()
        chunks = searcher.search_chunks(query, search_type, limit)
        
        results = []
        for chunk in chunks:
            results.append({
                'id': str(chunk.id),
                'document_name': chunk.document.name,
                'document_section': chunk.document.section,
                'document_title': chunk.document.title,
                'section_name': chunk.section_name,
                'anchor': chunk.anchor,
                'text': chunk.text,
                'token_count': chunk.token_count,
                'rank': getattr(chunk, 'rank', None),
                'similarity': getattr(chunk, 'similarity', None),
            })
        
        return JsonResponse({
            'results': results,
            'total': len(results),
            'query': query,
            'search_type': search_type
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)