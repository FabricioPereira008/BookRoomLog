import os
import uvicorn

from backend.app.core.config import DEFAULT_PORT

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host=os.environ.get("BOOKROOM_HOST", "127.0.0.1"),
        port=int(os.environ.get("BOOKROOM_PORT", str(DEFAULT_PORT))),
        reload=os.environ.get("BOOKROOM_RELOAD", "1") == "1",
    )
