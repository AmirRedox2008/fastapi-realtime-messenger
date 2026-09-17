from sqlalchemy import String, Column, Integer, Boolean, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=True)
    number = Column(String)
    email = Column(String, index=True)
    User_Contacts = Column(String)
    hashed_password = Column(String)
    blocked_id = Column(Integer)
    blocker_id = Column(Integer)
    profile = relationship("Profile", uselist=False, back_populates="user", cascade="all, delete-orphan")

class Room(Base):
    __tablename__ = 'rooms'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=True)
    is_channel = Column(Boolean, default=False)
    creator_id = Column(Integer, ForeignKey('users.id'))
    bio = Column(String, nullable=True)
    members = relationship("RoomMember", back_populates="room", cascade="all, delete-orphan")

class RoomMember(Base):
    __tablename__ = 'room_members'
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey('rooms.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    is_admin = Column(Boolean, default=False)
    is_muted = Column(Boolean, default=False)
    room = relationship("Room", back_populates="members")

class Profile(Base):
    __tablename__ = 'profiles'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    status = Column(String, default="Hey there!")
    user = relationship("User", back_populates="profile")

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer)
    receiver_id = Column(Integer, nullable=True)
    room_id = Column(Integer, ForeignKey('rooms.id'), nullable=True)
    content = Column(String)
    is_delivered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    views = Column(Integer, default=0)
    reactions = Column(Text, nullable=True)

class Block(Base):
    __tablename__ = 'blocks'
    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    blocked_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    __table_args__ = (UniqueConstraint('blocker_id', 'blocked_id', name='uq_block'),)

class RoomReadState(Base):
    __tablename__ = 'room_read_states'
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey('rooms.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    last_read_id = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint('room_id', 'user_id', name='uq_room_read'),)

class MessageView(Base):
    __tablename__ = 'message_views'
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    __table_args__ = (UniqueConstraint('message_id', 'user_id', name='uq_message_view'),)