from flask import session
from classes.config import Config

class AuthException(Exception): pass

class Auth:
    def is_authorized() -> bool:
        try:
            return session['name'] == 'Bqckup'
        except KeyError:
            return False
    
    def authorize(key: str) -> bool:
        legit = Config().read('auth', 'password')
        return key.strip() == legit.strip()
        