from sqlalchemy.orm import Session
from datetime import datetime, timezone
import base64
from services.google_gmail_service import GoogleGmailService
from services.google_drive_real import GoogleDriveRealService
import models

class GmailSyncService:
    def __init__(self, db: Session, user_email: str):
        self.db = db
        self.user_email = user_email
        self.gmail_service = GoogleGmailService(user_email)
        self.drive_service = GoogleDriveRealService() # Should ideally be scoped or use correct credentials

    def sync_messages(self, start_history_id: str = None):
        """
        Sync messages using History API or initial List.
        """
        if not start_history_id:
            # Initial Sync: List recent messages
            print(f"Initial sync for {self.user_email}")
            result = self.gmail_service.list_messages(max_results=20) # Limit for MVP
            messages = result.get('messages', [])
            self._process_message_list(messages)

            # Return new history ID
            profile = self.gmail_service.get_profile()
            return profile.get('historyId')
        else:
            # Incremental Sync
            print(f"Incremental sync for {self.user_email} from {start_history_id}")
            try:
                history = self.gmail_service.list_history(start_history_id)
                # History returns a list of records, each containing 'messages'
                # We extract all unique message IDs involved
                messages_to_fetch = set()
                if 'history' in history:
                    for record in history['history']:
                        for msg in record.get('messages', []):
                            messages_to_fetch.add(msg['id'])

                self._process_message_list([{'id': mid} for mid in messages_to_fetch])
                return history.get('historyId', start_history_id) # Or get new profile ID
            except Exception as e:
                print(f"History sync failed (possibly expired ID): {e}")
                # Fallback to full sync logic or just return current profile ID
                profile = self.gmail_service.get_profile()
                return profile.get('historyId')

    def _process_message_list(self, messages):
        for msg_summary in messages:
            msg_id = msg_summary['id']
            # Check if already exists
            existing = self.db.query(models.Email).filter(models.Email.google_message_id == msg_id).first()
            if existing:
                continue

            try:
                full_msg = self.gmail_service.get_message(msg_id)
                self._save_email(full_msg)
            except Exception as e:
                print(f"Failed to fetch/save message {msg_id}: {e}")

    def _save_email(self, msg_data):
        payload = msg_data.get('payload', {})
        headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}

        subject = headers.get('subject', '(No Subject)')
        from_addr = headers.get('from', '')
        to_addr = headers.get('to', '')

        # Simple Logic: Save EVERYTHING for now.
        # Real logic would check `from_addr` against leads/contacts tables.

        # Extract Body (Simple text/html extraction)
        body_html = ""
        snippet = msg_data.get('snippet', '')

        if 'body' in payload and payload['body'].get('data'):
             body_html = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html' and part['body'].get('data'):
                    body_html = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break

        # Internal Date
        internal_date = datetime.fromtimestamp(int(msg_data['internalDate'])/1000, tz=timezone.utc)

        email_entry = models.Email(
            google_message_id=msg_data['id'],
            thread_id=msg_data['threadId'],
            user_email=self.user_email,
            subject=subject,
            from_address=from_addr,
            to_address=to_addr,
            snippet=snippet,
            body_html=body_html,
            internal_date=internal_date
        )
        self.db.add(email_entry)
        self.db.commit()
        self.db.refresh(email_entry)

        # Handle Attachments
        # (Simplified: check parts)
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('filename') and part['body'].get('attachmentId'):
                    self._process_attachment(email_entry, msg_data['id'], part)

    def _process_attachment(self, email_entry, message_id, part):
        filename = part['filename']
        mime_type = part['mimeType']
        attachment_id = part['body']['attachmentId']

        drive_file_id = None

        # 1. Download
        try:
            attachment = self.gmail_service.get_attachment(message_id, attachment_id)
            data = base64.urlsafe_b64decode(attachment['data'])

            # 2. Upload to Drive (Only if we have a linked entity folder)
            # This requires finding the '03. Documentos Gerais' subfolder of the linked entity
            # For MVP, we skip automatic upload if entity_id is missing to avoid root clutter.

            if email_entry.entity_id and email_entry.entity_type:
                # Logic to find folder would go here (requires DB lookup of DriveFolder)
                # target_folder = self.db.query(models.DriveFolder).filter(...).first()
                # if target_folder:
                #    uploaded = self.drive_service.upload_file(data, filename, mime_type, target_folder.folder_id)
                #    drive_file_id = uploaded.get('id')
                pass

            # 3. Save Metadata
            att_entry = models.EmailAttachment(
                email_id=email_entry.id,
                file_name=filename,
                mime_type=mime_type,
                drive_file_id=drive_file_id
            )
            self.db.add(att_entry)
            self.db.commit()

        except Exception as e:
            print(f"Attachment processing failed: {e}")
