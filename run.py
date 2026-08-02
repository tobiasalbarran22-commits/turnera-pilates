"""
Este es el archivo que se ejecuta para levantar el servidor:
    python run.py
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
