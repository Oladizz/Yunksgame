# Yunks Game Bot 2.0.1 Blueprint

This blueprint outlines the development plan for the Yunks Game Bot v2.0.1. Each feature will be implemented, unit tested, and then manually tested before moving to the next.

## 1. Core Infrastructure & Setup
- [X] **Project Setup:** Create the basic directory structure, `requirements.txt`, `Dockerfile`, and initial `bot_main.py` in `yunks_game_2_0_1`.
- [X] **Logging:** Implement structured logging (`structlog`).
- [X] **Database Module:** Integrate Firestore connection (`firebase-admin`).
- [X] **Telegram Bot Setup:** Initialize `python-telegram-bot` Application.
- [X] **Error Handling:** Implement robust error handling for Telegram updates.

## 2. Core Bot Features
- [X] **User Recognition & XP:**
    - [X] Users are added to the database on their first message.
    - [X] Each message grants 1 XP.
- [X] **Admin Check Decorator:** Create `@is_admin` decorator to restrict commands.
- [X] **Main Menu (`/start`):**
    - [X] Welcome message and main menu buttons (Profile, Leaderboard, Play a Game, How to Play).
    - [X] Handles both command and callback queries.
- [X] **User Profile (`/menu` & 'My Profile' button):**
    - [X] Displays user's username and current XP.
- [X] **Leaderboard (`/leaderboard` & 'Leaderboard' button):**
    - [X] Displays top N users by XP.
    - [X] Handles optional limit argument.
- [X] **Help Command (`/help` & 'How to Play' button):**
    - [X] Detailed guide to all bot commands and features.
- [X] **Bot Mention Handler:** Respond when the bot is mentioned.

## 3. Action Commands
- [X] **Steal XP (`/steal`):**
    - [X] Requires replying to a user.
    - [X] Cooldown mechanism (1 hour).
    - [X] Success chance (50%).
    - [X] Steals 5-15 XP on success.
    - [X] Loses 5 XP on failure (penalty).
- [X] **Give XP (`/give`):**
    - [X] Requires replying to a user and specifying an amount.
    - [X] Transfers XP from sender to recipient.
    - [X] Checks if sender has sufficient XP.

## 4. Admin Commands
- [X] **Award XP (`/awardxp`):**
    - [X] Admin-only command.
    - [X] Requires replying to a user and specifying an amount.
    - [X] Awards XP to the target user.
- [X] **End Game (`/endgame`):**
    - [X] Admin-only command.
    - [X] Ends any active game in the current chat.

## 5. Game Features
- [X] **"Guess the Number" Game:**
    - [X] `/start_game` command to start.
    - [X] Game logic: random number 1-100, 7 tries, feedback (too high/low).
    - [X] XP awards (base + bonus up to 3 XP).
- [X] **"Last Person Standing" Game:**
    - [X] `/lastman` command to start a lobby.
    - [X] Lobby management (join, leave, start game).
    - [X] Elimination mechanics (random elimination after a delay).
    - [X] Last 3 players win.
    - [X] XP awards for winners.
- [X] **"Last Message Wins" Game:**
    - [X] `/lmw` command to start a lobby.
    - [X] Lobby management (join, leave, start game).
    - [X] Entry XP cost and XP pool.
    - [X] Countdown timer.
    - [X] Winner is the last person to send a message before the timer ends.
    - [X] Player can only send one message.
    - [X] XP awards (entire pool to the winner).

## 6. Utility Functions
- [X] **`strict_edit_message`:** Function to prevent redundant API calls for message editing.
