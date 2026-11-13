"""The Mixel cloud: is it up, and, signed in, who you are and the reviewed apps.

    python examples/cloud.py          health; with `mixel login` (or MIXEL_TOKEN), also your account and the apps
"""

from ox1audio.api import MixelError, connect
from ox1audio.cloud import AuthenticatedClient
from ox1audio.cloud.api.default import app_catalog, health, me

cloud = connect()
try:
    print(f"cloud: {health.sync(client=cloud).status}")
    if isinstance(cloud, AuthenticatedClient):
        print(f"account: {me.sync(client=cloud).status}")
        for app in app_catalog.sync(client=cloud).apps:
            print(f"  {app.display_name:<24} {app.version}")
except MixelError as error:
    raise SystemExit(f"{error.code}: {error.message}" + (f"\nfix: {error.fix}" if error.fix else "")) from None
