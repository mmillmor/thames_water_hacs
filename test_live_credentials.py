"""Local test script to test live Thames Water authentication and meter data retrieval.

Runs 100% independently of Home Assistant.

Usage:
    python test_live_credentials.py <email/username> <password>
"""
import asyncio
from datetime import date, timedelta
import importlib.util
import logging
import os
import sys

# Load api.py directly to avoid importing __init__.py (which imports homeassistant)
_API_PATH = os.path.join(os.path.dirname(__file__), "custom_components", "thames_water", "api.py")
_SPEC = importlib.util.spec_from_file_location("thames_water_api", _API_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["thames_water_api"] = _MODULE
_SPEC.loader.exec_module(_MODULE)

ThamesWaterAPI = _MODULE.ThamesWaterAPI
ThamesWaterAuthError = _MODULE.ThamesWaterAuthError
ThamesWaterConnectionError = _MODULE.ThamesWaterConnectionError

# Configure verbose logging to see all HTTP interactions
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_LOGGER = logging.getLogger("test_live_credentials")


async def main():
    if len(sys.argv) < 3:
        print("\nUsage: python test_live_credentials.py <email/username> <password>\n")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]

    print("=" * 60)
    print(f"Testing Thames Water API for user: {username}")
    print("=" * 60)

    api = ThamesWaterAPI(username=username, password=password)

    try:
        print("\n1. Attempting login...")
        login_success = await api.async_login()
        print(f"   Login result: {login_success}")

        print("\n2. Fetching meters...")
        try:
            meters = await api.async_get_meters()
            print(f"   Found {len(meters)} meter(s):")
            for m in meters:
                print(f"   - Meter ID: {m.meter_id} | Account: {m.account_number} | Address: {m.address}")
        except Exception as err:
            print(f"   Error fetching meters: {err}")

        if meters:
            end_date = date.today()
            start_date = end_date - timedelta(days=30)

            for meter in meters:
                print(f"\n3. Fetching consumption for meter {meter.meter_id} ({start_date} to {end_date})...")
                records = await api.async_get_consumption(meter.meter_id, start_date, end_date)
                print(f"   Retrieved {len(records)} record(s).")
                if records:
                    print(f"   Latest reading date: {records[-1].timestamp}")
                    print(f"   Latest cumulative: {records[-1].cumulative_m3} m³")
                    print(f"   Latest interval volume: {records[-1].volume_m3} m³")
                    print("   First 5 records:")
                    for r in records[:5]:
                        print(f"     - {r.timestamp} | volume: {r.volume_m3} m³ | cumulative: {r.cumulative_m3} m³")

    except ThamesWaterAuthError as err:
        print(f"\n[X] Authentication Error: {err}")
    except ThamesWaterConnectionError as err:
        print(f"\n[X] Connection Error: {err}")
    except Exception as err:
        print(f"\n[X] Unexpected Error: {err}")
        _LOGGER.exception("Detailed exception traceback:")
    finally:
        await api.close()
        print("\n" + "=" * 60)
        print("Test run complete.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
