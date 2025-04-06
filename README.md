# Delayed-Echo

A Telegram bot that allows users to schedule messages to be sent back to them at specified times. Perfect for reminders, notes to yourself, or delayed messages.

## Features

- 📅 Schedule messages to be sent at any future time
- ⏰ Simple time format (e.g., "5m", "3h", "1d")
- 🔄 Combine units like "2h 30m" for precise timing
- 📋 List your scheduled messages with the /list command
- 🔒 Secure and private - messages are only sent back to you

## Technical Details

- Built with Python, Flask, and python-telegram-bot
- Uses PostgreSQL for persistent storage of scheduled messages
- Scheduler implemented with APScheduler
- RESTful status endpoints for monitoring

## Deployment

### Environment Variables

This project requires the following environment variables:

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from BotFather
- `DATABASE_URL`: PostgreSQL database connection string

**IMPORTANT**: Never commit these values to your repository. Use environment variables or a `.env` file that is included in `.gitignore`.

### Deploying to Render.com

1. Push your code to GitHub (without sensitive information)
2. Create a PostgreSQL database on Render
3. Create a Web Service linked to your GitHub repository
4. Add the environment variables in the Render dashboard
5. Deploy and enjoy your always-on bot!

For detailed deployment instructions, see the deployment guide in the repository.

## Local Development

1. Clone the repository
2. Create a `.env` file with the required environment variables
3. Install dependencies: `pip install -r render_requirements.txt`
4. Run the application: `python main.py`

## Security Notes

- The `.env` file and `env.sample` are included in `.gitignore`
- Environment variables are set in the deployment platform, not in the code
- Database credentials are never hardcoded
- All sensitive information is accessed via environment variables

## License

MIT
