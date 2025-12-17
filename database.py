import firebase_admin
from firebase_admin import credentials, firestore
import os
import structlog
import json
import asyncio

logger = structlog.get_logger(__name__)

def init_firebase(credentials_path, is_json_string=False):
    """
    Initializes Firebase Admin SDK from a file path or a JSON string,
    and returns a Firestore client.
    """
    try:
        if not firebase_admin._apps:
            if is_json_string:
                # Initialize from JSON string content
                cred = credentials.Certificate(json.loads(credentials_path))
            else:
                # Initialize from file path
                cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
            
        db = firestore.client()
        logger.info("Firebase Admin SDK initialized successfully.")
        return db
    except Exception as e:
        logger.error("Error initializing Firebase Admin SDK", error=e)
        return None

def get_user_data(db, user_id):
    """Retrieves a user's data from Firestore."""
    if not db:
        logger.error("Firestore not initialized.")
        return None
    try:
        user_ref = db.collection('users').document(str(user_id))
        doc = user_ref.get() # Removed await
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error("Error getting user data", user_id=user_id, error=e)
        return None

def _add_xp_sync_transaction(transaction, db, user_id, username, xp_to_add):
    user_ref = db.collection('users').document(str(user_id))
    doc = transaction.get(user_ref)

    if doc.exists:
        current_xp = doc.to_dict().get('xp', 0)
        new_xp = current_xp + xp_to_add
        transaction.update(user_ref, {'xp': new_xp})
        logger.info("Updated XP for user", username=username, user_id=user_ref.id, new_xp=new_xp)
    else:
        transaction.set(user_ref, {
            'username': username,
            'xp': xp_to_add
        })
        logger.info("Created new user", username=username, user_id=user_ref.id, xp=xp_to_add)

async def add_xp(db, user_id, username, xp_to_add=1):
    """Adds XP to a user. Creates the user document if they don't exist."""
    if not db:
        logger.error("Firestore not initialized.")
        return
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, # Use the default thread pool executor
            db.run_transaction, # Function to run in the executor
            _add_xp_sync_transaction, # The synchronous update function for the transaction
            db, user_id, username, xp_to_add # Arguments to pass to _add_xp_sync_transaction
        )
    except Exception as e:
        logger.error("Error adding XP for user", user_id=user_id, error=e)

def get_leaderboard(db, limit=10):
    """Retrieves the top users from Firestore."""
    if not db:
        logger.error("Firestore not initialized.")
        return []
    try:
        users_ref = db.collection('users')
        query = users_ref.order_by('xp', direction=firestore.Query.DESCENDING).limit(limit)
        results = query.stream()
        leaderboard_data = []
        for doc in results:
            data = doc.to_dict()
            leaderboard_data.append((data.get('username', 'Unknown'), data.get('xp', 0)))
        return leaderboard_data
    except Exception as e:
        logger.error("Error getting leaderboard", error=e)
        return []


def _transfer_xp_sync_transaction(transaction, db, from_user_id, to_user_id, amount):
    from_user_ref = db.collection('users').document(str(from_user_id))
    to_user_ref = db.collection('users').document(str(to_user_id))

    from_doc = transaction.get(from_user_ref)
    to_doc = transaction.get(to_user_ref)

    if not from_doc.exists or not to_doc.exists:
        logger.warning("One or both users in transaction do not exist.", from_user_id=from_user_id, to_user_id=to_user_id)
        return False
        
    from_xp = from_doc.to_dict().get('xp', 0)
    to_xp = to_doc.to_dict().get('xp', 0)

    # Ensure victim has enough XP
    if from_xp < amount:
        return False # Not enough XP to steal

    # Perform the transfer
    transaction.update(from_user_ref, {'xp': from_xp - amount})
    transaction.update(to_user_ref, {'xp': to_xp + amount})
    
    return True

async def transfer_xp(db, from_user_id, to_user_id, amount):
    """Public function to initiate an XP transfer."""
    if not db:
        logger.error("Firestore not initialized.")
        return False
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, # Use the default thread pool executor
            db.run_transaction, # Function to run in the executor
            _transfer_xp_sync_transaction, # The synchronous update function for the transaction
            db, from_user_id, to_user_id, amount # Arguments to pass to _transfer_xp_sync_transaction
        )
    except Exception as e:
        logger.error("Error transferring XP", from_user_id=from_user_id, to_user_id=to_user_id, error=e)
        return False