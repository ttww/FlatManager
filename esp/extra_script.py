import re
from pathlib import Path
from typing import Any, cast

from SCons.Script import Import  # type: ignore

Import("env")
env = cast(Any, globals()["env"])

secret_file = Path("include/secrets.h")
content = secret_file.read_text(encoding="utf-8")

match = re.search(r'#define\s+FM_OTA_PASSWORD\s+"([^"]+)"', content)

if not match:
    raise RuntimeError("FM_OTA_PASSWORD not found in include/secrets.h")

ota_password = match.group(1)

env.Append(UPLOAD_FLAGS=[f"--auth={ota_password}"])
