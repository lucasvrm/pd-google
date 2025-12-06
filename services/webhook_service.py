"""
Service for managing Google Drive webhook notification channels.
Handles channel registration, renewal, and deactivation.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Union
from sqlalchemy.orm import Session
import models
from services.google_drive_real import GoogleDriveRealService
from services.google_drive_mock import GoogleDriveService
from config import config


class WebhookService:
    """
    Manages Google Drive webhook channels for real-time notifications.
    """
    
    def __init__(self, db: Session, drive_service: Optional[Union[GoogleDriveRealService, GoogleDriveService]] = None):
        self.db = db
        if drive_service:
            self.drive_service = drive_service
        elif config.USE_MOCK_DRIVE:
            self.drive_service = GoogleDriveService()
        else:
            self.drive_service = GoogleDriveRealService()
    
    def register_webhook_channel(
        self, 
        folder_id: str, 
        resource_type: str = "folder",
        ttl_hours: int = 24
    ) -> models.DriveWebhookChannel:
        """
        Register a new webhook channel with Google Drive for a specific folder.
        
        Args:
            folder_id: The Google Drive folder ID to watch
            resource_type: Type of resource ("folder" or "file")
            ttl_hours: Time to live for the channel in hours (max 24 hours for most resources)
        
        Returns:
            DriveWebhookChannel model instance
        """
        # Check if an active channel already exists for this folder
        existing_channel = self.db.query(models.DriveWebhookChannel).filter(
            models.DriveWebhookChannel.watched_resource_id == folder_id,
            models.DriveWebhookChannel.active == True
        ).first()
        
        if existing_channel:
            # Check if it's still valid
            # Make both datetimes timezone-aware for comparison
            expires_at = existing_channel.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if expires_at > datetime.now(timezone.utc):
                print(f"Active channel already exists for folder {folder_id}")
                return existing_channel
            else:
                # Expired, deactivate it
                existing_channel.active = False
                self.db.commit()
        
        # Generate unique channel ID
        channel_id = str(uuid.uuid4())
        
        # Build webhook URL
        webhook_url = f"{config.WEBHOOK_BASE_URL}/webhooks/google-drive"
        
        # In mock mode, we simulate the channel creation
        if config.USE_MOCK_DRIVE:
            print(f"MOCK: Would register webhook for folder {folder_id}")
            resource_id = f"mock-resource-{uuid.uuid4()}"
            expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        else:
            # Real Google Drive API call to watch a folder
            # Google Drive uses the Files.watch API
            try:
                body = {
                    'id': channel_id,
                    'type': 'web_hook',
                    'address': webhook_url,
                }
                
                # Add optional token for verification
                if config.WEBHOOK_SECRET:
                    body['token'] = config.WEBHOOK_SECRET
                
                # Set expiration (Google Drive accepts expiration in milliseconds)
                expiration = int((datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).timestamp() * 1000)
                body['expiration'] = expiration
                
                # Call Google Drive API
                response = self.drive_service.service.files().watch(
                    fileId=folder_id,
                    body=body
                ).execute()
                
                resource_id = response['resourceId']
                # Google returns expiration in milliseconds
                expires_at = datetime.fromtimestamp(int(response['expiration']) / 1000, tz=timezone.utc)
                
                print(f"Registered webhook channel {channel_id} for folder {folder_id}")
                
            except Exception as e:
                print(f"Failed to register webhook: {e}")
                raise
        
        # Save channel to database
        channel = models.DriveWebhookChannel(
            channel_id=channel_id,
            resource_id=resource_id,
            resource_type=resource_type,
            watched_resource_id=folder_id,
            expires_at=expires_at,
            active=True
        )
        
        self.db.add(channel)
        self.db.commit()
        self.db.refresh(channel)
        
        return channel
    
    def renew_webhook_channel(self, channel_id: str, ttl_hours: int = 24) -> models.DriveWebhookChannel:
        """
        Renew an existing webhook channel before it expires.
        This is done by stopping the old channel and creating a new one.
        
        Args:
            channel_id: The channel ID to renew
            ttl_hours: New TTL in hours
        
        Returns:
            New DriveWebhookChannel instance
        """
        channel = self.db.query(models.DriveWebhookChannel).filter(
            models.DriveWebhookChannel.channel_id == channel_id
        ).first()
        
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        
        # Stop the old channel
        self.stop_webhook_channel(channel_id)
        
        # Create a new channel for the same resource
        return self.register_webhook_channel(
            folder_id=channel.watched_resource_id,
            resource_type=channel.resource_type,
            ttl_hours=ttl_hours
        )
    
    def stop_webhook_channel(self, channel_id: str) -> bool:
        """
        Stop a webhook channel and mark it as inactive.
        
        Args:
            channel_id: The channel ID to stop
        
        Returns:
            True if successful, False otherwise
        """
        channel = self.db.query(models.DriveWebhookChannel).filter(
            models.DriveWebhookChannel.channel_id == channel_id
        ).first()
        
        if not channel:
            print(f"Channel {channel_id} not found")
            return False
        
        if config.USE_MOCK_DRIVE:
            print(f"MOCK: Would stop webhook channel {channel_id}")
        else:
            try:
                # Call Google Drive API to stop the channel
                self.drive_service.service.channels().stop(
                    body={
                        'id': channel.channel_id,
                        'resourceId': channel.resource_id
                    }
                ).execute()
                
                print(f"Stopped webhook channel {channel_id}")
            except Exception as e:
                print(f"Failed to stop webhook channel: {e}")
                # Continue to deactivate in DB even if API call fails
        
        # Mark as inactive in database
        channel.active = False
        self.db.commit()
        
        return True
    
    def get_active_channels(self) -> list[models.DriveWebhookChannel]:
        """
        Get all active webhook channels.
        
        Returns:
            List of active DriveWebhookChannel instances
        """
        return self.db.query(models.DriveWebhookChannel).filter(
            models.DriveWebhookChannel.active == True
        ).all()
    
    def cleanup_expired_channels(self) -> int:
        """
        Find and deactivate expired channels.
        
        Returns:
            Number of channels deactivated
        """
        now = datetime.now(timezone.utc)
        all_active = self.db.query(models.DriveWebhookChannel).filter(
            models.DriveWebhookChannel.active == True
        ).all()
        
        count = 0
        for channel in all_active:
            expires_at = channel.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if expires_at < now:
                channel.active = False
                count += 1
        
        if count > 0:
            self.db.commit()
            print(f"Deactivated {count} expired channels")
        
        return count
