import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from telegram import Bot, ParseMode
import os
import time
import flask

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global instance of scheduler to prevent garbage collection
_scheduler_instance = None

class MessageScheduler:
    """Class to handle scheduling and storing messages."""
    
    def __init__(self):
        """Initialize the scheduler and message store."""
        global _scheduler_instance
        
        # Configure the scheduler with thread pool executor and job store
        job_stores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(20)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 3,
            'misfire_grace_time': 60  # Allow 60 seconds of misfire grace time
        }
        
        # Create the scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=job_stores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Store the instance in the global variable to prevent garbage collection
        _scheduler_instance = self
        
        # Start the scheduler if it's not already running
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Message scheduler started")
        
        # We'll still keep an in-memory cache for quick access
        self.messages = {}  
        self.bot = None
        
        # Initialize the bot
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if token:
            self.bot = Bot(token)
            logger.info("Bot initialized for scheduler")
        else:
            logger.error("No TELEGRAM_BOT_TOKEN found in environment variables!")
            
        # Load any existing scheduled messages from the database
        self._load_messages_from_db()
        
        # Schedule regular database cleanup
        self._schedule_database_cleanup()
        
    def _load_messages_from_db(self):
        """Load existing scheduled messages from the database and schedule them."""
        try:
            # Import locally to avoid circular imports
            from database import app
            from models import ScheduledMessage
            
            with app.app_context():
                # Get all pending messages
                pending_messages = ScheduledMessage.query.filter_by(is_sent=False).all()
                logger.info(f"Loading {len(pending_messages)} pending messages from database")
                
                for msg in pending_messages:
                    # Check if message is still in the future
                    if msg.delivery_time > datetime.now():
                        # Add to scheduler
                        self.scheduler.add_job(
                            self.send_scheduled_message,
                            'date',
                            run_date=msg.delivery_time,
                            args=[msg.user_id, msg.text, msg.job_id],
                            id=msg.job_id,
                            replace_existing=True
                        )
                        
                        # Add to in-memory cache
                        if msg.user_id not in self.messages:
                            self.messages[msg.user_id] = []
                        
                        self.messages[msg.user_id].append(msg.to_dict())
                        
                        logger.info(f"Re-scheduled message {msg.job_id} for user {msg.user_id} at {msg.delivery_time}")
                    else:
                        # Message delivery time has passed
                        logger.warning(f"Message {msg.job_id} delivery time has passed: {msg.delivery_time}")
                        
                # Log the scheduled jobs
                self._log_scheduled_jobs()
                
        except Exception as e:
            logger.error(f"Error loading messages from database: {e}", exc_info=True)
    
    def schedule_message(self, user_id: int, text: str, delivery_time: datetime) -> bool:
        """
        Schedule a message to be sent at the specified time.
        
        Args:
            user_id: The Telegram user ID of the recipient
            text: The message text
            delivery_time: When to send the message
        
        Returns:
            True if scheduled successfully, False otherwise
        """
        if not self.bot:
            logger.error("Bot not initialized, cannot schedule message")
            return False
        
        try:
            # Create a unique job ID
            job_id = f"msg_{user_id}_{delivery_time.timestamp()}"
            scheduled_time = datetime.now()
            
            # Store message details
            message_data = {
                'user_id': user_id,
                'text': text,
                'scheduled_time': scheduled_time,
                'delivery_time': delivery_time,
                'job_id': job_id
            }
            
            # Store in our in-memory dictionary
            if user_id not in self.messages:
                self.messages[user_id] = []
            self.messages[user_id].append(message_data)
            
            # Log the scheduled message details
            logger.debug(f"Attempting to schedule message with job_id={job_id}, user_id={user_id}, delivery_time={delivery_time}")
            
            # Schedule the job
            job = self.scheduler.add_job(
                self.send_scheduled_message,
                'date',
                run_date=delivery_time,
                args=[user_id, text, job_id],
                id=job_id,
                replace_existing=True
            )
            
            logger.info(f"Scheduled message for user {user_id} at {delivery_time}, job_id={job_id}, next_run_time={job.next_run_time}")
            
            # Store in the database
            try:
                # Import locally to avoid circular imports
                from database import app
                from models import db, ScheduledMessage
                
                with app.app_context():
                    # Check if message with this job_id already exists
                    existing = ScheduledMessage.query.filter_by(job_id=job_id).first()
                    if not existing:
                        # Create a new record
                        message = ScheduledMessage(
                            user_id=user_id,
                            text=text,
                            scheduled_time=scheduled_time,
                            delivery_time=delivery_time,
                            job_id=job_id,
                            is_sent=False
                        )
                        db.session.add(message)
                        db.session.commit()
                        logger.info(f"Stored message {job_id} in database with ID {message.id}")
                    else:
                        logger.warning(f"Message with job_id {job_id} already exists in database")
            except Exception as db_error:
                logger.error(f"Error storing message in database: {db_error}", exc_info=True)
                # Continue even if DB storage fails - the in-memory scheduling still works
            
            # Log all scheduled jobs
            self._log_scheduled_jobs()
            
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling message: {e}", exc_info=True)
            return False
    
    def _log_scheduled_jobs(self):
        """Log all scheduled jobs for debugging purposes."""
        jobs = self.scheduler.get_jobs()
        logger.info(f"Current scheduled jobs ({len(jobs)}):")
        for job in jobs:
            logger.info(f"  Job ID: {job.id}, Next run: {job.next_run_time}")
    
    def send_scheduled_message(self, user_id: int, text: str, job_id: str) -> None:
        """
        Send a scheduled message to the user.
        
        Args:
            user_id: The Telegram user ID of the recipient
            text: The message text to send
            job_id: The ID of the scheduled job
        """
        try:
            logger.info(f"Attempting to send scheduled message to user {user_id}, job_id={job_id}")
            
            if not self.bot:
                logger.error("Bot not initialized, cannot send message")
                return
            
            # Ensure we have the latest bot instance
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            if token:
                self.bot = Bot(token)
            
            # Send the message
            result = self.bot.send_message(
                chat_id=user_id,
                text=f"🔔 *Scheduled Message Reminder*\n\n{text}",
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Successfully sent scheduled message to user {user_id}, message_id={result.message_id}")
            
            # Update the database to mark the message as sent
            try:
                # Import locally to avoid circular imports
                from database import app
                from models import db, ScheduledMessage
                
                with app.app_context():
                    # Find the message in the database
                    message = ScheduledMessage.query.filter_by(job_id=job_id).first()
                    if message:
                        message.is_sent = True
                        message.sent_at = datetime.now()
                        db.session.commit()
                        logger.info(f"Updated message {job_id} in database as sent")
                    else:
                        logger.warning(f"Message with job_id {job_id} not found in database")
            except Exception as db_error:
                logger.error(f"Error updating message in database: {db_error}", exc_info=True)
            
            # Remove the message from our store
            self.remove_scheduled_message(user_id, job_id)
            
        except Exception as e:
            logger.error(f"Error sending scheduled message: {e}", exc_info=True)
    
    def remove_scheduled_message(self, user_id: int, job_id: str) -> bool:
        """
        Remove a scheduled message from the store.
        
        Args:
            user_id: The Telegram user ID of the recipient
            job_id: The ID of the scheduled job
        
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            # Remove from scheduler if it exists
            try:
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed job {job_id} from scheduler")
            except Exception as e:
                logger.debug(f"Job {job_id} already removed from scheduler: {e}")
            
            # Remove from our store
            if user_id in self.messages:
                original_count = len(self.messages[user_id])
                self.messages[user_id] = [
                    msg for msg in self.messages[user_id] 
                    if msg['job_id'] != job_id
                ]
                new_count = len(self.messages[user_id])
                
                if original_count != new_count:
                    logger.info(f"Removed message {job_id} from store for user {user_id}")
                    return True
                else:
                    logger.debug(f"No message found with job_id {job_id} for user {user_id}")
            return False
        except Exception as e:
            logger.error(f"Error removing scheduled message: {e}", exc_info=True)
            return False
    
    def _schedule_database_cleanup(self):
        """Schedule a periodic task to clean up old messages from the database."""
        try:
            # Schedule the cleanup job to run every day at midnight
            self.scheduler.add_job(
                self._cleanup_old_messages,
                'interval',
                days=1,
                id='db_cleanup_job',
                replace_existing=True,
                next_run_time=datetime.now()  # Run once immediately, then on schedule
            )
            logger.info("Scheduled database cleanup job to run daily")
        except Exception as e:
            logger.error(f"Error scheduling database cleanup: {e}", exc_info=True)
    
    def _cleanup_old_messages(self):
        """Remove messages older than one week from the database."""
        try:
            # Import locally to avoid circular imports
            from database import app
            from models import db, ScheduledMessage
            
            with app.app_context():
                # Calculate the cutoff date (one week ago)
                one_week_ago = datetime.now() - timedelta(days=7)
                
                # Find all messages that were sent more than a week ago
                old_messages = ScheduledMessage.query.filter(
                    ScheduledMessage.is_sent == True,
                    ScheduledMessage.sent_at <= one_week_ago
                ).all()
                
                if old_messages:
                    # Delete the old messages
                    count = len(old_messages)
                    for message in old_messages:
                        db.session.delete(message)
                    
                    db.session.commit()
                    logger.info(f"Deleted {count} old messages from the database")
                else:
                    logger.info("No old messages to clean up")
                
                # Also clean up failed messages with passed delivery time
                failed_messages = ScheduledMessage.query.filter(
                    ScheduledMessage.is_sent == False,
                    ScheduledMessage.delivery_time <= one_week_ago
                ).all()
                
                if failed_messages:
                    # Delete the failed messages
                    count = len(failed_messages)
                    for message in failed_messages:
                        db.session.delete(message)
                    
                    db.session.commit()
                    logger.info(f"Deleted {count} failed/expired messages from the database")
        except Exception as e:
            logger.error(f"Error cleaning up old messages: {e}", exc_info=True)
    
    def get_user_scheduled_messages(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all scheduled messages for a user.
        
        Args:
            user_id: The Telegram user ID
        
        Returns:
            A list of message data dictionaries
        """
        try:
            # Try to get messages from the database first
            from database import app
            from models import ScheduledMessage
            
            with app.app_context():
                # Get pending messages from database
                db_messages = ScheduledMessage.query.filter_by(
                    user_id=user_id,
                    is_sent=False
                ).order_by(ScheduledMessage.delivery_time.asc()).all()
                
                if db_messages:
                    # Convert to dictionary format
                    messages = [msg.to_dict() for msg in db_messages]
                    logger.info(f"Retrieved {len(messages)} scheduled messages for user {user_id} from database")
                    return messages
                else:
                    # Fall back to in-memory cache if no DB messages found
                    logger.debug(f"No scheduled messages found in database for user {user_id}, using in-memory cache")
        except Exception as e:
            logger.error(f"Error retrieving messages from database: {e}", exc_info=True)
            logger.debug("Falling back to in-memory message store")
        
        # Fall back to in-memory cache
        messages = self.messages.get(user_id, [])
        logger.debug(f"Retrieved {len(messages)} scheduled messages for user {user_id} from in-memory cache")
        
        return messages
