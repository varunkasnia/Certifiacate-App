"""WebSocket consumers for real-time quiz"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from .models import Quiz, Question, Participant, Answer
from django.db import transaction

User = get_user_model()


class QuizConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for live quiz"""

    async def connect(self):
        self.quiz_id = self.scope['url_route']['kwargs']['quiz_id']
        self.quiz_group_name = f'quiz_{self.quiz_id}'

        # Get user from JWT token
        self.user = await self.get_user_from_jwt()

        # Join quiz group
        await self.channel_layer.group_add(
            self.quiz_group_name,
            self.channel_name
        )

        await self.accept()

        # Send current quiz state
        quiz = await self.get_quiz()
        if quiz:
            await self.send_quiz_state(quiz)
            # Broadcast participant count update when someone connects
            await self.broadcast_participant_update(quiz)
            # If quiz is live, send current question (synchronized)
            if quiz.status == 'live':
                await self.send_current_synchronized_question(quiz)

    async def disconnect(self, close_code):
        # Leave quiz group
        await self.channel_layer.group_discard(
            self.quiz_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'join':
                await self.handle_join(data)
            elif message_type == 'start_quiz':
                await self.handle_start_quiz(data)
            elif message_type == 'next_question':
                await self.handle_next_question(data)
            elif message_type == 'submit_answer':
                await self.handle_submit_answer(data)
            elif message_type == 'get_leaderboard':
                await self.handle_get_leaderboard(data)
            elif message_type == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))

    async def handle_join(self, data):
        """Handle participant join"""
        nickname = data.get('nickname')
        quiz = await self.get_quiz()

        if quiz and nickname:
            participant = await self.get_or_create_participant(quiz, nickname)
            await self.broadcast_participant_update(quiz)
            # Send current question to newly joined participant if quiz is live (synchronized)
            if quiz.status == 'live':
                await self.send_current_synchronized_question(quiz)

    async def handle_start_quiz(self, data):
        """Handle quiz start (host only)"""
        print(f"Start quiz request from user: {self.user}, authenticated: {self.user.is_authenticated}")
        if not self.user.is_authenticated:
            print("User not authenticated")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Authentication required to start quiz'
            }))
            return

        quiz = await self.get_quiz()
        print(f"Quiz found: {quiz is not None}")
        if quiz:
            is_host = await self.is_host(quiz)
            print(f"Is host: {is_host}, quiz host: {quiz.host}, current user: {self.user}")
            if is_host:
                await self.start_quiz(quiz)
                # Reset question index and send first question to all participants (synchronized)
                await self.reset_and_send_first_question(quiz)
                print("Quiz started successfully")
            else:
                print("User is not the host")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'You are not authorized to start this quiz'
                }))
        else:
            print("Quiz not found")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Quiz not found'
            }))


    async def handle_submit_answer(self, data):
        """Handle answer submission (synchronized - no auto-advance)"""
        quiz = await self.get_quiz()
        nickname = data.get('nickname')
        question_id = data.get('question_id')
        selected_option = data.get('selected_option')
        response_time = data.get('response_time', 0)

        if quiz and nickname and question_id:
            await self.save_answer(quiz, nickname, question_id, selected_option, response_time)
            await self.broadcast_leaderboard_update(quiz)
            # In synchronized mode, don't auto-advance - host controls progression

    async def handle_next_question(self, data):
        """Handle next question request (host only, synchronized)"""
        if not self.user.is_authenticated:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Authentication required'
            }))
            return

        quiz = await self.get_quiz()
        if quiz:
            is_host = await self.is_host(quiz)
            if is_host:
                await self.advance_to_next_question(quiz)
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Only host can advance questions'
                }))

    async def reset_and_send_first_question(self, quiz):
        """Reset quiz question index and send first question to all (synchronized)"""
        await database_sync_to_async(
            lambda: Quiz.objects.filter(id=quiz.id).update(current_question_index=0)
        )()
        await self.send_current_synchronized_question(quiz)

    async def advance_to_next_question(self, quiz):
        """Advance to next question and broadcast to all participants (synchronized)"""
        current_index = quiz.current_question_index
        questions = await database_sync_to_async(
            lambda: list(quiz.questions.all())
        )()
        
        if current_index + 1 < len(questions):
            # Advance to next question
            next_index = current_index + 1
            await database_sync_to_async(
                lambda: Quiz.objects.filter(id=quiz.id).update(current_question_index=next_index)
            )()
            await self.send_current_synchronized_question(quiz)
        else:
            # Quiz completed
            await self.complete_quiz(quiz)

    async def send_current_synchronized_question(self, quiz):
        """Send current question to all participants (synchronized)"""
        question = await self.get_question(quiz, quiz.current_question_index)
        if question:
            await self.channel_layer.group_send(
                self.quiz_group_name,
                {
                    'type': 'synchronized_question',
                    'question': {
                        'id': str(question.id),
                        'question_text': question.question_text,
                        'option_a': question.option_a,
                        'option_b': question.option_b,
                        'option_c': question.option_c,
                        'option_d': question.option_d,
                        'order': question.order,
                        'index': quiz.current_question_index
                    },
                    'time_limit': quiz.time_per_question
                }
            )
        else:
            # Quiz completed
            await self.complete_quiz(quiz)

    async def send_quiz_completed_to_participant(self, quiz, nickname):
        """Send quiz completed message to a specific participant"""
        try:
            leaderboard = await self.get_leaderboard(quiz)
            await self.send(text_data=json.dumps({
                'type': 'quiz_completed',
                'leaderboard': leaderboard
            }))
        except Exception:
            pass

    async def send_first_question_to_all_participants(self, quiz):
        """Send first question to all participants - deprecated, use send_current_synchronized_question"""
        await self.send_current_synchronized_question(quiz)

    async def handle_get_leaderboard(self, data):
        """Send leaderboard"""
        quiz = await self.get_quiz()
        if quiz:
            leaderboard = await self.get_leaderboard(quiz)
            await self.send(text_data=json.dumps({
                'type': 'leaderboard',
                'data': leaderboard
            }))

    @database_sync_to_async
    def get_user_from_jwt(self):
        """Get user from JWT token in query parameters"""
        try:
            # Get token from query string
            query_string = self.scope.get('query_string', b'').decode()
            token = None

            # Look for token in query params
            if 'token=' in query_string:
                token = query_string.split('token=')[1].split('&')[0]
            elif 'authorization=' in query_string:
                token = query_string.split('authorization=')[1].split('&')[0]
                if token.startswith('Bearer%20'):
                    token = token.replace('Bearer%20', '')
                elif token.startswith('Bearer '):
                    token = token.replace('Bearer ', '')

            if not token:
                return AnonymousUser()

            # Decode JWT token
            access_token = AccessToken(token)
            user_id = access_token['user_id']

            # Get user from database
            user = User.objects.get(id=user_id)
            return user

        except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
            return AnonymousUser()

    # Database operations
    @database_sync_to_async
    def get_quiz(self):
        try:
            return Quiz.objects.get(id=self.quiz_id)
        except Quiz.DoesNotExist:
            return None

    @database_sync_to_async
    def is_host(self, quiz):
        return self.user.is_authenticated and quiz.host == self.user

    @database_sync_to_async
    def get_or_create_participant(self, quiz, nickname):
        participant, created = Participant.objects.get_or_create(
            quiz=quiz,
            nickname=nickname,
            defaults={'user': self.user if self.user.is_authenticated else None}
        )
        return participant

    @database_sync_to_async
    def start_quiz(self, quiz):
        from django.utils import timezone
        quiz.status = 'live'
        quiz.started_at = timezone.now()
        quiz.current_question_index = 0  # Reset to first question
        quiz.save()

    @database_sync_to_async
    def get_question(self, quiz, index):
        questions = list(quiz.questions.all().order_by('order'))
        if 0 <= index < len(questions):
            return questions[index]
        return None

    @database_sync_to_async
    def get_quiz_with_index(self):
        """Get quiz with current question index"""
        try:
            return Quiz.objects.get(id=self.quiz_id)
        except Quiz.DoesNotExist:
            return None

    @database_sync_to_async
    def save_answer(self, quiz, nickname, question_id, selected_option, response_time):
        try:
            participant = Participant.objects.get(quiz=quiz, nickname=nickname)
            question = Question.objects.get(id=question_id, quiz=quiz)

            # Handle empty answers (time ran out with no selection)
            if not selected_option or selected_option.strip() == '':
                is_correct = False
                score = 0
                selected_option = ''  # Keep as empty string
            else:
                is_correct = selected_option.upper() == question.correct_answer.upper()
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
                    'selected_option': selected_option.upper() if selected_option else '',
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

            return answer
        except Exception as e:
            return None

    @database_sync_to_async
    def get_leaderboard(self, quiz):
        participants = list(quiz.participants.all().order_by(
            '-total_score', 'total_response_time'
        ))
        return [
            {
                'nickname': p.nickname,
                'total_score': p.total_score,
                'correct_answers': p.correct_answers,
                'total_response_time': p.total_response_time,
                'rank': idx + 1
            }
            for idx, p in enumerate(participants)
        ]

    @database_sync_to_async
    def get_participant_count(self, quiz):
        return quiz.participants.count()

    # Message sending
    async def send_quiz_state(self, quiz):
        """Send current quiz state"""
        participant_count = await self.get_participant_count(quiz)
        await self.send(text_data=json.dumps({
            'type': 'quiz_state',
            'data': {
                'id': str(quiz.id),
                'title': quiz.title,
                'status': quiz.status,
                'participant_count': participant_count,
                'time_per_question': quiz.time_per_question
            }
        }))

    async def send_first_question(self, quiz):
        """Send first question - deprecated, use send_first_question_to_all_participants"""
        await self.send_first_question_to_all_participants(quiz)

    async def send_question(self, quiz, index):
        """Send question at index"""
        question = await self.get_question(quiz, index)
        if question:
            await self.send_question_data(question, index, quiz.time_per_question)
        else:
            # Quiz completed
            await self.complete_quiz(quiz)

    async def send_question_data(self, question, index, time_limit):
        """Send question data to group"""
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                'type': 'question_message',
                'question': {
                    'id': str(question.id),
                    'question_text': question.question_text,
                    'option_a': question.option_a,
                    'option_b': question.option_b,
                    'option_c': question.option_c,
                    'option_d': question.option_d,
                    'order': question.order,
                    'index': index
                },
                'time_limit': time_limit
            }
        )

    async def complete_quiz(self, quiz):
        """Mark quiz as completed"""
        from django.utils import timezone
        quiz.status = 'completed'
        quiz.completed_at = timezone.now()
        await database_sync_to_async(quiz.save)()
        
        leaderboard = await self.get_leaderboard(quiz)
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                'type': 'quiz_completed',
                'leaderboard': leaderboard
            }
        )

    async def broadcast_participant_update(self, quiz):
        """Broadcast participant count update"""
        participant_count = await self.get_participant_count(quiz)
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                'type': 'participant_update',
                'participant_count': participant_count
            }
        )

    async def broadcast_leaderboard_update(self, quiz):
        """Broadcast leaderboard update"""
        leaderboard = await self.get_leaderboard(quiz)
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                'type': 'leaderboard_update',
                'leaderboard': leaderboard
            }
        )

    # Handler methods for group messages
    async def question_message(self, event):
        """Send question to WebSocket - deprecated"""
        await self.send(text_data=json.dumps({
            'type': 'question',
            'question': event['question'],
            'time_limit': event['time_limit']
        }))

    async def synchronized_question(self, event):
        """Send synchronized question to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'question',
            'question': event['question'],
            'time_limit': event['time_limit']
        }))

    async def participant_update(self, event):
        """Send participant update"""
        await self.send(text_data=json.dumps({
            'type': 'participant_update',
            'participant_count': event['participant_count']
        }))

    async def leaderboard_update(self, event):
        """Send leaderboard update"""
        await self.send(text_data=json.dumps({
            'type': 'leaderboard',
            'data': event['leaderboard']
        }))

    async def quiz_completed(self, event):
        """Send quiz completed message"""
        await self.send(text_data=json.dumps({
            'type': 'quiz_completed',
            'leaderboard': event['leaderboard']
        }))
