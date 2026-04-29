import os
import dateparser
import ollama
import json
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import pytz
from urllib.parse import urlparse, parse_qs

# Telegram Libraries
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

#Google GenAI (Gemini)
from google import genai
from google.genai import types

# Google Calendar Auth & API
# Google Calendar Auth & API
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow 
from google.auth.transport.requests import Request      
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow

# 1. SETUP & CONFIGURATION
load_dotenv() 

# 1a. GET KEYS FROM .ENV
TG_CODE = os.getenv("TELEGRAM_CODE") 
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

# 1b. CONFIGURE GEMINI
client = genai.Client(api_key=GEMINI_KEY)

# 1c. GOOGLE CALENDAR CONFIG
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service(user_id):
    base_path = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(base_path, f'token_{user_id}.json')

    creds = None
    if os.path.exists(token_path):                                  
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if creds and creds.valid:
        return build('calendar', 'v3', credentials=creds)
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'w') as token:                        
            token.write(creds.to_json())
        return build('calendar', 'v3', credentials=creds)

    print('unauthorized function tried to access the calendar')        
    return None


# 2. THE ollama or Gemini "BRAIN" Currently using ollama as repeated use of Gemini will exceed free tier limits
async def interpret_message(text):
    now_str = datetime.now(pytz.timezone('Asia/Singapore')).strftime('%d %B %Y')
    prompt = f"""
    You are a calendar assistant. TODAY's DATE IS {now_str}. Use Singapore/UK date format (DD/MM/YYYY).
    
    ### RULES OF LOGIC:
    - DATE FORMAT: Always treat numeric dates as DD/MM/YYYY. (Example: "04/06/26" -> 4th June 2026). 
        1. Use TODAY'S DATE ({now_str}) to determine the correct year for upcoming events.
    - RAW_DATE: Extract the EXACT WORDS the user typed for the start date and time. DO NOT calculate, format, or change the words. If they say "next thursday at 2pm", output exactly "next thursday at 2pm". NEVER include end times or ranges.
    - END_TIME: If a range is given, put the end time here (e.g., "6:00pm").
    - RELATIVE DATES: "Next", "Coming", and "Following" all refer to the upcoming occurrence of that day.
    - DURATION: Return ONLY the raw integer. No words.
    
    ### EXAMPLES:
    - "Meeting 04/06/26 at 2pm" -> {{"intent": "add", "summary": "Meeting", "raw_date": "04/06/2026 2pm", "duration_minutes": 60}}
    - "Flight 3:55am to 8:15am" -> {{"intent": "add", "summary": "Flight", "raw_date": "3:55am", "duration_minutes": 260}}
    - "Gym 7:15pm-9:05pm" -> {{"intent": "add", "summary": "Gym", "raw_date": "7:15pm", "duration_minutes": 110}}
    - "Meeting with Boss at 2pm for 2hours" -> {{"intent": "add", "summary": "Meeting with Boss", "raw_date": "2pm", "duration_minutes": "120"}}
    - "Lunch at 1pm for 1hour" -> {{"intent": "add", "summary": "Lunch", "raw_date": "1pm", "duration_minutes": "60"}}

    Analyze this request: "{text}"
    Extract into JSON:
    1. intent: (Options: add, list, delete)
    2. summary: (Extract the specific name of the activity or event. Do NOT use generic names.)
    3. "raw_date": "(The exact, unchanged words the user used for the start time)",
    4. "end_time": "HH:MM or null",
    5. "duration_minutes": 60
    Return strictly JSON.
    """
    
    try:
        response = ollama.chat(
            model='llama3', 
            messages=[{'role': 'user', 'content': prompt}],
            format='json' 
        )
        
        content = response['message']['content']
        print(f"Ollama raw output: {content}") 
        
        return json.loads(content)
    except Exception as e:
        print(f"Ollama Error: {e}")
        return {"intent": "unknown", "summary": "error", "raw_date": "now and error"}
    
# 3. TELEGRAM HANDLERS

def get_main_dashboard():
    keyboard = [
        [
            InlineKeyboardButton("📅 View Schedule", callback_data='view_schedule'),
            InlineKeyboardButton("🚨 Urgency List", callback_data='view_urgent')
        ],
        [
            InlineKeyboardButton("➕ Add Events", callback_data='help_add'),
            InlineKeyboardButton("🗑️ Delete Event", callback_data='delete_event')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

    
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES,
            redirect_uri='http://localhost'
        )
        auth_url, _ = flow.authorization_url(
            prompt='consent',
            access_type='offline'
        )

        context.user_data['oauth_flow'] = flow
        context.user_data['awaiting_auth_code'] = True

        instructions = (
            "🔗 **Click this link to authorize the bot:**\n\n"
            f"[Authorize Google Calendar]({auth_url})\n\n"
            "⚠️ **IMPORTANT INSTRUCTIONS:**\n"
            "1. Log in with your Google account.\n"
            "2. The final page will fail to load (it will say 'localhost refused to connect'). **This is normal!**\n"
            "3. **Copy the entire URL** from your browser's address bar on that broken page.\n"
            "4. Paste that full URL right here in this chat."
        )
        await update.message.reply_text(instructions, parse_mode='Markdown', disable_web_page_preview=True)

    except Exception as e:
        await update.message.reply_text(f"❌ Connection error: {e}")


async def confirm_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ **Google Calendar connected successfully!**", parse_mode='Markdown')

    features_message = (
        "Here is what I can do for you:\n\n"
        "📅 **Adding Events:** Add any event you would like by typing \n"
        "🗑️ **Deleting Events:** Choose from a list of event to delete\n"
        "🚨 **View Urgent Tasks:** Instantly see tasks that are coming up in the next 7 days.\n"
        "📅 **See Full Schedule:** Get your complete upcoming schedule."
    )

    await update.message.reply_text(features_message, parse_mode='Markdown', reply_markup=get_main_dashboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **How to use your AI Calendar Manager**\n\n"
        "**Adding Events:**\n"
        "Just type naturally! For example:\n"
        "• `Dinner with Tom at 8pm next Thursday`\n"
        "• `Meeting with Bill Gates tomorrow at 10am`\n\n"
        "**Managing Events:**\n"
        "• Use /list to see your upcoming schedule.\n"
        "• Type  `delete [event name]` to remove the event.\n"
        "• Click the 'Urgency List' button for task that are coming up in the next 3 days."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    welcome_text = (
        "👋 **Hello! I'm your AI Calendar Manager.**\n\n"
        "To get started, I need access to your Google Calendar.\n\n"
        "Send /connect to link your Google account. You'll be given a short code to "
        "enter on Google's website — you can do this from any browser, including your phone.\n\n"
        "Send /help at any time to see what I can do."
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide details! Example: `/add Gym at 6pm`", parse_mode='Markdown')
        return

    user_text = " ".join(context.args)
    await handle_message(update, context, override_text=user_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text=None):
    if update.message:
        user_text = update.message.text
        reply_target = update.message
        user_id = update.effective_user.id
    elif update.callback_query:
        user_text = override_text
        reply_target = update.callback_query.message
        user_id = update.callback_query.from_user.id
    else:
        return
    

    is_auth_url = "code=" in user_text and "scope=" in user_text
    
    if context.user_data.get('awaiting_auth_code') or is_auth_url:
        try:
            parsed_url = urlparse(user_text)
            auth_code = parse_qs(parsed_url.query).get('code', [None])[0]

            if auth_code:
                flow = context.user_data.get('oauth_flow')

                if not flow:
                    await reply_target.reply_text("❌ Session expired. Please type /connect again.")
                    return

            flow.fetch_token(code=auth_code)
            creds = flow.credentials

            with open(f'token_{user_id}.json', 'w') as token_file:
                token_file.write(creds.to_json())

            context.user_data['awaiting_auth_code'] = False
            context.user_data['oauth_flow'] = None  
            await confirm_connection(update, context)
            return
        except:
            await reply_target.reply_text("Authentication failed, code is wrong")


    service = get_calendar_service(user_id)
    if not service:
        await reply_target.reply_text("⚠️ You are not connected to Google Calendar yet. Please type /connect first.")
        return

    text_lower = user_text.lower()

    if "list my events" in text_lower:
        data = {"intent": "list", "urgent": False}
    elif "show my urgent tasks" in text_lower:
        data = {"intent": "list", "urgent": True}
    
    else:
        data = await interpret_message(user_text)
    

    event_name = data.get('summary')
    if not event_name or event_name == "null":
        event_name = "New Calendar Event"

    if data.get('intent') == 'error':
        await reply_target.reply_text("Time out Error! Please wait 30 seconds and try again.")

    elif data['intent'] == 'list':
        is_urgent_view = data.get('urgent', False)
        now = datetime.now(timezone.utc).isoformat()
        
        events_result = service.events().list(
            calendarId='primary', timeMin=now, maxResults=10, 
            singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            await reply_target.reply_text("Your calendar is completely clear!")
            return
        sgt = pytz.timezone('Asia/Singapore')
        filtered_events = []
        for e in events:
            start_str = e['start'].get('dateTime', e['start'].get('date'))
            parsed_start = dateparser.parse(start_str)
            if parsed_start.tzinfo is None:
                parsed_start = sgt.localize(parsed_start)

            days_until = (parsed_start.date() - datetime.now(sgt).date()).days

            if is_urgent_view and days_until <= 7:
                filtered_events.append((e, parsed_start))
            elif not is_urgent_view: 
                filtered_events.append((e, parsed_start))
        
        if not filtered_events:
            await reply_target.reply_text("You have no urgent tasks in the next 7 days. Good job! Remember to rest! 🥳")
            return

        header = "🚨 **Urgent Upcoming Tasks:**\n" if data.get('urgent') else "📅 **Your Schedule:**\n"
        msg = header
        for e, dt in filtered_events:
            diff_days = (dt.date() - datetime.now(sgt).date()).days

            if diff_days <= 3:
                prefix = "🚨 "
            elif 3 < diff_days <=7:
                prefix = "⚠️ "
            else:
                prefix = ""
            display_start = dt.strftime('%b %d %Y at %I:%M %p')
            msg += f"• {prefix}{e['summary']} ({display_start})\n"
            
        await reply_target.reply_text(msg, parse_mode='Markdown')
        await reply_target.reply_text("What would you like to do next?", reply_markup=get_main_dashboard())
    
    elif data['intent'] == 'add':
        raw_date_string = data['raw_date'].lower()
        if "following" in raw_date_string:
            raw_date_string = raw_date_string.replace("following", "next")
        
        elif 'coming' in raw_date_string:
            raw_date_string = raw_date_string.replace('coming', 'next')

        elif 'this' in raw_date_string:
            raw_date_string = raw_date_string.replace("this ", "")        
        data['raw_date'] = raw_date_string

        duration_str = str(data.get('duration_minutes', '60'))
        duration_digits = ''.join(filter(str.isdigit, duration_str))
        duration = int(duration_digits) if duration_digits else 60
        if duration <= 0:
            duration = 60

        sgt = pytz.timezone('Asia/Singapore')
        base_time = datetime.now(sgt).replace(tzinfo=None)
        
        parsed_date = dateparser.parse(
            data['raw_date'], 
            settings={
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': base_time, 
                'TIMEZONE': 'Asia/Singapore',
                'DATE_ORDER': 'DMY'
            }
        )
        
        if not parsed_date:
            print(f"Failed to parse: {raw_date_string}")
            await reply_target.reply_text("I couldn't understand that date. Try 'Go to Gym at Friday 2pm'.")
            return
        
        if parsed_date.tzinfo is None:
            parsed_date = sgt.localize(parsed_date)
        else:
            parsed_date = parsed_date.astimezone(sgt)

        end_time_str = data.get('end_time')
        end_time = None

        if end_time_str and end_time_str != "null":

            combined_end_str = f"{parsed_date.strftime('%d %B %Y')} {end_time_str}"
            end_time = dateparser.parse(combined_end_str, settings={'DATE_ORDER': 'DMY'})
            if end_time:
                if end_time.tzinfo is None:
                    end_time = sgt.localize(end_time)
                else:
                    end_time = end_time.astimezone(sgt)

                if end_time <= parsed_date:
                    end_time += timedelta(days=1)
        
        if not end_time:
            end_time = parsed_date + timedelta(minutes=duration)
        
        duration_minutes = (end_time - parsed_date).total_seconds() / 60

        event = {
            'summary': event_name,
            'start': {'dateTime': parsed_date.isoformat(), 'timeZone': 'Asia/Singapore'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Singapore'},
            }
        
        inserted_event = service.events().insert(calendarId='primary', body=event).execute()
        feedback_header = f"Your event **{event_name}** has been successfully added:\n\n"
        duration_minutes = (end_time - parsed_date).total_seconds() / 60
        details_body = (
            f"📅 **{parsed_date.strftime('%A, %B %d, %Y')}**\n" 
            f"⌚ Time: {parsed_date.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
            f" ({duration_minutes:.0f} min)\n\n" 
            "Here is the event you added:\n"
            f"**{event_name}**"
        )

        full_feedback = (
        f"{feedback_header}{details_body}\n\n"
        "Feel free to check it out in your calendar [here]"
        f"({inserted_event['htmlLink']}).\n\n" 
        "If you need anything else, just let me know!"
        )
        

        await reply_target.reply_text(full_feedback, parse_mode='Markdown', disable_web_page_preview=True)
        await reply_target.reply_text("What would you like to do next?", reply_markup=get_main_dashboard())

    elif data['intent'] == 'delete':
        service = get_calendar_service(user_id)
        now = datetime.now(timezone.utc).isoformat()
        events_result = service.events().list(calendarId='primary', q=data['summary'], 
                                             timeMin=now, maxResults=10).execute()
        events = events_result.get('items', [])

        if not events:
            await reply_target.reply_text(f"I couldn't find any events matching '{data['summary']}'.")
            return

        context.user_data['event_cache'] = {}
        keyboard = []
        for i, event in enumerate(events):
            event_id = event['id']
            summary = event.get('summary', '(No Title)')
            context.user_data['event_cache'][str(i)] = event_id
            keyboard.append([InlineKeyboardButton(f"❌ {summary}", callback_data=f"del_{i}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await reply_target.reply_text("Which event would you like to delete?", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    service = get_calendar_service(user_id)
    if not service:
        await query.message.reply_text("⚠️ You are not connected. Please type /connect.")
        return

    try:
        if query.data == 'view_schedule':
            await handle_message(update, context, override_text="list my events")
        

        elif query.data.startswith('del_'):
            short_id = query.data.split('_')[1]
            user_cache = context.user_data.get('event_cache', {})
            real_event_id = user_cache.get(short_id)

            if real_event_id:
                service.events().delete(calendarId='primary', eventId=real_event_id).execute()
                await query.edit_message_text(text="✅ Event successfully deleted from your calendar!")
                await query.message.reply_text("What would you like to do next?", reply_markup=get_main_dashboard())
            else:
                await query.edit_message_text(text="❌ Error: Event ID expired. Please click Delete again.")
                await query.message.reply_text("What would you like to do next?", reply_markup=get_main_dashboard())
        
        elif query.data == 'delete_event':
            sgt = pytz.timezone('Asia/Singapore')
            now_date = datetime.now(sgt).date() 
            now_utc = datetime.now(timezone.utc)
            events_result = service.events().list(calendarId='primary', timeMin=now_utc.isoformat(), 
                                                 maxResults=7, singleEvents=True, 
                                                 orderBy='startTime').execute()
            events = events_result.get('items', [])
            
            if not events:
                await query.message.reply_text("You have no upcoming events to delete!")
                return

            keyboard = []
            context.user_data['event_cache'] = {}

            for i, e in enumerate(events):
                start_raw = e['start'].get('dateTime',e['start'].get('date'))
                event_dt = dateparser.parse(start_raw)

                if event_dt.tzinfo is None:
                    event_dt = sgt.localize(event_dt)
                else:
                    event_dt = event_dt.astimezone(sgt)

                event_date = event_dt.date()
                
                diff_days = (event_date - now_date).days

                if diff_days == 0:
                    relative = 'Today'
                elif diff_days == 1:
                    relative = 'Tomorrow'
                elif diff_days < 0:
                    relative = 'Past'
                else:
                    relative = f'In {diff_days} days'
                    
                date_brief = event_date.strftime('%d %b %Y')
                btn_text = f"🗑️ [{date_brief}] {e['summary']} ({relative})"
                short_id = str(i)
                
                context.user_data['event_cache'][short_id] = e['id']
                
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"del_{short_id}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Select an event to remove:", reply_markup=reply_markup)


        elif query.data == 'view_urgent':
            await handle_message(update, context, override_text="show my urgent tasks")

        elif query.data == 'help_add':
            help_text = "Just type something like:\n`Dinner with Tommy tomorrow at 8pm`"

            if query.message.text != help_text:
                await query.edit_message_text(text=help_text, parse_mode='Markdown')
    except Exception as e:
        print(f"Error in button handler: {e}")

# 4. START THE BOT
if __name__ == '__main__':
    if not TG_CODE:
        print("Error: TELEGRAM_CODE not found in .env file")
    else:
        app = ApplicationBuilder().token(TG_CODE).build()

        # 1. Register Commands
        app.add_handler(CommandHandler("start", start))     
        app.add_handler(CommandHandler("connect", connect)) 
        app.add_handler(CommandHandler("help", help_command)) 
        app.add_handler(CommandHandler("list", lambda u, c: handle_message(u, c, override_text="list my events")))

        # 2. Register Button (Callback) Handler
        app.add_handler(CallbackQueryHandler(button_handler))

        # 3. Register General Message Handler
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        print("Bot is running...")
        app.run_polling()
        
