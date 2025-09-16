from django.urls import path

from . import views

app_name = "search"
urlpatterns = [
    path("", views.search_view, name="search"),
    path("api/", views.search_api, name="search-api"),
    path("ask/", views.ask_view, name="ask"),
    path("ask-api/", views.ask_api, name="ask-api"),
    path("loading-message/", views.loading_message_api, name="loading-message"),
]
