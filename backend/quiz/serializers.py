from rest_framework import serializers
from .models import Quiz, Document, Question, Participant, Answer


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ('id', 'file', 'file_type', 'uploaded_at')
        read_only_fields = ('id', 'uploaded_at')


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ('id', 'question_text', 'option_a', 'option_b', 'option_c', 
                 'option_d', 'correct_answer', 'explanation', 'order')
        read_only_fields = ('id',)


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = ('id', 'title', 'description', 'difficulty', 'status',
                 'time_per_question', 'current_question_index', 'created_at', 'questions', 'documents',
                 'participant_count', 'started_at', 'completed_at')
        read_only_fields = ('id', 'created_at', 'started_at', 'completed_at')

    def get_participant_count(self, obj):
        return obj.participants.count()


class QuizCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ('title', 'description', 'difficulty', 'time_per_question')

    def create(self, validated_data):
        validated_data['host'] = self.context['request'].user
        return super().create(validated_data)


class QuestionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ('question_text', 'option_a', 'option_b', 'option_c',
                 'option_d', 'correct_answer', 'explanation', 'order')

    def create(self, validated_data):
        quiz_id = self.context['quiz_id']
        validated_data['quiz_id'] = quiz_id
        return super().create(validated_data)


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = ('id', 'nickname', 'total_score', 'correct_answers',
                 'joined_at', 'total_response_time')
        read_only_fields = ('id', 'joined_at')


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ('id', 'selected_option', 'is_correct', 'response_time',
                 'score', 'answered_at')
        read_only_fields = ('id', 'is_correct', 'score', 'answered_at')


class LeaderboardEntrySerializer(serializers.Serializer):
    nickname = serializers.CharField()
    total_score = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    total_response_time = serializers.FloatField()
    rank = serializers.IntegerField()
