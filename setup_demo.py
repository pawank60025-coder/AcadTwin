"""Create a clean, fictional AcadTwin demo database for local use."""

from pathlib import Path
import sys

from database import DB_NAME, create_database
from populate_demo import populate_demo


def main():
    db_path = Path(DB_NAME)
    reset = "--reset" in sys.argv

    if db_path.exists():
        if not reset:
            print(f"Database already exists: {db_path.name}")
            print("Nothing was changed. Use `python setup_demo.py --reset` to replace it with fictional demo data.")
            return
        db_path.unlink()
        print(f"Removed existing {db_path.name}.")

    create_database()
    populate_demo()
    print()
    print("AcadTwin demo database is ready.")
    print("Run: python app.py")


if __name__ == "__main__":
    main()
