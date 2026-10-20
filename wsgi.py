"""WSGI entry point — `flask --app wsgi run` or `python wsgi.py`."""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug off unless asked for: the debugger is a remote shell to anyone
    # who can reach it. Use `FLASK_DEBUG=1 python wsgi.py` while developing.
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5001")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
