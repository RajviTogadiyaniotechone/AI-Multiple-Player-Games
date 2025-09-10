from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app import *  # Import necessary functions and variables from app.py

app = FastAPI(title="Multiplayer Story Game API")

# --- Models ---
class RoomActionRequest(BaseModel):
    room_code: str
    username: str
    action: str  # join | submit | get_state
    option: str = None  # Only required for 'submit' action

# --- Helper: get room reference (already in app.py) ---
def get_room_ref(room_code):
    return db.reference(f"rooms/{room_code}")

# --- Single Endpoint ---
@app.post("/room-action")
def room_action(request: RoomActionRequest):
    room_ref = get_room_ref(request.room_code)
    room = room_ref.get()

    # --- Join Room ---
    if request.action == "join":
        if not room:
            init_room(request.room_code)  # Initialize room if not existing
        players = room_ref.child("players").get() or {}
        if request.username not in players:
            room_ref.child("players").update({request.username: 0})  # Set initial score for the player
        return {"message": f"{request.username} joined room {request.room_code}"}

    # --- Submit Option ---
    elif request.action == "submit":
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if not request.option:
            raise HTTPException(status_code=400, detail="Option is required for submit")

        # Update the options for the room
        room_ref.child("options").update({request.username: request.option})
        submitted = set(room.get("submitted", []))
        submitted.add(request.username)
        room_ref.update({"submitted": list(submitted)})

        # --- Update story if all players have submitted ---
        players = room.get("players", {})
        if len(submitted) == len(players) and players:
            round_id = str(uuid.uuid4())  # New round ID
            combined_options = "\n".join([f"{u}: {o}" for u, o in room["options"].items()])

            # Create prompt for story generation
            prompt = f"""
            Current story: {room['story']}
            Players submitted the following actions:
            {combined_options}
            Create one funny and chaotic story paragraph incorporating all actions. 
            Make sure the paragraph ends with a complete sentence and includes humor and emojis.
            """
            new_story = call_groq_api(prompt, max_tokens=600)
            new_story = complete_sentence(new_story)  # Ensure it ends with a complete sentence

            # Update the room in Firebase with the new story and reset options/submitted
            room_ref.update({
                "story": new_story,
                "options": {},
                "submitted": [],
                "round_id": round_id
            })

            # Update player scores
            for player in players.keys():
                last_round = room_ref.child("players").child(player).child("last_round_scored").get()
                current_score = room_ref.child("players").child(player).child("score").get() or 0
                if last_round != round_id:  # Update score if not already scored in this round
                    room_ref.child("players").child(player).update({
                        "score": current_score + 1,
                        "last_round_scored": round_id
                    })
            return {"message": "Option submitted and story updated successfully"}

    # --- Get Current State ---
    elif request.action == "get_state":
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        return room

    else:
        raise HTTPException(status_code=400, detail="Invalid action")

