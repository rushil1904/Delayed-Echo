import os
import logging
import re
from datetime import datetime, timedelta
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, ConversationHandler
)
from telegram import Update, ParseMode
from scheduler import MessageScheduler

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot states
WAITING_FOR_MESSAGE, WAITING_FOR_TIME = range(2)

# Initialize scheduler
scheduler = MessageScheduler()

def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    welcome_text = (
        f"👋 Hello {user.first_name}!\n\n"
        "I'm your Message Scheduler Bot. I can schedule messages to be sent back to you after a specified delay.\n\n"
        "*How to use me:*\n"
        "1️⃣ Forward me any message or send a new one\n"
        "2️⃣ Tell me when to send it back to you\n\n"
        "For detailed instructions, use /help"
    )
    update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a help message when the command /help is issued."""
    help_text = (
        "*📋 Bot Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/schedule - Start scheduling a new message\n"
        "/cancel - Cancel the current operation\n"
        "/list - Show your scheduled messages\n\n"
        
        "*⏱️ Time Format Examples:*\n"
        "- `5m` or `5 minutes` - 5 minutes from now\n"
        "- `2h` or `2 hours` - 2 hours from now\n"
        "- `1d` or `1 day` - 1 day from now\n"
        "- `30s` or `30 seconds` - 30 seconds from now\n"
        "- `tomorrow 9am` - at 9:00 AM tomorrow\n"
        "- `3h 30m` - 3 hours and 30 minutes from now\n\n"
        
        "You can also directly forward a message and include the time in the same message, like:\n"
        "Forward a message and add: `!schedule 2h`"
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def schedule_command(update: Update, context: CallbackContext) -> int:
    """Start the scheduling process."""
    update.message.reply_text(
        "Please send or forward the message you want me to schedule."
    )
    return WAITING_FOR_MESSAGE

def list_scheduled(update: Update, context: CallbackContext) -> None:
    """List all scheduled messages for the user."""
    user_id = update.effective_user.id
    messages = scheduler.get_user_scheduled_messages(user_id)
    
    if not messages:
        update.message.reply_text("You don't have any scheduled messages.")
        return
    
    response = "*Your scheduled messages:*\n\n"
    for idx, msg in enumerate(messages, 1):
        delivery_time = msg['delivery_time'].strftime("%Y-%m-%d %H:%M:%S")
        message_preview = msg['text'][:50] + "..." if len(msg['text']) > 50 else msg['text']
        response += f"{idx}. {message_preview}\n   📅 Scheduled for: {delivery_time}\n\n"
    
    update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current conversation."""
    update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def receive_message(update: Update, context: CallbackContext) -> int:
    """Store the message and ask for the time delay."""
    user_id = update.effective_user.id
    
    # Check if the message contains a scheduling command
    message_text = update.message.text or update.message.caption or ""
    schedule_match = re.search(r'!schedule\s+(.+)$', message_text, re.IGNORECASE)
    
    if schedule_match:
        # Extract the time specification and process immediately
        time_spec = schedule_match.group(1).strip()
        # Remove the scheduling command from the message
        clean_message = re.sub(r'!schedule\s+.+$', '', message_text, flags=re.IGNORECASE).strip()
        
        # Store the message without the scheduling command
        if update.message.text:
            context.user_data['message'] = clean_message
        elif update.message.caption:
            context.user_data['message'] = clean_message
        else:
            context.user_data['message'] = "Forwarded message"
        
        # Process the time specification and schedule the message
        return process_time(update, context, time_spec)
    
    # Store the message for later scheduling
    if update.message.text:
        context.user_data['message'] = update.message.text
    elif update.message.caption:
        context.user_data['message'] = update.message.caption
    else:
        context.user_data['message'] = "Forwarded message"
    
    # If it's a forwarded message, add more details
    if update.message.forward_from:
        forward_from = update.message.forward_from
        context.user_data['message'] = f"Forwarded from {forward_from.first_name} (@{forward_from.username if forward_from.username else 'unknown'}):\n\n{context.user_data['message']}"
    
    update.message.reply_text(
        "When should I send this message back to you? Examples:\n"
        "- `5m` or `5 minutes` - 5 minutes from now\n"
        "- `2h` or `2 hours` - 2 hours from now\n"
        "- `1d` or `1 day` - 1 day from now\n"
        "- `3h 30m` - 3 hours and 30 minutes from now"
    )
    return WAITING_FOR_TIME

def receive_time(update: Update, context: CallbackContext) -> int:
    """Process the time delay and schedule the message."""
    time_spec = update.message.text
    return process_time(update, context, time_spec)

def process_time(update: Update, context: CallbackContext, time_spec: str) -> int:
    """Process the time specification and schedule the message."""
    try:
        # Parse the time specification
        delivery_time = parse_time_specification(time_spec)
        
        if not delivery_time:
            update.message.reply_text(
                "I couldn't understand that time format. Please try again with a format like:\n"
                "- `5m` or `5 minutes`\n"
                "- `2h` or `2 hours`\n"
                "- `1d` or `1 day`\n"
                "- `3h 30m`"
            )
            return WAITING_FOR_TIME
        
        # Get the message from user data
        message = context.user_data.get('message', "Empty message")
        
        # Schedule the message
        user_id = update.effective_user.id
        scheduler.schedule_message(user_id, message, delivery_time)
        
        # Format the delivery time for display
        formatted_time = delivery_time.strftime("%Y-%m-%d %H:%M:%S")
        time_diff = delivery_time - datetime.now()
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        readable_diff = f"{time_diff.days} days, " if time_diff.days else ""
        readable_diff += f"{hours}h {minutes}m {seconds}s"
        
        update.message.reply_text(
            f"✅ Message scheduled successfully!\n\n"
            f"📅 Delivery time: {formatted_time}\n"
            f"⏱️ That's in: {readable_diff}\n\n"
            f"I'll send your message at the scheduled time."
        )
        
        # Clean up user data
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error scheduling message: {e}")
        update.message.reply_text(
            "Sorry, there was an error processing your request. Please try again."
        )
        return ConversationHandler.END

def parse_time_specification(time_spec: str) -> datetime | None:
    """Parse the time specification into a datetime object."""
    now = datetime.now()
    
    # Simple regex patterns for common time formats
    minutes_pattern = re.compile(r'(\d+)\s*(?:m|min|minute|minutes)', re.IGNORECASE)
    hours_pattern = re.compile(r'(\d+)\s*(?:h|hr|hour|hours)', re.IGNORECASE)
    days_pattern = re.compile(r'(\d+)\s*(?:d|day|days)', re.IGNORECASE)
    seconds_pattern = re.compile(r'(\d+)\s*(?:s|sec|second|seconds)', re.IGNORECASE)
    
    # Check for combined formats like "1h 30m"
    total_seconds = 0
    
    # Extract minutes
    minutes_match = minutes_pattern.search(time_spec)
    if minutes_match:
        minutes = int(minutes_match.group(1))
        total_seconds += minutes * 60
    
    # Extract hours
    hours_match = hours_pattern.search(time_spec)
    if hours_match:
        hours = int(hours_match.group(1))
        total_seconds += hours * 3600
    
    # Extract days
    days_match = days_pattern.search(time_spec)
    if days_match:
        days = int(days_match.group(1))
        total_seconds += days * 86400
    
    # Extract seconds
    seconds_match = seconds_pattern.search(time_spec)
    if seconds_match:
        seconds = int(seconds_match.group(1))
        total_seconds += seconds
    
    # If we found any time components, calculate the future time
    if total_seconds > 0:
        return now + timedelta(seconds=total_seconds)
    
    # Short formats like "5m" or "2h"
    short_format = re.match(r'^\s*(\d+)([mhds])\s*$', time_spec, re.IGNORECASE)
    if short_format:
        value = int(short_format.group(1))
        unit = short_format.group(2).lower()
        
        if unit == 'm':
            return now + timedelta(minutes=value)
        elif unit == 'h':
            return now + timedelta(hours=value)
        elif unit == 'd':
            return now + timedelta(days=value)
        elif unit == 's':
            return now + timedelta(seconds=value)
    
    # If no recognized format, return None
    return None

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            update.effective_message.reply_text(
                "Sorry, something went wrong. Please try again or contact the bot administrator."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

def setup_bot():
    """Set up the bot with the necessary handlers."""
    # Get the token from environment variable
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables!")
        return
    
    # Create the updater and pass it the bot's token
    updater = Updater(token)
    
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    # Add command handlers first (they take precedence)
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(CommandHandler('list', list_scheduled))
    
    # Add conversation handler for scheduling messages
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('schedule', schedule_command),
            MessageHandler(Filters.text | Filters.forwarded, receive_message)
        ],
        states={
            WAITING_FOR_MESSAGE: [
                MessageHandler(Filters.text | Filters.forwarded, receive_message)
            ],
            WAITING_FOR_TIME: [
                MessageHandler(Filters.text & ~Filters.command, receive_time)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    dispatcher.add_handler(conv_handler)
    
    # Add error handler
    dispatcher.add_error_handler(error_handler)
    
    # Start the Bot
    updater.start_polling()
    logger.info("Bot started!")
    
    # Don't call idle() when running in a thread
    # Just return the updater so it keeps running
    return updater
