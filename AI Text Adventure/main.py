# from fastapi import FastAPI, Request
# from fastapi.responses import RedirectResponse

# app = FastAPI()

# @app.get("/launch_game")
# async def launch_game(request: Request, game: str):
#     """
#     Single endpoint for launching games.
#     Redirects user to the correct Streamlit app/game.
#     """
    
#     if game == "AI Text Adventure":
#         return RedirectResponse(url="https://ai-games-1-lvxs.onrender.com/ai_text_adventure")
#     else:
#         return {"error": f"Unknown game: {game}"}





# ✅ Features of this API
# Join Room: /join-room (POST) → body: { "room_code": "...", "username": "..." }
# Submit Option: /submit-option (POST) → body: { "room_code": "...", "username": "...", "option": "..." }
# Get Room State: /get-room/{room_code} (GET) → returns current story, leaderboard, submitted options, etc.
# Automatic Story Update: When all players submit, the story is updated and scores are incremented.





# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel
# from dotenv import load_dotenv

# # --- FastAPI App ---
# app = FastAPI(title="Multiplayer Story Game API")

# # --- Request Models ---
# class JoinRoomRequest(BaseModel):
#     room_code: str
#     username: str

# class SubmitOptionRequest(BaseModel):
#     room_code: str
#     username: str
#     option: str

# # --- API Endpoints ---

# @app.post("/join-room")
# def join_room(request: JoinRoomRequest):
#     room_ref = get_room_ref(request.room_code)
#     if not room_ref.get():
#         init_room(request.room_code)
#     players = room_ref.child("players").get() or {}
#     if request.username not in players:
#         room_ref.child("players").update({request.username: 0})
#     return {"message": f"{request.username} joined room {request.room_code}!"}

# @app.post("/submit-option")
# def submit_option(request: SubmitOptionRequest):
#     room_ref = get_room_ref(request.room_code)
#     room = room_ref.get()
#     if not room:
#         raise HTTPException(status_code=404, detail="Room not found")

#     # Update option
#     room_ref.child("options").update({request.username: request.option})
#     submitted = set(room.get("submitted", []))
#     submitted.add(request.username)
#     room_ref.update({"submitted": list(submitted)})

#     # Check if all players submitted
#     players = room.get("players", {})
#     if len(submitted) == len(players) and players:
#         round_id = str(uuid.uuid4())
#         combined_options = "\n".join([f"{u}: {o}" for u, o in room["options"].items()])
#         prompt = f"""
#         Current story: {room['story']}
#         Players submitted the following actions:
#         {combined_options}
#         Create one funny and chaotic story paragraph incorporating all these actions.
#         Include emojis and humor. Make sure the paragraph ends with a complete sentence.
#         """
#         new_story = call_groq_api(prompt, max_tokens=600)
#         new_story = complete_sentence(new_story)
#         # Update story and reset options/submitted
#         room_ref.update({
#             "story": new_story,
#             "options": {},
#             "submitted": [],
#             "round_id": round_id
#         })
#         # Update player scores
#         for player in players.keys():
#             last_round = room_ref.child("players").child(player).child("last_round_scored").get()
#             current_score = room_ref.child("players").child(player).child("score").get() or 0
#             if last_round != round_id:
#                 room_ref.child("players").child(player).update({
#                     "score": current_score + 1,
#                     "last_round_scored": round_id
#                 })

#     return {"message": "Option submitted successfully"}

# @app.get("/get-room/{room_code}")
# def get_room(room_code: str):
#     room_ref = get_room_ref(room_code)
#     room = room_ref.get()
#     if not room:
#         raise HTTPException(status_code=404, detail="Room not found")
#     return room


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app import *


app = FastAPI(title="Multiplayer Story Game Single Endpoint API")

# --- Models ---
class RoomActionRequest(BaseModel):
    room_code: str
    username: str
    action: str  # join | submit | get_state
    option: str = None  # only for submit


# --- Single Endpoint ---
@app.post("/room-action")
def room_action(request: RoomActionRequest):
    room_ref = get_room_ref(request.room_code)
    room = room_ref.get()

    # --- Join Room ---
    if request.action == "join":
        if not room:
            init_room(request.room_code)
        players = room_ref.child("players").get() or {}
        if request.username not in players:
            room_ref.child("players").update({request.username: 0})
        return {"message": f"{request.username} joined {request.room_code}"}

    # --- Submit Option ---
    elif request.action == "submit":
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if not request.option:
            raise HTTPException(status_code=400, detail="Option is required for submit")
        room_ref.child("options").update({request.username: request.option})
        submitted = set(room.get("submitted", []))
        submitted.add(request.username)
        room_ref.update({"submitted": list(submitted)})

        # --- Update story if all players submitted ---
        players = room.get("players", {})
        if len(submitted) == len(players) and players:
            round_id = str(uuid.uuid4())
            combined_options = "\n".join([f"{u}: {o}" for u, o in room["options"].items()])
            prompt = f"""
            Current story: {room['story']}
            Players submitted:
            {combined_options}
            Create one funny and chaotic paragraph incorporating all actions. End with a complete sentence.
            """
            new_story = call_groq_api(prompt, max_tokens=600)
            new_story = complete_sentence(new_story)
            room_ref.update({"story": new_story, "options": {}, "submitted": [], "round_id": round_id})

            # Update scores
            for player in players.keys():
                last_round = room_ref.child("players").child(player).child("last_round_scored").get()
                current_score = room_ref.child("players").child(player).child("score").get() or 0
                if last_round != round_id:
                    room_ref.child("players").child(player).update({"score": current_score + 1, "last_round_scored": round_id})
        return {"message": "Option submitted successfully"}

    # --- Get Current State ---
    elif request.action == "get_state":
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        return room

    else:
        raise HTTPException(status_code=400, detail="Invalid action")

