import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class ScheduledMessage(db.Model):
    """Model for storing scheduled messages."""
    __tablename__ = 'scheduled_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    delivery_time = db.Column(db.DateTime, nullable=False, index=True)
    job_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_sent = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ScheduledMessage(id={self.id}, user_id={self.user_id}, delivery_time={self.delivery_time})>"
    
    def to_dict(self):
        """Convert the model to a dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'text': self.text,
            'scheduled_time': self.scheduled_time,
            'delivery_time': self.delivery_time,
            'job_id': self.job_id,
            'created_at': self.created_at,
            'is_sent': self.is_sent,
            'sent_at': self.sent_at
        }