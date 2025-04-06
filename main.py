import os
import logging
from flask import render_template, jsonify
import threading
from bot import setup_bot
from database import app, db
from models import ScheduledMessage

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variable to store the updater
bot_updater = None

# Define a function to run the bot
def run_bot():
    global bot_updater
    bot_updater = setup_bot()
    # No need to call idle, just keep the thread alive

# Start the Telegram bot in a separate thread when this module is imported
logger.info("Setting up Telegram bot...")
bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

@app.route('/')
def home():
    """Render the home page of the web application."""
    return render_template('index.html')

@app.route('/status')
def status():
    """Simple status endpoint for uptime monitoring."""
    return "OK", 200

@app.route('/bot-status')
def bot_status():
    """Check if the bot is running."""
    global bot_updater
    if bot_updater:
        try:
            # Get scheduled message count for additional status info
            with app.app_context():
                pending_count = ScheduledMessage.query.filter_by(is_sent=False).count()
                sent_count = ScheduledMessage.query.filter_by(is_sent=True).count()
            
            return jsonify({
                "status": "running", 
                "bot_name": "Telegram Message Scheduler Bot",
                "pending_messages": pending_count,
                "sent_messages": sent_count
            })
        except Exception as e:
            logger.error(f"Error retrieving message counts: {e}")
            return jsonify({"status": "running", "bot_name": "Telegram Message Scheduler Bot"})
    else:
        return jsonify({"status": "not running", "error": "Bot updater not initialized"})

@app.route('/messages/<int:user_id>')
def get_user_messages(user_id):
    """Get a user's scheduled messages."""
    try:
        messages = ScheduledMessage.query.filter_by(user_id=user_id).order_by(ScheduledMessage.delivery_time.desc()).all()
        return jsonify([msg.to_dict() for msg in messages])
    except Exception as e:
        logger.error(f"Error retrieving messages for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

def run_flask():
    """Run the Flask application."""
    app.run(host='0.0.0.0', port=5000)

def main():
    """Main function to start both the Flask server and the Telegram bot."""
    # Run Flask in the main thread
    logger.info("Starting Flask web server...")
    run_flask()

if __name__ == "__main__":
    main()
