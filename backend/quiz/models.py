from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class Quiz(models.Model):
    """Quiz model"""
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('live', 'Live'),
        ('completed', 'Completed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hosted_quizzes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    time_per_question = models.IntegerField(default=30)  # seconds
    current_question_index = models.IntegerField(default=0)  # Track current question for synchronized progression
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.id})"


class Document(models.Model):
    """Uploaded documents for quiz generation"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='documents/')
    file_type = models.CharField(max_length=20)  # pdf, pptx, docx, txt, image
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.name} - {self.quiz.title}"


class Question(models.Model):
    """Quiz question"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_answer = models.CharField(max_length=1, choices=[
        ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')
    ])
    explanation = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q{self.order + 1}: {self.question_text[:50]}..."


class Participant(models.Model):
    """Quiz participant"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='participations', null=True, blank=True)
    nickname = models.CharField(max_length=100)
    joined_at = models.DateTimeField(auto_now_add=True)
    total_score = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    total_response_time = models.FloatField(default=0.0)  # seconds
    current_question_index = models.IntegerField(default=0)  # Track which question they're on

    class Meta:
        unique_together = ['quiz', 'nickname']

    def __str__(self):
        return f"{self.nickname} - {self.quiz.title}"


class Answer(models.Model):
    """Participant's answer to a question"""
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    selected_option = models.CharField(max_length=1, blank=True, choices=[
        ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')
    ])
    is_correct = models.BooleanField(default=False)
    response_time = models.FloatField(default=0.0)  # seconds
    score = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['participant', 'question']

    def __str__(self):
        return f"{self.participant.nickname} - Q{self.question.order + 1}"
