from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import json
import uuid
import requests
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db


# --- Load environment ---
load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"


# --- Initialize Firebase lazily to avoid import-time failures on deploy ---
def ensure_firebase_initialized() -> bool:
    """Initialize Firebase with proper error handling for deployment"""
    if firebase_admin._apps:
        return True
    
    try:
        firebase_key_env = os.getenv("FIREBASE_KEY")
        cred = None
        
        if firebase_key_env:
            try:
                cred_dict = json.loads(firebase_key_env)
                cred = credentials.Certificate(cred_dict)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Warning: Failed to parse FIREBASE_KEY: {e}")
                cred = None
        
        if cred is None:
            key_path = os.path.join(os.getcwd(), "firebase_key.json")
            if os.path.exists(key_path):
                try:
                    cred = credentials.Certificate(key_path)
                except Exception as e:
                    print(f"Warning: Failed to load firebase_key.json: {e}")
                    cred = None
        
        if cred is None:
            print("Warning: No Firebase credentials found. Firebase features will be disabled.")
            return False
        
        database_url = os.getenv("FIREBASE_DATABASE_URL", "https://ai-games-b5c1b-default-rtdb.firebaseio.com/")
        firebase_admin.initialize_app(cred, {"databaseURL": database_url})
        return True
        
    except Exception as e:
        print(f"Warning: Firebase initialization failed: {e}")
        return False


# --- Groq API Call ---
def call_groq_api(prompt: str, max_tokens: int = 200) -> str:
    if not GROQ_KEY:
        return "⚠️ No API key found. Please set GROQ_API_KEY in your environment."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"API Error: {e}"
    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


# --- Firebase helpers ---
def get_room_ref(room_code: str):
    return db.reference(f"rooms/{room_code}")


def complete_sentence(text: str) -> str:
    if not text:
        return text
    if "." in text:
        return text.rsplit(".", 1)[0] + "."
    return text


def init_room(room_code: str) -> None:
    room_ref = get_room_ref(room_code)
    prompt = (
        "Create a funny, mysterious, and adventurous opening paragraph for a multiplayer story game. "
        "Include emojis and humor. Make sure the paragraph ends with a complete sentence and does not cut off."
    )
    initial_story = call_groq_api(prompt, max_tokens=50)
    initial_story = complete_sentence(initial_story)

    room_ref.set({
        "players": {},
        "story": initial_story,
        "options": {},
        "submitted": [],
    })


app = FastAPI(title="Multiplayer Story Game API")


@app.get("/")
def health_check():
    """Health check endpoint for deployment monitoring"""
    return {"status": "healthy", "message": "Multiplayer Story Game API is running"}


@app.get("/health")
def health():
    """Alternative health check endpoint"""
    return {"status": "ok"}


class RoomActionRequest(BaseModel):
    room_code: str
    username: str
    action: str  # join | submit | get_state
    option: Optional[str] = None  # Only required for 'submit' action


@app.post("/room-action")
def room_action(request: RoomActionRequest):
    if not ensure_firebase_initialized():
        raise HTTPException(status_code=500, detail="Firebase not configured. Set FIREBASE_KEY or include firebase_key.json.")
    room_ref = get_room_ref(request.room_code)
    room = room_ref.get()

    # --- Join Room ---
    if request.action == "join":
        if not room:
            init_room(request.room_code)
        players = room_ref.child("players").get() or {}
        if request.username not in players:
            room_ref.child("players").update({request.username: 0})
        # Return latest room state so clients can show the story immediately
        latest = room_ref.get() or {}
        return {"message": f"{request.username} joined room {request.room_code}", "room": latest}

    # --- Submit Option ---
    elif request.action == "submit":
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        if not request.option or not request.option.strip():
            raise HTTPException(status_code=400, detail="Option is required for submit")

        # Update the option and submitted list
        room_ref.child("options").update({request.username: request.option.strip()})

        current_submitted = set((room.get("submitted") or []))
        current_submitted.add(request.username)
        room_ref.update({"submitted": list(current_submitted)})

        # Refresh room snapshot to get latest data for this round
        room = room_ref.get() or {}
        players = room.get("players", {}) or {}
        submitted = set(room.get("submitted", []))

        # If all players have submitted, generate next story paragraph and score
        if players and len(submitted) == len(players):
            round_id = str(uuid.uuid4())
            options_now = room_ref.child("options").get() or {}
            combined_options = "\n".join([f"{user}: {opt}" for user, opt in options_now.items()])

            prompt = f"""
            Current story: {room.get('story', '')}
            Players submitted the following actions:
            {combined_options}
            Create one funny and chaotic story paragraph incorporating all these actions.
            Include emojis and humor. Make sure the paragraph ends with a complete sentence.
            """

            new_story = call_groq_api(prompt, max_tokens=600)
            new_story = complete_sentence(new_story)

            # Update story and reset round fields
            room_ref.update({
                "story": new_story,
                "options": {},
                "submitted": [],
                "round_id": round_id,
            })

            # Update player scores safely
            for player in players.keys():
                last_round = room_ref.child("players").child(player).child("last_round_scored").get()
                current_score = room_ref.child("players").child(player).child("score").get() or 0
                if last_round != round_id:
                    room_ref.child("players").child(player).update({
                        "score": current_score + 1,
                        "last_round_scored": round_id,
                    })

            # Return the updated story and room state in the response
            latest = room_ref.get() or {}
            return {
                "message": "Option submitted and story updated successfully",
                "story": latest.get("story", ""),
                "round_id": latest.get("round_id"),
                "room": latest,
            }

        # Not all players submitted yet; return current state so client can wait/poll
        latest = room_ref.get() or {}
        return {"message": "Option submitted", "room": latest}

    # --- Get Current State ---
    elif request.action == "get_state":
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        return room

    else:
        raise HTTPException(status_code=400, detail="Invalid action")

