"""Platform admin, the same entry as `python -m app.seed.admin`.

The other sample accounts are separate modules so each can be run on its own.
"""

from app.seed.admin import seed_admin
from app.seed.run import run

if __name__ == "__main__":
    run(seed_admin)
