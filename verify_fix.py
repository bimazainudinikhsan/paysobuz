from src.core.auth import AuthManager

def verify_fix():
    print("=== VERIFYING LOGIN FIX ===")
    auth = AuthManager()
    print("Cookies loaded.")
    
    is_valid = auth.check_session()
    print(f"check_session() result: {is_valid}")
    
    if is_valid:
        print("SUCCESS: Session is now correctly detected as valid!")
    else:
        print("FAILURE: Session is still invalid. Need further investigation.")

if __name__ == "__main__":
    verify_fix()
