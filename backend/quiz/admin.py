from django.contrib import admin
from .models import Quiz, Document, Question, Participant, Answer


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'host', 'status', 'difficulty', 'created_at')
    list_filter = ('status', 'difficulty', 'created_at')
    search_fields = ('title', 'host__email')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'order', 'question_text', 'correct_answer')
    list_filter = ('quiz',)


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('nickname', 'quiz', 'total_score', 'correct_answers')
    list_filter = ('quiz',)


admin.site.register(Document)
admin.site.register(Answer)
