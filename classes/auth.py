import os
from pathlib import Path
from config import BQ_PATH
from flask import session

class AuthException(Exception): pass

class Auth:
    def is_authorized() -> bool:
        return session['name'] == 'Bqckup'
    
    def authorize(key: str) -> bool:
        legit = Path(
            os.path.join(
                BQ_PATH,
                '.key'
            )
        ).read_text()

        return key == legit
        