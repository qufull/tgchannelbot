

from aiogram.fsm.state import StatesGroup, State


class AdminStates(StatesGroup):
    wait_inbox_forward = State()
    wait_target_forward = State()