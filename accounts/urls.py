from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_request, name="login"),
    path("login-token/", views.login_token, name="login-token"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("search/", views.search_view, name="search"),
    path("api/search/", views.search_api, name="search-api"),
]
