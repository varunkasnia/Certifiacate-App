from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuizViewSet, PublicQuizViewSet

router = DefaultRouter()
router.register(r'host', QuizViewSet, basename='quiz')
router.register(r'public', PublicQuizViewSet, basename='public-quiz')

urlpatterns = [
    path('', include(router.urls)),
]
