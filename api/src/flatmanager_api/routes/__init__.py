from fastapi import APIRouter

from .access_codes import router as access_codes_router
from .access_logs import router as access_logs_router
from .apartments import router as apartments_router
from .commands import router as commands_router
from .device_agent import router as device_agent_router
from .devices import router as devices_router
from .guest import router as guest_router

router = APIRouter()
router.include_router(apartments_router)
router.include_router(devices_router)
router.include_router(access_codes_router)
router.include_router(commands_router)
router.include_router(access_logs_router)
router.include_router(guest_router)
router.include_router(device_agent_router)
