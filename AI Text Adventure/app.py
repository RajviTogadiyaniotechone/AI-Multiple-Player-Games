import streamlit as st
import requests
import os
import json
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
import uuid
round_id = str(uuid.uuid4())

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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


# --- Load Environment Variables ---
load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"


# --- Initialize Firebase ---
if not firebase_admin._apps:
    firebase_key = os.getenv("FIREBASE_KEY")
    if firebase_key:
        cred_dict = json.loads(firebase_key)  # parse JSON from env var
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred, {
            "databaseURL": "https://ai-games-b5c1b-default-rtdb.firebaseio.com/"
        })
    else:
        raise ValueError("FIREBASE_KEY environment variable not set")

# --- Groq API Call ---
def call_groq_api(prompt, max_tokens=200):
    if not GROQ_KEY:
        return "⚠️ No API key found. Please set GROQ_API_KEY in your environment."
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    payload = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"API Error: {e}"
    data = response.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

# --- Helper: get room reference ---
def get_room_ref(room_code):
    return db.reference(f"rooms/{room_code}")

# --- Initialize a room in Firebase ---
def init_room(room_code):
    room_ref = get_room_ref(room_code)
    
    # --- Create dynamic initial story ---
    prompt = "Create a funny, mysterious, and adventurous opening paragraph for a multiplayer story game. Include emojis and humor.Make sure the paragraph ends with a complete sentence and does not cut off."
    initial_story = call_groq_api(prompt, max_tokens=50)  # adjust tokens as needed

    # Post-process to ensure complete sentence
    if "." in initial_story:
        initial_story = initial_story.rsplit(".", 1)[0] + "."

    # --- Set room in Firebase ---
    room_ref.set({
        "players": {},     
        "story": initial_story,
        "options": {},
        "submitted": []
    })

# --- UI: Room and Username ---
room_code = st.text_input("Enter Room Code (same for all players to join):")
username = st.text_input("Enter your Username:")

if st.button("Join Room") and room_code and username:
    room_ref = get_room_ref(room_code)
    if not room_ref.get():
        init_room(room_code)
    players = room_ref.child("players").get() or {}
    if username not in players:
        room_ref.child("players").update({username: 0})
    st.session_state.current_room = room_code
    st.session_state.current_user = username
    st.success(f"{username} joined room {room_code}!")

# --- Main Game UI ---
if "current_room" in st.session_state and "current_user" in st.session_state:
    room_code = st.session_state.current_room
    username = st.session_state.current_user
    room_ref = get_room_ref(room_code)
    room = room_ref.get()

    st.subheader("Current Story:")
    st.write(room["story"])

    # --- Submit option ---
    st.subheader("Your Funny Option:")
    user_option = st.text_input("Type a funny action or idea:", key=f"option_{username}")
    if st.button("Submit Option", key=f"submit_{username}"):
        if user_option.strip():
            room_ref.child("options").update({username: user_option})
            submitted = set(room.get("submitted", []))
            submitted.add(username)
            room_ref.update({"submitted": list(submitted)})
            st.success("Option submitted!")

    # --- Check if all players submitted ---
    players = room.get("players", {})
    submitted = set(room.get("submitted", []))

    # Generate a unique round ID only when all players submitted
    if len(submitted) == len(players) and players:
        round_id = str(uuid.uuid4())  # new round
        combined_options = "\n".join([f"{u}: {o}" for u, o in room["options"].items()])

        prompt = f"""
        Current story: {room['story']}
        Players submitted the following actions:
        {combined_options}
        Create one funny and     chaotic story paragraph incorporating all these actions.
        Include emojis and humor. Make sure the paragraph ends with a complete sentence.
        """

        # Ensure complete sentence
        def complete_sentence(text):
            if "." in text:
                return text.rsplit(".", 1)[0] + "."
            return text
        
        new_story = call_groq_api(prompt, max_tokens=600)
        new_story = complete_sentence(new_story) 

        # Update story and reset options/submitted
        room_ref.update({
            "story": new_story,
            "options": {},
            "submitted": [],
            "round_id": round_id
        })

        # Update player scores safely
        for player in players.keys():
            last_round = room_ref.child("players").child(player).child("last_round_scored").get()
            current_score = room_ref.child("players").child(player).child("score").get() or 0
            if last_round != round_id:
                room_ref.child("players").child(player).update({
                    "score": current_score + 1,
                    "last_round_scored": round_id
                })

    # --- Display updated leaderboard ---
    st.subheader("🏆 Leaderboard")
    players = room_ref.child("players").get() or {}

    def get_score(data):
        return data.get("score", 0) if isinstance(data, dict) else data

    for player, data in sorted(players.items(), key=lambda x: -get_score(x[1])):
        st.write(f"{player}: {get_score(data)} points")

    # --- Auto-refresh every 5s to sync ---
    st_autorefresh(interval=5000, key="refresh")

