"""Quiz API views"""
import os
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from openpyxl import Workbook
from django.http import HttpResponse
from io import BytesIO
from .models import Quiz, Document, Question, Participant, Answer
from .serializers import (
    QuizSerializer, QuizCreateSerializer, QuestionSerializer,
    QuestionCreateSerializer, ParticipantSerializer, AnswerSerializer,
    LeaderboardEntrySerializer, DocumentSerializer
)
from .utils.document_processor import DocumentProcessor
from .utils.rag_pipeline import RAGPipeline


class QuizViewSet(viewsets.ModelViewSet):
    """Quiz CRUD operations"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Quiz.objects.filter(host=user).order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return QuizCreateSerializer
        return QuizSerializer

    def create(self, request):
        """Create a new quiz"""
        serializer = QuizCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            quiz = serializer.save()
            return Response(QuizSerializer(quiz).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def upload_documents(self, request, pk=None):
        """Upload documents for quiz generation"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        
        if 'files' not in request.FILES:
            return Response({'error': 'No files provided'}, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist('files')
        processor = DocumentProcessor()
        all_texts = []

        for file in files:
            file_type = file.name.split('.')[-1].lower()
            if file_type not in ['pdf', 'pptx', 'ppt', 'docx', 'doc', 'txt', 
                               'jpg', 'jpeg', 'png', 'gif', 'bmp']:
                continue

            try:
                text = processor.process_document(file, file_type)
                if text:
                    all_texts.append(text)
                    Document.objects.create(
                        quiz=quiz,
                        file=file,
                        file_type=file_type
                    )
            except Exception as e:
                return Response({'error': f'Error processing {file.name}: {str(e)}'}, 
                              status=status.HTTP_400_BAD_REQUEST)

        if all_texts:
            # Create vector store
            rag = RAGPipeline()
            rag.create_vector_store(all_texts, quiz.id)

        return Response({'message': f'Processed {len(all_texts)} documents'}, 
                       status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def generate_questions(self, request, pk=None):
        """Generate questions using RAG"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        num_questions = request.data.get('num_questions', 10)
        difficulty = request.data.get('difficulty', quiz.difficulty)

        rag = RAGPipeline()
        rag.load_vector_store(quiz.id)

        if not rag.vector_store:
            # Fallback: use manual title/description
            context = f"Title: {quiz.title}\nDescription: {quiz.description}"
        else:
            # Retrieve context based on quiz title/description
            query = f"{quiz.title} {quiz.description}"
            context = rag.retrieve_context(query, k=5)

        questions = rag.generate_questions(num_questions, difficulty, context)

        # Save questions
        created_questions = []
        for idx, q_data in enumerate(questions):
            question = Question.objects.create(
                quiz=quiz,
                question_text=q_data.get('question', ''),
                option_a=q_data.get('options', {}).get('A', ''),
                option_b=q_data.get('options', {}).get('B', ''),
                option_c=q_data.get('options', {}).get('C', ''),
                option_d=q_data.get('options', {}).get('D', ''),
                correct_answer=q_data.get('correct_answer', 'A'),
                explanation=q_data.get('explanation', ''),
                order=idx
            )
            created_questions.append(QuestionSerializer(question).data)

        quiz.status = 'ready'
        quiz.save()

        return Response({'questions': created_questions}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def questions(self, request, pk=None):
        """Get all questions for a quiz"""
        quiz = get_object_or_404(Quiz, pk=pk)
        questions = quiz.questions.all()
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_question(self, request, pk=None):
        """Add a new question"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        serializer = QuestionCreateSerializer(
            data=request.data,
            context={'quiz_id': quiz.id}
        )
        if serializer.is_valid():
            question = serializer.save()
            return Response(QuestionSerializer(question).data, 
                          status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['put'])
    def update_question(self, request, pk=None):
        """Update a question"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        question_id = request.data.get('question_id')
        question = get_object_or_404(Question, pk=question_id, quiz=quiz)
        
        serializer = QuestionSerializer(question, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def delete_question(self, request, pk=None):
        """Delete a question"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        question_id = request.query_params.get('question_id')
        question = get_object_or_404(Question, pk=question_id, quiz=quiz)
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def confirm_quiz(self, request, pk=None):
        """Confirm quiz and make it ready"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        if quiz.questions.count() == 0:
            return Response({'error': 'Quiz must have at least one question'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        quiz.status = 'ready'
        quiz.time_per_question = request.data.get('time_per_question', quiz.time_per_question)
        quiz.save()
        return Response(QuizSerializer(quiz).data)

    @action(detail=True, methods=['get'])
    def leaderboard(self, request, pk=None):
        """Get leaderboard for quiz"""
        quiz = get_object_or_404(Quiz, pk=pk)
        participants = quiz.participants.all().order_by('-total_score', 'total_response_time')
        
        leaderboard = []
        for rank, participant in enumerate(participants, 1):
            leaderboard.append({
                'nickname': participant.nickname,
                'total_score': participant.total_score,
                'correct_answers': participant.correct_answers,
                'total_response_time': participant.total_response_time,
                'rank': rank
            })
        
        return Response(LeaderboardEntrySerializer(leaderboard, many=True).data)

    @action(detail=True, methods=['get'], url_path='results/download')
    def download_results(self, request, pk=None):
        """Download quiz results as an Excel file"""
        quiz = get_object_or_404(Quiz, pk=pk, host=request.user)
        
        # Create a new Excel workbook and add a worksheet
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Quiz Results"

        # Add headers
        worksheet.append([
            "Player Nickname",
            "Total Score"
        ])

        # Populate with data
        participants = quiz.participants.all().order_by('-total_score')
        for participant in participants:
            worksheet.append([
                participant.nickname,
                participant.total_score
            ])

        # Prepare the response
        excel_file = BytesIO()
        workbook.save(excel_file)
        excel_file.seek(0)

        response = HttpResponse(
            excel_file.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{quiz.title}_results.xlsx"'
        return response


class PublicQuizViewSet(viewsets.ReadOnlyModelViewSet):
    """Public quiz endpoints for participants"""
    permission_classes = []  # Public access
    queryset = Quiz.objects.filter(status__in=['ready', 'live'])

    @action(detail=True, methods=['post'])
    def join(self, request, pk=None):
        """Join a quiz"""
        quiz = get_object_or_404(Quiz, pk=pk, status__in=['ready', 'live'])
        nickname = request.data.get('nickname')
        
        if not nickname:
            return Response({'error': 'Nickname required'}, 
                          status=status.HTTP_400_BAD_REQUEST)

        participant, created = Participant.objects.get_or_create(
            quiz=quiz,
            nickname=nickname,
            defaults={'user': request.user if request.user.is_authenticated else None}
        )

        return Response(ParticipantSerializer(participant).data, 
                       status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def submit_answer(self, request, pk=None):
        """Submit answer to a question"""
        quiz = get_object_or_404(Quiz, pk=pk)
        nickname = request.data.get('nickname')
        question_id = request.data.get('question_id')
        selected_option = request.data.get('selected_option')
        response_time = request.data.get('response_time', 0)

        participant = get_object_or_404(Participant, quiz=quiz, nickname=nickname)
        question = get_object_or_404(Question, pk=question_id, quiz=quiz)

        is_correct = selected_option.upper() == question.correct_answer.upper()
        
        # Calculate score
        base_score = 100 if is_correct else 0
        time_bonus = 0
        if is_correct and quiz.time_per_question > 0:
            remaining_time = max(0, quiz.time_per_question - response_time)
            time_bonus = int((remaining_time / quiz.time_per_question) * 50)
        score = base_score + time_bonus

        answer, created = Answer.objects.update_or_create(
            participant=participant,
            question=question,
            defaults={
                'selected_option': selected_option.upper(),
                'is_correct': is_correct,
                'response_time': response_time,
                'score': score
            }
        )

        # Update participant stats
        participant.total_score = sum(a.score for a in participant.answers.all())
        participant.correct_answers = participant.answers.filter(is_correct=True).count()
        participant.total_response_time += response_time
        participant.save()

        return Response(AnswerSerializer(answer).data)
