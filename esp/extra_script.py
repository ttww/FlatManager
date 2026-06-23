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

import re
from pathlib import Path
from typing import Any, cast

from SCons.Script import Import  # type: ignore

Import("env")
env = cast(Any, globals()["env"])

project_dir = Path(str(env.subst("$PROJECT_DIR")))
secret_file = project_dir / "include" / "secrets.h"

if not secret_file.exists():
    raise RuntimeError(f"OTA secret file not found: {secret_file}")

content = secret_file.read_text(encoding="utf-8")

match = re.search(r'#define\s+FM_OTA_PASSWORD\s+"([^"]+)"', content)

if not match:
    raise RuntimeError(f"FM_OTA_PASSWORD not found in {secret_file}")

ota_password = match.group(1)

if not ota_password or ota_password == "CHANGE_ME_OTA_PASSWORD":
    raise RuntimeError(
        f"Invalid FM_OTA_PASSWORD in {secret_file}: replace the placeholder before OTA upload"
    )

env.Append(UPLOAD_FLAGS=[f"--auth={ota_password}"])
print(f"Using OTA password from {secret_file}")
