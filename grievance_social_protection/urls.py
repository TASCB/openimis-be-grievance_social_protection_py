from django.urls import path
from . import views

urlpatterns = [
    path("attach", views.attach, name="attach"),
    path("upload", views.upload, name="upload"),
]
