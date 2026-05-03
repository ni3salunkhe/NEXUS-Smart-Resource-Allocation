import asyncio
import sys
import os

# Adjust path to include backend for shared modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from dotenv import load_dotenv
load_dotenv("backend/.env")

try:
    from shared.kafka import ensure_topics_exist
    from shared.config import get_settings
    print("Imports successful")
except ImportError as e:
    # Try adding backend to sys.path if not already there
    sys.path.insert(0, os.path.abspath("backend"))
    from shared.kafka import ensure_topics_exist
    from shared.config import get_settings
    print("Imports successful after sys.path adjustment")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

async def test_kafka_connectivity():
    settings = get_settings()
    print(f"Testing connectivity to Kafka at: {settings.KAFKA_BOOTSTRAP_SERVERS}")
    
    try:
        # ensure_topics_exist internally creates an admin client and tries to list/create topics
        # This is a solid connectivity test.
        await asyncio.wait_for(ensure_topics_exist(), timeout=10.0)
        print("SUCCESS: Kafka is reachable and topics are initialized/verified.")
    except asyncio.TimeoutError:
        print("FAILURE: Kafka connection timed out (10s).")
    except Exception as e:
        print(f"FAILURE: Kafka connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_kafka_connectivity())
