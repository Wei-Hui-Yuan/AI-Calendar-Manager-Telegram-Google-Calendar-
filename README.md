# 🤖 AI Calendar Manager (Telegram + Google Calendar)

A multi-user Telegram bot that manages Google Calendar using natural language. Powered by Llama 3 (via Ollama) and Python, this bot features automated urgency tagging and secure OAuth2 authentication for multiple users.

## 🌟 Key Features (Server Version)
The primary version of this bot is designed to be hosted on a server to support multiple users simultaneously:
* **Natural Language Processing:** Uses Llama 3 to interpret complex dates, times, and intents (Add, List, Delete) straight from casual conversation.
* **Multi-User Support:** Securely manages individual Google Calendar tokens (`token_{user_id}.json`) for every user who connects via Telegram.
* **Smart Urgency System:** Dynamically categorizes tasks on your schedule using 🚨 (Urgent, <4 days) and ⚠️ (Upcoming, <7 days) based on the current date.
* **Smart Timezones:** Pre-configured for seamless handling of the `Asia/Singapore` (SGT) timezone.

> **💡 Note on the Local Version:** If you are looking for a simpler setup for a single user and do not wish to handle server-side callback URLs, I have included `Python_code_local_version.py`. This version is optimized for personal, local execution.

---

## 🛠️ Prerequisites
Before running the bot, ensure you have the following installed and configured:
* **Python 3.10+**
* **Ollama:** Must be installed and running on the host machine. You must have the Llama 3 model downloaded (`ollama run llama3`).
* **Google Cloud Project:** You will need a `credentials.json` file with the **Google Calendar API** enabled.
* **Telegram Bot Token:** Obtained via BotFather on Telegram.

## 🚀 Setup Instructions

**1. Clone the repository:**
```bash
git clone https://github.com/yourusername/AI-Calendar-Manager-Telegram-Google-Calendar-.git
cd AI-Calendar-Manager-Telegram-Google-Calendar-

2. Install dependencies:
pip install -r requirements.txt

3. Configure Environment Variables:
Rename .env.example.txt to .env and add your API keys:
TELEGRAM_CODE=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
(Note: While the bot uses Ollama locally for privacy/cost, the code currently initializes the Google Gemini client as a backup/alternative, so a placeholder key is required in the .env file to prevent startup errors).

4. Google Credentials:
Place your credentials.json file directly into the root folder of the project.

5. Run the Bot:
python Python_code_sever_version.py

📖 How to Use
Start a chat with your bot on Telegram and send /connect.
Click the provided link to authorize your Google Calendar.
Log in with Google. When the final page fails to load (showing localhost refused to connect), copy the entire URL from your browser's address bar.
Paste that full URL back into the Telegram chat to complete the connection.
Start managing your calendar naturally!
"Meet Tommy tomorrow at 3pm"
"View Schedule"
"Urgency List"
