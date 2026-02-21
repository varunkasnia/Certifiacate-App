import socketio
import asyncio
from typing import Dict, List
from database import get_db, GameSession, Player, Question, Answer
from sqlalchemy.orm import Session
from config import settings
from datetime import datetime

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)


# In-memory store for active game rooms
active_games: Dict[str, dict] = {}
pending_player_disconnects: Dict[str, asyncio.Task] = {}
PLAYER_DISCONNECT_GRACE_SECONDS = 8


async def _remove_player_after_grace(pin: str, sid: str):
    """Remove player only if they did not reconnect quickly."""
    try:
        await asyncio.sleep(PLAYER_DISCONNECT_GRACE_SECONDS)
        game_data = active_games.get(pin)
        if not game_data:
            return
        if sid not in game_data.get('players', {}):
            return

        player_name = game_data['players'][sid]['name']
        del game_data['players'][sid]
        await sio.emit('player_left', {'player_name': player_name}, room=pin)

        players_list = [
            {'name': p['name'], 'player_id': p['player_id']}
            for p in game_data['players'].values()
        ]
        await sio.emit('lobby_updated', {
            'players': players_list,
            'count': len(players_list)
        }, room=pin)
    finally:
        pending_player_disconnects.pop(sid, None)


@sio.event
async def connect(sid, environ):
    """Handle client connection"""
    print(f"Client connected: {sid}")
    await sio.emit('connected', {'sid': sid}, room=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    print(f"Client disconnected: {sid}")
    
    # Remove from active games
    for pin, game_data in active_games.items():
        if sid == game_data.get('host_sid'):
            game_data['host_sid'] = None
            await sio.emit('host_disconnected', {'message': 'Host disconnected'}, room=pin)

        if sid in game_data.get('players', {}):
            previous_task = pending_player_disconnects.pop(sid, None)
            if previous_task:
                previous_task.cancel()
            pending_player_disconnects[sid] = asyncio.create_task(_remove_player_after_grace(pin, sid))


@sio.event
async def join_lobby(sid, data):
    """Player joins a game lobby"""
    pin = data.get('pin')
    player_name = data.get('name')
    player_id = data.get('player_id')
    
    if not pin or not player_name:
        await sio.emit('error', {'message': 'Invalid data'}, room=sid)
        return

    reconnect_task = pending_player_disconnects.pop(sid, None)
    if reconnect_task:
        reconnect_task.cancel()
    
    # Join the room
    await sio.enter_room(sid, pin)
    
    # Initialize game data if not exists
    if pin not in active_games:
        active_games[pin] = {
            'players': {},
            'host_sid': None,
            'status': 'waiting',
            'current_question': 0,
            'current_question_data': None
        }

    # If this player reconnects, remove stale socket entries for same player_id/name.
    stale_sids = [
        existing_sid
        for existing_sid, existing_player in active_games[pin]['players'].items()
        if existing_sid != sid and (
            (player_id is not None and existing_player.get('player_id') == player_id) or
            existing_player.get('name') == player_name
        )
    ]
    for stale_sid in stale_sids:
        stale_task = pending_player_disconnects.pop(stale_sid, None)
        if stale_task:
            stale_task.cancel()
        del active_games[pin]['players'][stale_sid]
    
    # Add player to game
    active_games[pin]['players'][sid] = {
        'name': player_name,
        'player_id': player_id,
        'score': 0
    }
    
    # Notify all players in the lobby
    players_list = [
        {'name': p['name'], 'player_id': p['player_id']}
        for p in active_games[pin]['players'].values()
    ]
    
    await sio.emit('lobby_updated', {
        'players': players_list,
        'count': len(players_list)
    }, room=pin)

    # If player joins/reconnects while game is active, sync active state immediately.
    if active_games[pin]['status'] == 'active':
        await sio.emit('game_started', {
            'message': 'Game is starting!',
            'current_question': active_games[pin]['current_question']
        }, room=sid)

        if active_games[pin]['current_question_data'] is not None:
            await sio.emit('question_update', active_games[pin]['current_question_data'], room=sid)
    
    print(f"Player {player_name} joined lobby {pin}")


@sio.event
async def host_join(sid, data):
    """Host joins their game room"""
    pin = data.get('pin')
    
    if not pin:
        await sio.emit('error', {'message': 'Invalid PIN'}, room=sid)
        return
    
    await sio.enter_room(sid, pin)
    
    # Initialize or update game data
    if pin not in active_games:
        active_games[pin] = {
            'players': {},
            'host_sid': sid,
            'status': 'waiting',
            'current_question': 0,
            'current_question_data': None
        }
    else:
        active_games[pin]['host_sid'] = sid
    
    print(f"Host joined game {pin}")


@sio.event
async def start_game(sid, data):
    """Host starts the game"""
    pin = data.get('pin')
    
    if not pin or pin not in active_games:
        await sio.emit('error', {'message': 'Game not found'}, room=sid)
        return
    
    if active_games[pin]['host_sid'] != sid:
        await sio.emit('error', {'message': 'Only host can start the game'}, room=sid)
        return
    
    active_games[pin]['status'] = 'active'
    active_games[pin]['current_question'] = 0
    active_games[pin]['current_question_data'] = None
    
    # Notify all players
    await sio.emit('game_started', {
        'message': 'Game is starting!',
        'current_question': 0
    }, room=pin)
    
    print(f"Game {pin} started")


@sio.event
async def next_question(sid, data):
    """Host moves to next question"""
    pin = data.get('pin')
    question_index = data.get('question_index')
    question_data = data.get('question_data')
    
    if not pin or pin not in active_games:
        await sio.emit('error', {'message': 'Game not found'}, room=sid)
        return
    
    if active_games[pin]['host_sid'] != sid:
        await sio.emit('error', {'message': 'Only host can control questions'}, room=sid)
        return
    
    active_games[pin]['current_question'] = question_index
    
    # Send question to all players (without correct answer)
    player_question = {
        'index': question_index,
        'question_id': question_data.get('id') or question_data.get('question_id'),
        'question_text': question_data['question_text'],
        'options': question_data['options'],
        'time_limit': question_data['time_limit']
    }

    active_games[pin]['current_question_data'] = player_question
    
    await sio.emit('question_update', player_question, room=pin)
    print(f"Game {pin} moved to question {question_index}")


@sio.event
async def submit_answer(sid, data):
    """Player submits an answer"""
    pin = data.get('pin')
    answer = data.get('answer')
    time_taken = data.get('time_taken')
    player_id = data.get('player_id')
    question_id = data.get('question_id')
    
    if not all([pin, answer is not None, time_taken is not None]):
        await sio.emit('error', {'message': 'Invalid answer data'}, room=sid)
        return
    
    # Store the answer (you could emit to host for real-time feedback)
    await sio.emit('answer_received', {
        'player_id': player_id,
        'question_id': question_id
    }, room=sid)
    
    # Optionally notify host
    if pin in active_games and active_games[pin]['host_sid'] and sid in active_games[pin]['players']:
        await sio.emit('player_answered', {
            'player_name': active_games[pin]['players'][sid]['name'],
            'time_taken': time_taken
        }, room=active_games[pin]['host_sid'])


@sio.event
async def show_results(sid, data):
    """Host shows question results"""
    pin = data.get('pin')
    results = data.get('results')
    
    if not pin or pin not in active_games:
        return
    
    if active_games[pin]['host_sid'] != sid:
        return
    
    await sio.emit('results_update', results, room=pin)


@sio.event
async def end_game(sid, data):
    """Host ends the game"""
    pin = data.get('pin')
    final_results = data.get('final_results')
    
    if not pin or pin not in active_games:
        return
    
    if active_games[pin]['host_sid'] != sid:
        return
    
    active_games[pin]['status'] = 'finished'
    
    await sio.emit('game_ended', {
        'message': 'Game has ended!',
        'results': final_results
    }, room=pin)
    
    print(f"Game {pin} ended")


@sio.event
async def request_leaderboard(sid, data):
    """Send current leaderboard to client"""
    pin = data.get('pin')
    
    if not pin or pin not in active_games:
        return
    
    # Get current scores from database or in-memory store
    # This is a simplified version
    players_scores = [
        {
            'name': p['name'],
            'score': p['score'],
            'player_id': p['player_id']
        }
        for p in active_games[pin]['players'].values()
    ]
    
    # Sort by score
    players_scores.sort(key=lambda x: x['score'], reverse=True)
    
    await sio.emit('leaderboard_update', {
        'players': players_scores
    }, room=pin)


def calculate_score(is_correct: bool, time_taken: float, time_limit: int) -> int:
    """Calculate score based on correctness and speed"""
    if not is_correct:
        return 0
    
    base_points = settings.POINTS_CORRECT
    
    # Speed bonus: faster answers get more points
    time_ratio = max(0, (time_limit - time_taken) / time_limit)
    speed_bonus = int(settings.SPEED_BONUS_MAX * time_ratio)
    
    return base_points + speed_bonus
