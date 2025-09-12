from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any

# Import the game logic and global store from the Streamlit app module
# Run uvicorn with working directory set to this folder:
#   cd "AI Bingo" && uvicorn bingo_api:api --host 0.0.0.0 --port 8000 --reload
from app import BingoGame, BingoCard, get_global_games  # type: ignore


class BingoActionRequest(BaseModel):
    action: str  # create | join | start | call | mark | state | restart_round | leave
    room_code: Optional[str] = None
    username: Optional[str] = None
    number: Optional[int] = None  # for mark only
    new_cards: Optional[bool] = False  # for restart_round


def serialize_game(room_code: str, game: BingoGame, for_user: Optional[str] = None) -> Dict[str, Any]:
    players = list(game.players.keys())
    state: Dict[str, Any] = {
        "room_code": room_code,
        "players": players,
        "started": game.started,
        "winner": game.winner,
        "host_name": game.host_name,
        "called_numbers": list(game.called_numbers_ordered),
    }
    if for_user and for_user in game.players:
        card = game.players[for_user]
        state["card"] = {
            "grid": [[card.card[c][r] for c in range(5)] for r in range(5)],
            "marked": list(sorted([[c, r] for (c, r) in card.marked])),
        }
    return state


# Router for inclusion into a larger app (with prefix and tag for docs grouping)
router = APIRouter(prefix="/api/Bingo", tags=["Bingo"])


@router.get("/", summary="Bingo service status")
def api_root():
    return {"status": "ok", "service": "Bingo Game API"}


@router.get("/health", summary="Health check")
def api_health():
    return {"status": "healthy"}


@router.post("/Action", summary="Perform a Bingo action")
def bingo_action(req: BingoActionRequest):
    games = get_global_games()
    action = (req.action or "").strip().lower()

    if action == "create":
        game = BingoGame()
        room_code = game.generate_room_code()
        if req.username:
            game.host_name = req.username
            game.add_player(req.username)
        games[room_code] = game
        return {"message": "room created", "room": serialize_game(room_code, game, req.username)}

    if not req.room_code:
        raise HTTPException(status_code=400, detail="room_code is required")

    game: Optional[BingoGame] = games.get(req.room_code)
    if not game:
        raise HTTPException(status_code=404, detail="Room not found")

    if action == "join":
        if not req.username or not req.username.strip():
            raise HTTPException(status_code=400, detail="username is required")
        if not game.host_name:
            game.host_name = req.username
        game.add_player(req.username)
        return {"message": f"{req.username} joined", "room": serialize_game(req.room_code, game, req.username)}

    if action == "start":
        if req.username != game.host_name:
            raise HTTPException(status_code=403, detail="Only host can start")
        game.start_game()
        return {"message": "game started", "room": serialize_game(req.room_code, game, req.username)}

    if action == "call":
        if req.username != game.host_name:
            raise HTTPException(status_code=403, detail="Only host can call numbers")
        if not game.started:
            raise HTTPException(status_code=400, detail="Game not started")
        num = game.call_number()
        if num is None:
            return {"message": "no numbers remaining", "room": serialize_game(req.room_code, game, req.username)}
        return {"message": "number called", "number": num, "room": serialize_game(req.room_code, game, req.username)}

    if action == "mark":
        if not req.username or req.number is None:
            raise HTTPException(status_code=400, detail="username and number are required")
        player = game.players.get(req.username)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found in room")
        if req.number != 0:
            if req.number not in game.called_numbers:
                raise HTTPException(status_code=400, detail="Number not called yet")
            pos = player.find_position(req.number)
            if pos is None:
                raise HTTPException(status_code=400, detail="Number not on your card")
            if pos != (2, 2):
                player.marked.add(pos)
        game.check_winner()
        return {"message": "marked", "room": serialize_game(req.room_code, game, req.username)}

    if action == "state":
        return {"message": "ok", "room": serialize_game(req.room_code, game, req.username)}

    if action == "restart_round":
        if req.username != game.host_name:
            raise HTTPException(status_code=403, detail="Only host can restart round")
        game.reset_round(keep_cards=not bool(req.new_cards))
        return {"message": "round reset", "room": serialize_game(req.room_code, game, req.username)}

    if action == "leave":
        if not req.username:
            raise HTTPException(status_code=400, detail="username is required")
        try:
            if req.username in game.players:
                del game.players[req.username]
        except Exception:
            pass
        return {"message": "left room", "room": serialize_game(req.room_code, game)}

    raise HTTPException(status_code=400, detail="Invalid action")


# Optional standalone FastAPI for running this module alone
api = FastAPI(title="Bingo Game API (Standalone)")
api.include_router(router)
