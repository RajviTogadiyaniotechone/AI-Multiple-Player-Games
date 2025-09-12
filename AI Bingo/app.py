import random
import streamlit as st
from typing import List, Optional, Tuple
import string
import time

# Bingo Number Set
BINGO_NUMBERS = list(range(1, 76))
BINGO_HEADERS = ["B", "I", "N", "G", "O"]
BINGO_COLORS = {
    "B": "#629FCA",
    "I": "#222f5b",
    "N": "#2a623d",
    "G": "#d62728",
    "O": "#9467bd",
}


def number_to_letter(number: int) -> str:
    if 1 <= number <= 15:
        return "B"
    if 16 <= number <= 30:
        return "I"
    if 31 <= number <= 45:
        return "N"
    if 46 <= number <= 60:
        return "G"
    return "O"


@st.cache_resource
def get_global_games() -> dict:
    """Global, cross-session storage for rooms and games."""
    return {}


class BingoCard:
    def __init__(self):
        self.card = self.generate_card()
        self.marked = set()
        # Auto-mark the Free center
        self.marked.add((2, 2))

    def generate_card(self) -> List[List[int]]:
        """Generate a random Bingo card as 5 columns (B, I, N, G, O)."""
        card = []
        for i in range(5):
            column = random.sample(range(i * 15 + 1, (i + 1) * 15 + 1), 5)
            card.append(column)
        # Center is Free conceptually; we keep the number but treat (2,2) as marked
        return card

    def find_position(self, number: int) -> Optional[Tuple[int, int]]:
        for col_index in range(5):
            if number in self.card[col_index]:
                row_index = self.card[col_index].index(number)
                return col_index, row_index
        return None

    def toggle_mark(self, col_index: int, row_index: int):
        key = (col_index, row_index)
        if key in self.marked:
            # Do not allow unmarking the Free space
            if key == (2, 2):
                return
            self.marked.remove(key)
        else:
            self.marked.add(key)

    def clear_marks(self):
        self.marked = {(2, 2)}

    def check_bingo(self) -> bool:
        """Check rows, columns, and diagonals for Bingo"""
        # Columns
        for c in range(5):
            if all((c, r) in self.marked for r in range(5)):
                return True
        # Rows
        for r in range(5):
            if all((c, r) in self.marked for c in range(5)):
                return True
        # Diagonals
        if all((i, i) in self.marked for i in range(5)):
            return True
        if all((i, 4 - i) in self.marked for i in range(5)):
            return True
        return False


class BingoGame:
    def __init__(self, host_name: Optional[str] = None):
        self.players = {}
        self.called_numbers_ordered: List[int] = []
        self.started = False
        self.winner: Optional[str] = None
        self.host_name: Optional[str] = host_name
        self.last_called_ts: Optional[float] = None
        self.call_interval_sec: int = 5
        self.winner_announced_ts: Optional[float] = None

    @property
    def called_numbers(self) -> set:
        return set(self.called_numbers_ordered)

    def add_player(self, name: str):
        if name not in self.players:
            self.players[name] = BingoCard()
            return True
        return False

    def generate_room_code(self) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def start_game(self):
        self.started = True
        self.winner = None
        # Force the first call to happen immediately on the next refresh
        self.last_called_ts = 0.0
        self.winner_announced_ts = None

    def call_number(self) -> Optional[int]:
        remaining_numbers = list(set(BINGO_NUMBERS) - self.called_numbers)
        if not remaining_numbers:
            return None
        number = random.choice(remaining_numbers)
        self.called_numbers_ordered.append(number)
        return number

    def maybe_auto_call(self):
        """Call next number automatically if interval elapsed."""
        if not self.started or self.winner is not None:
            return
        now = time.time()
        if self.last_called_ts is None or now - self.last_called_ts >= self.call_interval_sec:
            num = self.call_number()
            self.last_called_ts = now
            return num
        return None

    def check_winner(self) -> Optional[str]:
        for player_name, card in self.players.items():
            if card.check_bingo():
                if self.winner is None:
                    self.winner = player_name
                    self.winner_announced_ts = time.time()
                return player_name
        return None

    def reset_round(self, keep_cards: bool = True):
        self.called_numbers_ordered = []
        self.winner = None
        self.started = False
        self.last_called_ts = None
        self.winner_announced_ts = None
        if keep_cards:
            for card in self.players.values():
                card.clear_marks()
        else:
            for name in list(self.players.keys()):
                self.players[name] = BingoCard()


# ------------ UI Helpers ------------

def initialize_state():
    if "room_code" not in st.session_state:
        st.session_state.room_code = None
    if "player_name" not in st.session_state:
        st.session_state.player_name = None
    if "is_host" not in st.session_state:
        st.session_state.is_host = False


def get_current_game() -> Optional[BingoGame]:
    room_code = st.session_state.get("room_code")
    if not room_code:
        return None
    return get_global_games().get(room_code)


def render_header(title: str):
    st.title("Virtual Bingo Game 🎲")
    st.caption("Easy, friendly, and fun for everyone!")
    st.subheader(title)


def render_called_chips(numbers: List[int]):
    if not numbers:
        st.write("None yet")
        return
    chips = []
    for n in sorted(numbers):
        letter = number_to_letter(n)
        color = BINGO_COLORS[letter]
        chips.append(
            f'<span style="display:inline-block;margin:4px;padding:6px 10px;border-radius:16px;background:{color};color:white;font-weight:600">{letter}-{n}</span>'
        )
    st.markdown(" ".join(chips), unsafe_allow_html=True)


def render_sidebar():
    game = get_current_game()
    with st.sidebar:
        st.markdown("## Room")
        if st.session_state.room_code:
            st.code(st.session_state.room_code)
        else:
            st.write("No room selected")

        if game and game.host_name:
            st.markdown(f"**Host:** {game.host_name}")
        players = list(game.players.keys()) if game else []
        st.markdown("**Players:**")
        if players:
            st.write("\n".join([f"- {p}" for p in players]))
        else:
            st.write("(none)")

        if game and game.called_numbers_ordered:
            st.markdown("**Called Numbers:**")
            render_called_chips(game.called_numbers_ordered)

        st.markdown("---")
        if st.button("Leave Room"):
            # Remove player from room
            if game and st.session_state.player_name in game.players:
                try:
                    del game.players[st.session_state.player_name]
                except Exception:
                    pass
            st.session_state.player_name = None
            st.session_state.is_host = False
            st.session_state.room_code = None
            st.rerun()


def render_landing():
    render_header("Join a room or create a new one")
    st.write("Enter a room code to join your friends, or generate a brand new room and share the code.")
    code = st.text_input("Room Code", value="", placeholder="e.g., ABC123")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Join Room"):
            if code and code in get_global_games():
                st.session_state.room_code = code
            else:
                st.warning("Room not found. Check the code or create a new room.")
    with col2:
        if st.button("Generate Room Code", type="secondary"):
            game = BingoGame()
            room_code = game.generate_room_code()
            get_global_games()[room_code] = game
            st.session_state.room_code = room_code
            st.session_state.is_host = True

    if st.session_state.room_code:
        st.success(f"Room ready: {st.session_state.room_code}")
        st.info("Now enter your name to join the room.")


def render_name_entry():
    game = get_current_game()
    if not game:
        return

    name = st.text_input("Your Name", value=st.session_state.get("player_name") or "", placeholder="Type your display name")
    st.caption("Tip: Share the room code with friends so they can join.")
    if st.button("Enter Room", type="primary"):
        if not name.strip():
            st.warning("Please enter a valid name.")
            return
        st.session_state.player_name = name.strip()
        # Set host name if this user is host and not yet set
        if st.session_state.is_host and not game.host_name:
            game.host_name = st.session_state.player_name
        added = game.add_player(st.session_state.player_name)
        if added:
            st.success(f"{st.session_state.player_name} joined room {st.session_state.room_code}")
        else:
            st.info("Welcome back!")

    with st.expander("Room Details", expanded=True):
        st.markdown(f"**Room Code:** `{st.session_state.room_code}`")
        st.markdown("**Share this code with friends to join!**")


def render_lobby():
    game = get_current_game()
    if not game:
        return

    render_header("Let's The Game Begin..:video_game:")
    st.markdown(f"**Room Code:** `{st.session_state.room_code}`")
    if game.host_name:
        st.markdown(f"**Host:** {game.host_name}")

    # If a winner already exists, show the banner here too so late joiners or players in lobby see it
    if game.winner:
        render_winner_image_banner(game.winner)
        st.info("The game is over.")
        # Give a simple leave option
        if st.button("Leave Room"):
            try:
                if st.session_state.player_name in game.players:
                    del game.players[st.session_state.player_name]
            except Exception:
                pass
            st.session_state.player_name = None
            st.session_state.is_host = False
            st.session_state.room_code = None
            st.rerun()
        # Refresh briefly then return (no start controls when round ended)
        time.sleep(1)
        st.rerun()
        return

    player_list = list(game.players.keys())
    st.markdown("**Players in room:**")
    if player_list:
        st.write(", ".join(player_list))
    else:
        st.write("Waiting for players…")

    is_host = st.session_state.is_host and st.session_state.player_name == game.host_name

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Copy Room Code"):
            st.success("Room code copied! Share it with friends.")
    with col2:
        if is_host:
            can_start = len(player_list) >= 1
            start_disabled = not can_start
            if st.button("Start Game", disabled=start_disabled, type="primary"):
                game.start_game()
                st.rerun()
        else:
            st.info("Waiting for host to start the game…")

    # Auto-refresh the lobby every second so all clients see when the host starts
    time.sleep(1)
    st.rerun()


def render_card_grid(game: BingoGame, card: BingoCard):
    st.caption("Click a number to mark it once the host calls it. The Free center is already marked.")
    # Headers
    header_cols = st.columns(5)
    for i, h in enumerate(BINGO_HEADERS):
        header_cols[i].markdown(f"<div style='text-align:left;font-weight:900;color:{BINGO_COLORS[h]}'>{h}</div>", unsafe_allow_html=True)

    # Rows
    for row_index in range(5):
        cols = st.columns(5)
        for col_index in range(5):
            value = card.card[col_index][row_index]
            is_free = (col_index, row_index) == (2, 2)
            is_marked = (col_index, row_index) in card.marked
            is_called = is_free or value in game.called_numbers
            label = "Free" if is_free else f"{number_to_letter(value)}-{value}"
            button_key = f"cell_{st.session_state.room_code}_{st.session_state.player_name}_{col_index}_{row_index}"
            button_label = f"✅ {label}" if is_marked else label
            # Disable if number not called yet or the game already has a winner
            disabled = (game.winner is not None) or (not is_called)
            if cols[col_index].button(button_label, key=button_key, disabled=disabled):
                if is_called and game.winner is None:
                    card.toggle_mark(col_index, row_index)
                    game.check_winner()
                    st.rerun()

def render_game():
    game = get_current_game()
    if not game:
        return

    # Auto-call logic (host drives calling to avoid races)
    is_host = st.session_state.is_host and st.session_state.player_name == game.host_name
    if is_host and game.started and game.winner is None:
        called = game.maybe_auto_call()
        if called is not None:
            st.rerun()

    render_header("Game In Progress")

    current_called = game.called_numbers_ordered[-1] if game.called_numbers_ordered else None

    top_cols = st.columns(2)
    with top_cols[0]:
        st.markdown("**Latest Number:**")
        if current_called is not None:
            st.success(f"{number_to_letter(current_called)}-{current_called}")
        else:
            st.info("No numbers called yet.")
        

    with top_cols[1]:
        if game.winner:
            st.subheader(f"🎉 {game.winner} has BINGO! 🎉")
        else:
            st.info("Numbers are called automatically every 5 seconds…")

    # Player card
    st.markdown("---")
    st.markdown(f"**Your card, {st.session_state.player_name}:**")
    player_card = game.players.get(st.session_state.player_name)
    if not player_card:
        st.warning("You are not in this room. Rejoin from the landing page.")
        return

    render_card_grid(game, player_card)

    # Winner check and message visible to all users
    if game.winner:
        # Stop auto-calling by marking game as not started
        game.started = False
        # Celebration visible on refresh for all users
        st.balloons()
        try:
            st.snow()
        except Exception:
            pass
        render_winner_image_banner(game.winner)
        
        # Single restart option (host only): reset everything back to landing
        if st.session_state.player_name == game.host_name:
            if st.button("Restart Game"):
                # Remove the existing room entirely
                try:
                    old_code = st.session_state.room_code
                    if old_code in get_global_games():
                        del get_global_games()[old_code]
                except Exception:
                    pass
                # Clear local session to return to landing (fresh flow)
                try:
                    st.session_state.clear()
                except Exception:
                    st.session_state.room_code = None
                    st.session_state.player_name = None
                    st.session_state.is_host = False
                st.rerun()

        # For about 3 seconds after first announce, keep clients refreshing to pick up banner
        if game.winner_announced_ts and (time.time() - game.winner_announced_ts) < 3:
            time.sleep(0.8)
            st.rerun()
    else:
        winner = game.check_winner()
        if winner:
            # Trigger a quick rerun so everyone sees the winner promptly
            st.rerun()

    # Lightweight auto-refresh for all users while the game runs
    if game.started and game.winner is None:
        time.sleep(1)
        st.rerun()


def render_winner_image_banner(winner_name: str):
    # Inline SVG trophy + confetti banner
    svg = f"""
    <div style='margin-top:12px;padding:16px;border-radius:12px;background:#e6ffed;border:2px solid #b7eb8f;display:flex;align-items:center;gap:12px;justify-content:center;'>
      <svg width='40' height='40' viewBox='0 0 64 64' xmlns='http://www.w3.org/2000/svg'>
        <g fill='none' fill-rule='evenodd'>
          <path d='M12 10h40v10a16 16 0 0 1-16 16h-8A16 16 0 0 1 12 20V10z' fill='#f4c542'/>
          <path d='M24 36h16v6a8 8 0 0 1-8 8 8 8 0 0 1-8-8v-6z' fill='#cfa12a'/>
          <rect x='28' y='50' width='8' height='4' rx='1' fill='#8c6d1f'/>
          <rect x='22' y='54' width='20' height='4' rx='1' fill='#8c6d1f'/>
          <path d='M12 14H6a6 6 0 0 0 6 6v-6zm40 0h6a6 6 0 0 1-6 6v-6z' fill='#f4c542'/>
          <circle cx='10' cy='6' r='2' fill='#ff6b6b'/>
          <circle cx='54' cy='6' r='2' fill='#6bc1ff'/>
          <circle cx='6' cy='20' r='2' fill='#6bff95'/>
          <circle cx='58' cy='20' r='2' fill='#ffd36b'/>
        </g>
      </svg>
      <div style='font-weight:900;font-size:18px;color:#0f5132;'>🎉 {winner_name} wins the game!</div>
    </div>
    """
    st.markdown(svg, unsafe_allow_html=True)


def main():
    initialize_state()
    render_sidebar()

    # Step 1: Choose / Create room
    if not st.session_state.room_code:
        render_landing()
        # If room established, move to name entry
        if st.session_state.room_code and not st.session_state.player_name:
            render_name_entry()
        return

    # Step 2: Enter name if not yet set
    if not st.session_state.player_name:
        render_name_entry()
        return

    # With room and name set, get game
    game = get_current_game()
    if not game:
        st.warning("Room not found. Please go back and create/join again.")
        # Clear session to restart flow
        st.session_state.room_code = None
        st.session_state.player_name = None
        st.session_state.is_host = False
        return

    # Step 3: Lobby or Game
    if not game.started:
        render_lobby()
    else:
        render_game()


if __name__ == "__main__":
    main()
