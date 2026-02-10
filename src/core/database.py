import json
import os
import time
from datetime import datetime, timedelta

class PaymentDatabase:
    def __init__(self, filename="payment_history.json"):
        self.filename = filename
        self.data = self._load_data()

    def _load_data(self):
        if not os.path.exists(self.filename):
            return {"payments": [], "user_settings": {}, "global_settings": {}}
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "user_settings" not in data:
                    data["user_settings"] = {}
                if "global_settings" not in data:
                    data["global_settings"] = {}
                return data
        except Exception as e:
            print(f"Error loading database: {e}")
            return {"payments": [], "user_settings": {}, "global_settings": {}}

    def _save_data(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving database: {e}")

    def add_payment(self, user_id, payment_url, method, amount, message, donor_name, order_id=None):
        """Adds a new payment record."""
        # Use order_id as the unique ID if provided, otherwise generate one
        if order_id:
            payment_id = order_id
        else:
            payment_id = f"pay_{int(time.time())}_{user_id}"
        
        record = {
            "id": payment_id,
            "user_id": user_id,
            "status": "pending",
            "url": payment_url,
            "method": method,
            "amount": amount,
            "message": message,
            "donor_name": donor_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "details": {} # Store API response details here if needed
        }
        
        # Check if exists to prevent duplicates
        for p in self.data["payments"]:
            if p["id"] == payment_id:
                # Update existing instead of adding
                p.update(record)
                self._save_data()
                return payment_id

        self.data["payments"].append(record)
        self._save_data()
        return payment_id

    def update_payment_status(self, payment_id, new_status, details=None):
        """Updates the status of a payment."""
        for p in self.data["payments"]:
            if p["id"] == payment_id:
                p["status"] = new_status
                p["updated_at"] = datetime.now().isoformat()
                if details:
                    # Merge details instead of overwriting to preserve message_id etc.
                    if "details" not in p:
                        p["details"] = {}
                    if isinstance(p["details"], dict) and isinstance(details, dict):
                        p["details"].update(details)
                    else:
                        p["details"] = details
                self._save_data()
                return True
        return False
        
    def get_pending_payments(self, max_age_minutes=60):
        """Returns a list of all pending payments created within the last max_age_minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        active_payments = []
        
        for p in self.data["payments"]:
            if p["status"] == "pending":
                try:
                    # Handle ISO format parsing
                    created_at = datetime.fromisoformat(p["created_at"])
                    if created_at > cutoff_time:
                        active_payments.append(p)
                except Exception as e:
                    # If date is missing or invalid, skip it (treat as old)
                    continue
                    
        return active_payments

    def get_user_history(self, user_id, limit=10):
        """Returns payment history for a specific user."""
        user_payments = [p for p in self.data["payments"] if p["user_id"] == user_id]
        # Sort by created_at desc
        user_payments.sort(key=lambda x: x["created_at"], reverse=True)
        return user_payments[:limit]

    def get_user_success_total(self, user_id):
        """Returns total successful payment amount for a specific user."""
        total = 0
        for p in self.data["payments"]:
            if p["user_id"] == user_id and p["status"] == "success":
                try:
                    total += float(p["amount"])
                except:
                    pass
        return total

    def get_payment(self, payment_id):
        for p in self.data["payments"]:
            if p["id"] == payment_id:
                return p
        return None

    def get_user_setting(self, user_id, key, default=None):
        """Get a specific setting for a user."""
        user_id = str(user_id)
        if user_id in self.data["user_settings"]:
            return self.data["user_settings"][user_id].get(key, default)
        return default

    def set_user_setting(self, user_id, key, value):
        """Set a specific setting for a user."""
        user_id = str(user_id)
        if user_id not in self.data["user_settings"]:
            self.data["user_settings"][user_id] = {}
        
        self.data["user_settings"][user_id][key] = value
        self._save_data()

    def get_global_setting(self, key, default=None):
        """Get a global setting."""
        return self.data["global_settings"].get(key, default)

    def set_global_setting(self, key, value):
        """Set a global setting."""
        self.data["global_settings"][key] = value
        self._save_data()

    def get_bot_info(self):
        """Get the custom bot info/announcement."""
        return self.get_global_setting("bot_info_text", "")

    def set_bot_info(self, text):
        """Set the custom bot info/announcement."""
        self.set_global_setting("bot_info_text", text)
